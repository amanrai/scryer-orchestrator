import uuid
from datetime import datetime, timezone

from ..config import settings
from ..schemas.process import (
    HookEventName,
    NotificationEvent,
    PhaseStatus,
    StepRuntimeDetails,
    StepStatus,
    WorkflowPhaseInsert,
    WorkflowHookMap,
    WorkflowInstanceCreate,
    WorkflowInstanceRead,
    WorkflowInstanceSummary,
    WorkflowStepConfigUpdate,
    WorkflowStepInsert,
    WorkflowStepMove,
    WorkflowStepTarget,
)
from . import event_log
from .execution import kill_tmux_session
from .hooks import fire_hook
from .messaging import get_redis, list_pending
from .runtime import workflow_log_path
from .workflows import get_workflow

TERMINAL_WORKFLOW_STATUSES = {"completed", "failed"}
LIVE_STEP_STATUSES = {"dispatched", "running", "rfi"}
SUCCESS_STEP_STATUSES = {"completed", "pass"}
TERMINAL_STEP_STATUSES = SUCCESS_STEP_STATUSES | {"failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_key(workflow_uuid: str) -> str:
    return f"workflow:{workflow_uuid}"


async def _save_instance(instance: WorkflowInstanceRead) -> None:
    redis = await get_redis()
    pending = []
    for message in list_pending():
        if message.get("workflow_uuid") == instance.workflow_uuid:
            pending.append(message["message_id"])
    instance.pending_messages = pending
    await redis.set(_process_key(instance.workflow_uuid), instance.model_dump_json())
    await redis.sadd("workflows", instance.workflow_uuid)


async def get_workflow_instance(workflow_uuid: str) -> WorkflowInstanceRead | None:
    redis = await get_redis()
    data = await redis.get(_process_key(workflow_uuid))
    if data is None:
        return None
    return WorkflowInstanceRead.model_validate_json(data)


async def list_workflow_instances() -> list[WorkflowInstanceSummary]:
    redis = await get_redis()
    ids = await redis.smembers("workflows")
    results = []
    for workflow_uuid in sorted(ids):
        instance = await get_workflow_instance(workflow_uuid)
        if instance is None:
            continue
        results.append(
            WorkflowInstanceSummary(
                workflow_uuid=instance.workflow_uuid,
                task_id=instance.task_id,
                workflow_name=instance.workflow_name,
                project_name=instance.project_name,
                status=instance.status,
                current_phase=instance.current_phase,
                total_phases=len(instance.phases),
                current_session_name=instance.current_session_name,
                created_at=instance.created_at,
                updated_at=instance.updated_at,
            )
        )
    return results


def _copy_workflow_hooks(workflow_definition: dict) -> WorkflowHookMap:
    return WorkflowHookMap.model_validate(workflow_definition.get("hooks", {}))


def _step_from_name(step_name: str, config: dict | None = None) -> StepStatus:
    config = config or {}
    return StepStatus(
        name=step_name,
        config=config,
        model=config.get("model"),
        executor_label=config.get("executor_label"),
        timeout_seconds=config.get("timeout_seconds") or settings.process_timeout_seconds,
        user_overrides=config.get("user_overrides", {}),
    )


def _phase_unstarted(phase: PhaseStatus) -> bool:
    return phase.status == "pending" and all(step.status == "pending" for step in phase.steps)


def _find_step(instance: WorkflowInstanceRead, phase_number: int, step_name: str) -> tuple[PhaseStatus | None, StepStatus | None]:
    if phase_number < 0 or phase_number >= len(instance.phases):
        return None, None
    phase = instance.phases[phase_number]
    for step in phase.steps:
        if step.name == step_name:
            return phase, step
    return phase, None


def _recompute_phase_statuses(instance: WorkflowInstanceRead) -> None:
    for phase in instance.phases:
        if phase.status == "completed" and phase.number < instance.current_phase:
            continue
        if phase.pending_hook_event:
            phase.status = "running"
        elif not phase.steps:
            phase.status = "pending"
        elif any(step.status == "failed" for step in phase.steps):
            phase.status = "failed"
        elif any(step.status in LIVE_STEP_STATUSES for step in phase.steps):
            phase.status = "running"
        elif any(step.status in SUCCESS_STEP_STATUSES for step in phase.steps):
            phase.status = "running"
        else:
            phase.status = "pending"


def _earliest_unfinished_phase(instance: WorkflowInstanceRead) -> int:
    for index, phase in enumerate(instance.phases):
        if any(step.status not in SUCCESS_STEP_STATUSES for step in phase.steps):
            return index
    return len(instance.phases)


def _hook_name(detail: dict | None) -> HookEventName | None:
    if not detail:
        return None
    value = detail.get("hook_event_name")
    if value in {
        "pre_workflow",
        "post_workflow",
        "pre_phase",
        "post_phase",
        "pre_step",
        "step",
        "post_step",
        "on_workflow_pause",
        "on_workflow_continue",
        "on_step_timeout",
        "on_step_user_kill",
    }:
        return value
    return None


def _session_name_from_detail(detail: dict | None) -> str | None:
    if not detail:
        return None
    for key in ("session_name", "session_id", "session", "tmux_session", "tmuxSession"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _record_step_session(instance: WorkflowInstanceRead, step: StepStatus, session_name: str | None) -> None:
    if not session_name:
        return
    if session_name not in step.tmux_sessions:
        step.tmux_sessions.append(session_name)
    instance.current_session_name = session_name


def _record_step_start(step: StepStatus, timestamp: str) -> None:
    if not step.started_ats or step.started_ats[-1] != timestamp:
        step.started_ats.append(timestamp)


def _record_step_completion(step: StepStatus, timestamp: str) -> None:
    if not step.completed_ats or step.completed_ats[-1] != timestamp:
        step.completed_ats.append(timestamp)


def _phase_all_steps_terminal(phase: PhaseStatus) -> bool:
    return all(step.status in TERMINAL_STEP_STATUSES for step in phase.steps)


def _phase_all_steps_passed(phase: PhaseStatus) -> bool:
    return bool(phase.steps) and all(step.status == "pass" for step in phase.steps)


def _phase_is_complete(phase: PhaseStatus) -> bool:
    if phase.completionMode == "execCount":
        return phase.phase_iteration >= phase.maxTimes
    return _phase_all_steps_passed(phase)


def _reset_phase_for_next_iteration(phase: PhaseStatus) -> None:
    phase.pending_hook_event = None
    phase.iteration_should_restart = False
    phase.status = "pending"
    for step in phase.steps:
        step.status = "pending"
        step.tmux_sessions = []
        step.detail = None
        step.pending_hook_event = None


def _phase_ready_for_post_phase(phase: PhaseStatus) -> bool:
    if phase.type == "ExecSerial" and phase.completionMode == "allPass" and phase.iteration_should_restart:
        return True
    return _phase_all_steps_terminal(phase)


def _fail_instance(instance: WorkflowInstanceRead, now: str, detail: dict | None = None) -> None:
    instance.pending_hook_event = None
    instance.status = "failed"
    if detail is not None:
        instance.additional_caller_info = {**instance.additional_caller_info, "_failure_detail": detail}
    instance.updated_at = now


def _has_hooks(instance: WorkflowInstanceRead, hook_event_name: HookEventName) -> bool:
    return bool(getattr(instance.hooks, hook_event_name))


async def _launch_workflow_hook(instance: WorkflowInstanceRead, hook_event_name: HookEventName) -> bool:
    if not _has_hooks(instance, hook_event_name):
        return False
    await _fire_group(instance, hook_event_name)
    instance.pending_hook_event = hook_event_name
    return True


async def _launch_phase_hook(instance: WorkflowInstanceRead, phase: PhaseStatus, hook_event_name: HookEventName) -> bool:
    if not _has_hooks(instance, hook_event_name):
        return False
    await _fire_group(instance, hook_event_name, phase_number=phase.number, phase_iteration=phase.phase_iteration)
    phase.pending_hook_event = hook_event_name
    return True


async def _launch_step_hook(instance: WorkflowInstanceRead, phase: PhaseStatus, step: StepStatus, hook_event_name: HookEventName) -> bool:
    if not _has_hooks(instance, hook_event_name):
        return False
    await _fire_group(
        instance,
        hook_event_name,
        phase_number=phase.number,
        phase_iteration=phase.phase_iteration,
        step=step,
    )
    step.pending_hook_event = hook_event_name
    return True


async def _launch_step_pipeline(instance: WorkflowInstanceRead, phase: PhaseStatus, step: StepStatus) -> None:
    if step.status in {"completed", "pass", "failed"} or step.pending_hook_event:
        return
    if step.status == "pending":
        launched = await _launch_step_hook(instance, phase, step, "pre_step")
        if launched:
            step.status = "dispatched"
            _record_step_start(step, _now())
            return
        launched = await _launch_step_hook(instance, phase, step, "step")
        if launched:
            step.status = "dispatched"
            _record_step_start(step, _now())
            return
        raise RuntimeError(
            f"Workflow {instance.workflow_name!r} cannot dispatch step {step.name!r}: "
            "no pre_step or step hooks are configured."
        )


async def _launch_phase_steps(instance: WorkflowInstanceRead, phase: PhaseStatus) -> None:
    if phase.type == "ExecSerial":
        if any(step.status in LIVE_STEP_STATUSES or step.pending_hook_event for step in phase.steps):
            return
        for step in phase.steps:
            if step.status == "pending" and not step.pending_hook_event:
                await _launch_step_pipeline(instance, phase, step)
                return
        return
    for step in phase.steps:
        if step.status == "pending" and not step.pending_hook_event:
            await _launch_step_pipeline(instance, phase, step)


async def _advance_workflow(instance: WorkflowInstanceRead) -> None:
    if instance.status != "running" or instance.pending_hook_event is not None:
        return
    if instance.current_phase >= len(instance.phases):
        launched = await _launch_workflow_hook(instance, "post_workflow")
        if launched:
            instance.updated_at = _now()
            await _save_instance(instance)
            return
        raise RuntimeError(
            f"Workflow {instance.workflow_name!r} reached terminal advancement without a post_workflow hook."
        )

    phase = instance.phases[instance.current_phase]
    if phase.pending_hook_event is None and phase.status == "pending":
        phase.status = "running"
        launched = await _launch_phase_hook(instance, phase, "pre_phase")
        if launched:
            instance.updated_at = _now()
            await _save_instance(instance)
            return
        raise RuntimeError(
            f"Workflow {instance.workflow_name!r} phase {phase.number} cannot start without a pre_phase hook."
        )

    if phase.pending_hook_event is None:
        if _phase_ready_for_post_phase(phase):
            launched = await _launch_phase_hook(instance, phase, "post_phase")
            if launched:
                instance.updated_at = _now()
                await _save_instance(instance)
                return
            raise RuntimeError(
                f"Workflow {instance.workflow_name!r} phase {phase.number} cannot complete without a post_phase hook."
            )
        await _launch_phase_steps(instance, phase)
        if any(step.status == "failed" for step in phase.steps):
            phase.status = "failed"
            instance.status = "failed"

    _recompute_phase_statuses(instance)
    instance.updated_at = _now()
    await _save_instance(instance)


async def create_workflow_instance(body: WorkflowInstanceCreate) -> WorkflowInstanceRead:
    workflow = get_workflow(body.workflow_name)
    workflow_uuid = str(uuid.uuid4())
    now = _now()
    phases = []
    for phase_number, phase_definition in enumerate(workflow.phases):
        configured = body.step_configs.get(phase_number, {})
        phases.append(
            PhaseStatus(
                number=phase_number,
                type=phase_definition.type,
                completionMode=phase_definition.completionMode,
                maxTimes=phase_definition.maxTimes,
                steps=[_step_from_name(step_name, configured.get(step_name)) for step_name in phase_definition.steps],
            )
        )
    instance = WorkflowInstanceRead(
        workflow_uuid=workflow_uuid,
        task_id=body.task_id,
        workflow_name=workflow.name,
        workflow_definition=workflow.model_dump(),
        project_name=body.project_name,
        project_base_repo_path_relative_to_common_volume=body.project_base_repo_path_relative_to_common_volume,
        project_identities_associated=body.project_identities_associated,
        project_environment_variables_associated=body.project_environment_variables_associated,
        current_session_name=None,
        additional_caller_info=body.additional_caller_info,
        status="pending",
        current_phase=0,
        phases=phases,
        hooks=_copy_workflow_hooks(workflow.model_dump()),
        post_step_on_fail=body.post_step_on_fail,
        created_at=now,
        updated_at=now,
    )
    await _save_instance(instance)
    event_log.record(instance.workflow_uuid, "workflow_created")
    return instance


async def _fire_group(
    instance: WorkflowInstanceRead,
    hook_event_name: str,
    phase_number: int | None = None,
    phase_iteration: int | None = None,
    step: StepStatus | None = None,
) -> list[str]:
    sessions = []
    for hook in getattr(instance.hooks, hook_event_name):
        step_details = None
        if step is not None:
            step_details = StepRuntimeDetails(
                name=step.name,
                config=step.config,
                model=step.model,
                executor_label=step.executor_label,
                timeout_seconds=step.timeout_seconds,
                user_overrides=step.user_overrides,
            )
        try:
            session = fire_hook(
                instance,
                hook_event_name=hook_event_name,
                hook=hook,
                phase_number=phase_number,
                phase_iteration=phase_iteration,
                step=step_details,
            )
        except Exception as exc:
            event_log.record(
                instance.workflow_uuid,
                f"hook_launch_failed:{hook_event_name}",
                phase_number=phase_number,
                step_name=step.name if step else None,
                detail={"asset_name": hook.asset_name, "error": str(exc), "failure_policy": hook.failure_policy},
            )
            if hook.failure_policy == "fail":
                raise
            continue
        sessions.append(session)
        event_log.record(
            instance.workflow_uuid,
            f"hook_fired:{hook_event_name}",
            phase_number=phase_number,
            step_name=step.name if step else None,
            detail={"asset_name": hook.asset_name, "session": session},
        )
    return sessions


async def start_workflow_instance(workflow_uuid: str) -> WorkflowInstanceRead:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        raise ValueError(f"Workflow instance not found: {workflow_uuid}")
    try:
        launched = await _launch_workflow_hook(instance, "pre_workflow")
        if not launched:
            raise RuntimeError(
                f"Workflow {instance.workflow_name!r} cannot start without a pre_workflow hook."
            )
    except Exception:
        instance.status = "failed"
        instance.updated_at = _now()
        await _save_instance(instance)
        raise
    instance.status = "running"
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def _dispatch_current_phase(instance: WorkflowInstanceRead) -> None:
    await _advance_workflow(instance)


async def pause_workflow_instance(workflow_uuid: str) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    instance.status = "paused"
    instance.updated_at = _now()
    await _save_instance(instance)
    await _fire_group(instance, "on_workflow_pause")
    event_log.record(instance.workflow_uuid, "workflow_paused")
    return instance


async def resume_workflow_instance(workflow_uuid: str) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    instance.status = "running"
    instance.updated_at = _now()
    await _save_instance(instance)
    await _fire_group(instance, "on_workflow_continue")
    await _dispatch_current_phase(instance)
    event_log.record(instance.workflow_uuid, "workflow_resumed")
    return instance


async def delete_workflow_instance(workflow_uuid: str) -> bool:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return False
    sessions_to_kill: set[str] = set()
    if instance.current_session_name:
        sessions_to_kill.add(instance.current_session_name)
    for phase in instance.phases:
        for step in phase.steps:
            for session in step.tmux_sessions:
                sessions_to_kill.add(session)
    for session in sessions_to_kill:
        kill_tmux_session(session)
    redis = await get_redis()
    await redis.delete(_process_key(workflow_uuid))
    await redis.srem("workflows", workflow_uuid)
    event_log.record(workflow_uuid, "workflow_deleted")
    return True


async def update_step_config(workflow_uuid: str, body: WorkflowStepConfigUpdate) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        raise ValueError("Completed or failed workflows cannot be reconfigured.")
    _phase, step = _find_step(instance, body.phase_number, body.step_name)
    if step is None:
        raise ValueError(f"Step not found: phase={body.phase_number} step={body.step_name}")
    if step.status != "pending":
        raise ValueError("Only pending steps can be reconfigured.")
    step.config.update(body.config)
    if body.model is not None:
        step.model = body.model
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def add_phase(workflow_uuid: str, body: WorkflowPhaseInsert) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        raise ValueError("Completed or failed workflows cannot be edited.")
    if body.insert_index < 0 or body.insert_index > len(instance.phases):
        raise ValueError("Invalid phase insertion index.")
    earliest = _earliest_unfinished_phase(instance)
    if body.insert_index < earliest:
        raise ValueError("Only future, unstarted phases can be inserted.")
    instance.phases.insert(body.insert_index, PhaseStatus(number=body.insert_index, steps=[], status="pending"))
    for index, phase in enumerate(instance.phases):
        phase.number = index
    instance.current_phase = _earliest_unfinished_phase(instance)
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def delete_phase(workflow_uuid: str, phase_number: int) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        raise ValueError("Completed or failed workflows cannot be edited.")
    if phase_number < 0 or phase_number >= len(instance.phases):
        raise ValueError("Invalid phase number.")
    phase = instance.phases[phase_number]
    if not _phase_unstarted(phase):
        raise ValueError("Only future, unstarted phases can be deleted.")
    del instance.phases[phase_number]
    for index, item in enumerate(instance.phases):
        item.number = index
    _recompute_phase_statuses(instance)
    instance.current_phase = _earliest_unfinished_phase(instance)
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def add_step(workflow_uuid: str, body: WorkflowStepInsert) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        raise ValueError("Completed or failed workflows cannot be edited.")
    if body.phase_number < 0 or body.phase_number >= len(instance.phases):
        raise ValueError("Invalid phase number.")
    phase = instance.phases[body.phase_number]
    if not _phase_unstarted(phase):
        raise ValueError("Only future, unstarted phases can be edited.")
    if any(step.name == body.step_name for step in phase.steps):
        raise ValueError("This phase already contains that step.")
    phase.steps.append(
        StepStatus(
            name=body.step_name,
            config=body.config,
            model=body.model,
            executor_label=body.executor_label,
            timeout_seconds=body.timeout_seconds or settings.process_timeout_seconds,
            user_overrides=body.user_overrides,
        )
    )
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def delete_step(workflow_uuid: str, body: WorkflowStepTarget) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        raise ValueError("Completed or failed workflows cannot be edited.")
    phase, step = _find_step(instance, body.phase_number, body.step_name)
    if phase is None or step is None:
        raise ValueError(f"Step not found: phase={body.phase_number} step={body.step_name}")
    if not _phase_unstarted(phase):
        raise ValueError("Only future, unstarted phases can be edited.")
    phase.steps = [item for item in phase.steps if item.name != body.step_name]
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def move_step(workflow_uuid: str, body: WorkflowStepMove) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        raise ValueError("Completed or failed workflows cannot be edited.")
    source_phase, step = _find_step(instance, body.from_phase_number, body.step_name)
    if source_phase is None or step is None:
        raise ValueError(f"Step not found: phase={body.from_phase_number} step={body.step_name}")
    if body.to_phase_number < 0 or body.to_phase_number >= len(instance.phases):
        raise ValueError("Invalid target phase.")
    target_phase = instance.phases[body.to_phase_number]
    if not _phase_unstarted(source_phase) or not _phase_unstarted(target_phase):
        raise ValueError("Only future, unstarted phases can be edited.")
    if any(item.name == body.step_name for item in target_phase.steps):
        raise ValueError("Target phase already contains that step.")
    source_phase.steps = [item for item in source_phase.steps if item.name != body.step_name]
    target_phase.steps.append(step)
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def run_step(workflow_uuid: str, body: WorkflowStepTarget) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status != "paused":
        raise ValueError("Only paused workflows can run a specific step.")
    earliest = _earliest_unfinished_phase(instance)
    if body.phase_number != earliest:
        raise ValueError("Only the earliest runnable phase can start individual steps.")
    phase, step = _find_step(instance, body.phase_number, body.step_name)
    if phase is None or step is None:
        raise ValueError(f"Step not found: phase={body.phase_number} step={body.step_name}")
    if step.status != "pending":
        raise ValueError("Only pending steps can be run individually.")
    instance.status = "running"
    phase.status = "running"
    try:
        await _launch_step_pipeline(instance, phase, step)
    except Exception as exc:
        step.status = "failed"
        _record_step_completion(step, _now())
        step.detail = {"reason": "hook_launch_failed", "error": str(exc)}
        phase.status = "failed"
        instance.status = "failed"
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def kill_step(workflow_uuid: str, body: WorkflowStepTarget) -> WorkflowInstanceRead | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    if instance.status not in {"running", "paused"}:
        raise ValueError("Only running or paused workflows can kill a live step.")
    phase, step = _find_step(instance, body.phase_number, body.step_name)
    if phase is None or step is None:
        raise ValueError(f"Step not found: phase={body.phase_number} step={body.step_name}")
    if step.status not in LIVE_STEP_STATUSES:
        raise ValueError("Only live steps can be user-killed.")
    await _launch_step_hook(instance, phase, step, "on_step_user_kill")
    instance.updated_at = _now()
    await _save_instance(instance)
    return instance


async def handle_notification(event: NotificationEvent) -> None:
    instance = await get_workflow_instance(event.workflow_uuid)
    if instance is None:
        return
    event_log.record(
        event.workflow_uuid,
        event.event,
        phase_number=event.phase_number,
        step_name=event.step_name,
        detail=event.detail,
    )
    if instance.status in TERMINAL_WORKFLOW_STATUSES:
        return
    hook_event_name = _hook_name(event.detail)
    session_name = _session_name_from_detail(event.detail)
    now = _now()
    if event.phase_number is None and event.step_name is None:
        if event.event == "pass":
            _fail_instance(instance, now, {"reason": "invalid_pass_scope", "scope": "workflow"})
            await _save_instance(instance)
            return
        if session_name:
            instance.current_session_name = session_name
        if hook_event_name and instance.pending_hook_event != hook_event_name:
            return
        if event.event == "done":
            completed_hook = hook_event_name or instance.pending_hook_event
            instance.pending_hook_event = None
            if completed_hook == "post_workflow":
                instance.status = "completed"
                instance.updated_at = now
                await _save_instance(instance)
                event_log.record(instance.workflow_uuid, "workflow_completed")
                return
            instance.updated_at = now
            await _save_instance(instance)
            await _advance_workflow(instance)
            return
        if event.event == "fail":
            instance.pending_hook_event = None
            instance.status = "failed"
            instance.updated_at = now
            await _save_instance(instance)
            return
        return

    if event.phase_number is None or event.phase_number >= len(instance.phases):
        return
    phase = instance.phases[event.phase_number]

    if event.step_name is None:
        if event.event == "pass":
            phase.pending_hook_event = None
            phase.status = "failed"
            instance.status = "failed"
            instance.updated_at = now
            await _save_instance(instance)
            return
        if hook_event_name and phase.pending_hook_event != hook_event_name:
            return
        if event.event == "done":
            phase.pending_hook_event = None
            if hook_event_name == "post_phase":
                phase.phase_iteration += 1
                if _phase_is_complete(phase):
                    phase.status = "completed"
                    phase.iteration_should_restart = False
                    instance.current_phase = phase.number + 1
                else:
                    _reset_phase_for_next_iteration(phase)
            instance.updated_at = now
            await _save_instance(instance)
            await _advance_workflow(instance)
            return
        if event.event == "fail":
            phase.pending_hook_event = None
            phase.status = "failed"
            instance.status = "failed"
            instance.updated_at = now
            await _save_instance(instance)
            return
        return

    target = next((step for step in phase.steps if step.name == event.step_name), None)
    if target is None:
        return
    if hook_event_name and target.pending_hook_event and target.pending_hook_event != hook_event_name:
        return

    if event.event == "start":
        target.status = "running"
        target.detail = event.detail
        _record_step_session(instance, target, session_name)
    elif event.event in {"done", "pass"}:
        completed_hook = hook_event_name or target.pending_hook_event
        target.pending_hook_event = None
        if event.detail:
            target.detail = event.detail
        _record_step_session(instance, target, session_name)
        if completed_hook == "pre_step":
            await _launch_step_hook(instance, phase, target, "step")
            target.status = "dispatched"
        elif completed_hook == "step":
            if _has_hooks(instance, "post_step"):
                await _launch_step_hook(instance, phase, target, "post_step")
            else:
                raise RuntimeError(
                    f"Workflow {instance.workflow_name!r} step {target.name!r} cannot complete without a post_step hook."
                )
        elif completed_hook == "post_step":
            if target.status != "failed":
                target.status = "pass" if event.event == "pass" else "completed"
            _record_step_completion(target, now)
        else:
            target.status = "pass" if event.event == "pass" else "completed"
            _record_step_completion(target, now)
        if phase.completionMode == "allPass" and phase.type == "ExecSerial" and target.status == "completed":
            phase.iteration_should_restart = True
    elif event.event == "fail":
        completed_hook = hook_event_name or target.pending_hook_event
        target.pending_hook_event = None
        target.detail = event.detail
        _record_step_session(instance, target, session_name)
        if completed_hook == "step" and instance.post_step_on_fail and _has_hooks(instance, "post_step"):
            target.status = "failed"
            _record_step_completion(target, now)
            await _launch_step_hook(instance, phase, target, "post_step")
        else:
            target.status = "failed"
            _record_step_completion(target, now)
            instance.status = "failed"
    elif event.event == "rfi":
        target.status = "rfi"
        target.detail = event.detail
        _record_step_session(instance, target, session_name)
    elif event.event == "progress":
        target.detail = event.detail
        _record_step_session(instance, target, session_name)

    _recompute_phase_statuses(instance)
    if any(item.status == "failed" for item in instance.phases):
        instance.status = "failed"
    instance.updated_at = now
    await _save_instance(instance)
    if instance.status == "running":
        await _advance_workflow(instance)


async def check_timeouts() -> None:
    redis = await get_redis()
    ids = await redis.smembers("workflows")
    now = datetime.now(timezone.utc)
    for workflow_uuid in ids:
        instance = await get_workflow_instance(workflow_uuid)
        if instance is None or instance.status != "running" or instance.current_phase >= len(instance.phases):
            continue
        phase = instance.phases[instance.current_phase]
        for step in phase.steps:
            if step.status not in LIVE_STEP_STATUSES or not step.started_ats:
                continue
            started_at = datetime.fromisoformat(step.started_ats[-1])
            elapsed = (now - started_at).total_seconds()
            timeout_seconds = step.timeout_seconds or settings.process_timeout_seconds
            if elapsed <= timeout_seconds:
                continue
            step.detail = {"reason": "timeout", "elapsed_seconds": int(elapsed)}
            await _launch_step_hook(instance, phase, step, "on_step_timeout")
            event_log.record(
                instance.workflow_uuid,
                "step_timeout",
                phase_number=phase.number,
                step_name=step.name,
                detail=step.detail,
            )
        _recompute_phase_statuses(instance)
        instance.updated_at = _now()
        await _save_instance(instance)


async def read_workflow_log(workflow_uuid: str) -> str | None:
    instance = await get_workflow_instance(workflow_uuid)
    if instance is None:
        return None
    log_path = workflow_log_path(workflow_uuid)
    if not log_path.exists():
        return ""
    return log_path.read_text()
