from __future__ import annotations

import pytest

from new_orchestrator.app.schemas.process import (
    NotificationEvent,
    PhaseStatus,
    StepStatus,
    WorkflowHookEntry,
    WorkflowHookMap,
    WorkflowInstanceRead,
    WorkflowStepTarget,
)
from new_orchestrator.app.services import processes


@pytest.mark.asyncio
async def test_step_done_launches_post_step_without_killing_session(monkeypatch):
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-notify-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[
            PhaseStatus(
                number=0,
                status="running",
                steps=[
                    StepStatus(
                        name="dummy",
                        status="running",
                        pending_hook_event="step",
                    )
                ],
            )
        ],
        hooks=WorkflowHookMap(
            post_step=[WorkflowHookEntry(asset_name="scryer-post-step", failure_policy="fail")]
        ),
    )

    launched: list[tuple[int, str, str]] = []
    saved_statuses: list[str] = []

    async def fake_get_workflow_instance(workflow_uuid: str):
        assert workflow_uuid == "wf-notify-123"
        return instance

    async def fake_save_instance(saved_instance):
        saved_statuses.append(saved_instance.phases[0].steps[0].status)

    async def fake_advance_workflow(saved_instance):
        return None

    async def fake_launch_step_hook(saved_instance, phase, step, hook_event_name):
        launched.append((phase.number, step.name, hook_event_name))
        step.pending_hook_event = hook_event_name
        return True

    monkeypatch.setattr(processes, "get_workflow_instance", fake_get_workflow_instance)
    monkeypatch.setattr(processes, "_save_instance", fake_save_instance)
    monkeypatch.setattr(processes, "_advance_workflow", fake_advance_workflow)
    monkeypatch.setattr(processes, "_launch_step_hook", fake_launch_step_hook)
    monkeypatch.setattr(processes.event_log, "record", lambda *args, **kwargs: None)

    await processes.handle_notification(
        NotificationEvent(
            workflow_uuid="wf-notify-123",
            phase_number=0,
            step_name="dummy",
            event="done",
            detail={
                "hook_event_name": "step",
                "session_name": "wf-notify-123-p0-dummy",
            },
        )
    )

    assert launched == [(0, "dummy", "post_step")]
    assert instance.phases[0].steps[0].status in {"running", "dispatched"}
    assert instance.phases[0].steps[0].pending_hook_event == "post_step"
    assert instance.phases[0].steps[0].tmux_sessions == ["wf-notify-123-p0-dummy"]
    assert saved_statuses


@pytest.mark.asyncio
async def test_kill_step_dispatches_user_kill_hook_without_direct_failure(monkeypatch):
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-kill-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[
            PhaseStatus(
                number=0,
                status="running",
                steps=[StepStatus(name="dummy", status="running")],
            )
        ],
        hooks=WorkflowHookMap(
            on_step_user_kill=[WorkflowHookEntry(asset_name="scryer-step-fail", failure_policy="fail")]
        ),
    )

    launched: list[tuple[int, str, str]] = []

    async def fake_get_workflow_instance(workflow_uuid: str):
        return instance

    async def fake_launch_step_hook(saved_instance, phase, step, hook_event_name):
        launched.append((phase.number, step.name, hook_event_name))
        step.pending_hook_event = hook_event_name
        return True

    async def fake_save_instance(saved_instance):
        return None

    monkeypatch.setattr(processes, "get_workflow_instance", fake_get_workflow_instance)
    monkeypatch.setattr(processes, "_launch_step_hook", fake_launch_step_hook)
    monkeypatch.setattr(processes, "_save_instance", fake_save_instance)

    await processes.kill_step("wf-kill-123", WorkflowStepTarget(phase_number=0, step_name="dummy"))

    assert launched == [(0, "dummy", "on_step_user_kill")]
    assert instance.phases[0].steps[0].status == "running"
    assert instance.phases[0].steps[0].pending_hook_event == "on_step_user_kill"
    assert instance.status == "running"


