from pathlib import Path

from ..config import settings
from ..schemas.process import HookEventName, StepRuntimeDetails, WorkflowStateDict


def ensure_runtime_roots() -> None:
    settings.hook_fires_path.mkdir(parents=True, exist_ok=True)


def build_hook_fire_path(
    workflow_uuid: str,
    hook_event_name: HookEventName,
    phase_number: int | None = None,
    step_name: str | None = None,
) -> Path:
    root = settings.hook_fires_path / workflow_uuid

    if hook_event_name in {"pre_workflow", "post_workflow", "on_workflow_pause", "on_workflow_continue"}:
        return root / hook_event_name

    if phase_number is None:
        return root / hook_event_name

    phase_root = root / "phases" / f"phase-{phase_number}"

    if hook_event_name in {"pre_phase", "post_phase"}:
        return phase_root / hook_event_name

    if step_name:
        return phase_root / step_name / hook_event_name

    return phase_root / hook_event_name


def build_state_dict(
    workflow_uuid: str,
    hook_event_name: HookEventName,
    current_session_name: str | None,
    project_identities_associated: list[str],
    project_environment_variables_associated: list[str],
    additional_caller_info: dict,
    workflow_definition: dict,
    phase_number: int | None = None,
    phase_iteration: int | None = None,
    step_details: StepRuntimeDetails | None = None,
) -> WorkflowStateDict:
    caller_info = dict(additional_caller_info or {})
    if step_details is not None:
        caller_info["selected_agent"] = step_details.executor_label or ""
        caller_info["selected_model"] = step_details.model or ""

    return WorkflowStateDict(
        workflow_uuid=workflow_uuid,
        hook_event_name=hook_event_name,
        common_volume_root=str(settings.common_volume_root),
        orchestrator_url=settings.orchestrator_url,
        tmuxer_url=settings.tmuxer_url,
        interaction_service_url=settings.interaction_service_url,
        secrets_service_url=settings.secrets_service_url,
        current_session_name=current_session_name,
        project_identities_associated=project_identities_associated,
        project_environment_variables_associated=project_environment_variables_associated,
        additional_caller_info=caller_info,
        workflow_definition=workflow_definition,
        phase_number=phase_number,
        phase_iteration=phase_iteration,
        step_details=step_details,
    )


def state_dict_path(
    workflow_uuid: str,
    hook_event_name: HookEventName,
    phase_number: int | None = None,
    step_name: str | None = None,
) -> Path:
    return build_hook_fire_path(
        workflow_uuid=workflow_uuid,
        hook_event_name=hook_event_name,
        phase_number=phase_number,
        step_name=step_name,
    ) / "state.json"


def workflow_log_path(workflow_uuid: str) -> Path:
    return settings.hook_fires_path / workflow_uuid / "logs.log"