@pytest.mark.asyncio
async def test_check_timeouts_dispatches_timeout_hook_without_direct_failure(monkeypatch):
    step = StepStatus(
        name="dummy",
        status="running",
        started_ats=["2000-01-01T00:00:00+00:00"],
        timeout_seconds=1,
    )
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-timeout-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[PhaseStatus(number=0, status="running", steps=[step])],
        hooks=WorkflowHookMap(
            on_step_timeout=[WorkflowHookEntry(asset_name="scryer-step-fail", failure_policy="fail")]
        ),
    )

    launched: list[tuple[int, str, str]] = []

    class FakeRedis:
        async def smembers(self, key: str):
            assert key == "workflows"
            return {"wf-timeout-123"}

    async def fake_get_workflow_instance(workflow_uuid: str):
        return instance

    async def fake_launch_step_hook(saved_instance, phase, target, hook_event_name):
        launched.append((phase.number, target.name, hook_event_name))
        target.pending_hook_event = hook_event_name
        return True

    async def fake_save_instance(saved_instance):
        return None

    async def fake_get_redis():
        return FakeRedis()

    monkeypatch.setattr(processes, "get_redis", fake_get_redis)
    monkeypatch.setattr(processes, "get_workflow_instance", fake_get_workflow_instance)
    monkeypatch.setattr(processes, "_launch_step_hook", fake_launch_step_hook)
    monkeypatch.setattr(processes, "_save_instance", fake_save_instance)
    monkeypatch.setattr(processes.event_log, "record", lambda *args, **kwargs: None)

    await processes.check_timeouts()

    assert launched == [(0, "dummy", "on_step_timeout")]
    assert step.status == "running"
    assert step.pending_hook_event == "on_step_timeout"
    assert step.detail is not None
    assert step.detail["reason"] == "timeout"
    assert step.detail["elapsed_seconds"] > 0
    assert instance.status == "running"


@pytest.mark.asyncio
async def test_step_pass_is_stored_as_pass_status(monkeypatch):
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-pass-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[
            PhaseStatus(
                number=0,
                status="running",
                steps=[
                    StepStatus(
                        name="dummy",
                        status="running",
                        pending_hook_event="post_step",
                    )
                ],
            )
        ],
        hooks=WorkflowHookMap(),
    )

    async def fake_get_workflow_instance(workflow_uuid: str):
        return instance

    async def fake_save_instance(saved_instance):
        return None

    async def fake_advance_workflow(saved_instance):
        return None

    monkeypatch.setattr(processes, "get_workflow_instance", fake_get_workflow_instance)
    monkeypatch.setattr(processes, "_save_instance", fake_save_instance)
    monkeypatch.setattr(processes, "_advance_workflow", fake_advance_workflow)
    monkeypatch.setattr(processes.event_log, "record", lambda *args, **kwargs: None)

    await processes.handle_notification(
        NotificationEvent(
            workflow_uuid="wf-pass-123",
            phase_number=0,
            step_name="dummy",
            event="pass",
            detail={"hook_event_name": "post_step"},
        )
    )

    assert instance.phases[0].steps[0].status == "pass"
    assert len(instance.phases[0].steps[0].completed_ats) == 1


@pytest.mark.asyncio
async def test_workflow_scoped_pass_fails_workflow(monkeypatch):
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-invalid-pass-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[PhaseStatus(number=0, status="pending", steps=[StepStatus(name="dummy", status="pending")])],
        hooks=WorkflowHookMap(),
    )

    async def fake_get_workflow_instance(workflow_uuid: str):
        return instance

    async def fake_save_instance(saved_instance):
        return None

    monkeypatch.setattr(processes, "get_workflow_instance", fake_get_workflow_instance)
    monkeypatch.setattr(processes, "_save_instance", fake_save_instance)
    monkeypatch.setattr(processes.event_log, "record", lambda *args, **kwargs: None)

    await processes.handle_notification(
        NotificationEvent(
            workflow_uuid="wf-invalid-pass-123",
            event="pass",
            detail={"hook_event_name": "pre_workflow"},
        )
    )

    assert instance.status == "failed"
