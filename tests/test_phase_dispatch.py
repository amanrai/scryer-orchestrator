from __future__ import annotations

import pytest

from new_orchestrator.app.schemas.process import NotificationEvent, PhaseStatus, StepStatus, WorkflowHookMap, WorkflowInstanceRead
from new_orchestrator.app.services import processes


@pytest.mark.asyncio
async def test_launch_phase_steps_dispatches_all_pending_steps(monkeypatch):
    phase = PhaseStatus(
        number=0,
        status="running",
        steps=[
            StepStatus(name="alpha", status="pending"),
            StepStatus(name="beta", status="pending"),
            StepStatus(name="gamma", status="pending"),
        ],
    )
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-phase-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[phase],
        hooks=WorkflowHookMap(),
    )

    launched: list[str] = []

    async def fake_launch_step_pipeline(saved_instance, saved_phase, step):
        assert saved_instance is instance
        assert saved_phase is phase
        launched.append(step.name)
        step.status = "dispatched"

    monkeypatch.setattr(processes, "_launch_step_pipeline", fake_launch_step_pipeline)

    await processes._launch_phase_steps(instance, phase)

    assert launched == ["alpha", "beta", "gamma"]
    assert [step.status for step in phase.steps] == ["dispatched", "dispatched", "dispatched"]


@pytest.mark.asyncio
async def test_launch_phase_steps_dispatches_only_first_pending_step_for_exec_serial(monkeypatch):
    phase = PhaseStatus(
        number=0,
        type="ExecSerial",
        status="running",
        steps=[
            StepStatus(name="alpha", status="pending"),
            StepStatus(name="beta", status="pending"),
            StepStatus(name="gamma", status="pending"),
        ],
    )
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-phase-serial-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[phase],
        hooks=WorkflowHookMap(),
    )

    launched: list[str] = []

    async def fake_launch_step_pipeline(saved_instance, saved_phase, step):
        assert saved_instance is instance
        assert saved_phase is phase
        launched.append(step.name)
        step.status = "dispatched"

    monkeypatch.setattr(processes, "_launch_step_pipeline", fake_launch_step_pipeline)

    await processes._launch_phase_steps(instance, phase)

    assert launched == ["alpha"]
    assert [step.status for step in phase.steps] == ["dispatched", "pending", "pending"]


@pytest.mark.asyncio
async def test_advance_workflow_requires_pre_phase_hook(monkeypatch):
    phase = PhaseStatus(number=0, status="pending", steps=[StepStatus(name="alpha", status="pending")])
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-phase-contract-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[phase],
        hooks=WorkflowHookMap(),
    )

    monkeypatch.setattr(processes, "_save_instance", lambda saved_instance: None)

    with pytest.raises(RuntimeError, match="pre_phase hook"):
        await processes._advance_workflow(instance)


@pytest.mark.asyncio
async def test_post_phase_done_restarts_exec_count_iteration_until_max_times(monkeypatch):
    phase = PhaseStatus(
        number=0,
        completionMode="execCount",
        maxTimes=2,
        phase_iteration=0,
        status="running",
        pending_hook_event="post_phase",
        steps=[
            StepStatus(
                name="alpha",
                status="completed",
                started_ats=["2026-04-04T00:00:00+00:00"],
                completed_ats=["2026-04-04T00:01:00+00:00"],
                tmux_sessions=["wf-phase-repeat-p0-alpha"],
                detail={"note": "complete"},
            )
        ],
    )
    instance = WorkflowInstanceRead(
        workflow_uuid="wf-phase-repeat-123",
        workflow_name="dummy workflow",
        project_name="scryer testing",
        project_base_repo_path_relative_to_common_volume="",
        status="running",
        current_phase=0,
        phases=[phase],
        hooks=WorkflowHookMap(),
    )

    saved_iterations: list[int] = []
    advanced: list[int] = []

    async def fake_get_workflow_instance(workflow_uuid: str):
        return instance

    async def fake_save_instance(saved_instance):
        saved_iterations.append(saved_instance.phases[0].phase_iteration)

    async def fake_advance_workflow(saved_instance):
        advanced.append(saved_instance.phases[0].phase_iteration)

    monkeypatch.setattr(processes, "get_workflow_instance", fake_get_workflow_instance)
    monkeypatch.setattr(processes, "_save_instance", fake_save_instance)
    monkeypatch.setattr(processes, "_advance_workflow", fake_advance_workflow)
    monkeypatch.setattr(processes.event_log, "record", lambda *args, **kwargs: None)

    await processes.handle_notification(
        NotificationEvent(
            workflow_uuid="wf-phase-repeat-123",
            phase_number=0,
            event="done",
            detail={"hook_event_name": "post_phase"},
        )
    )

    assert phase.phase_iteration == 1
    assert phase.status == "pending"
    assert phase.pending_hook_event is None
    assert phase.steps[0].status == "pending"
    assert phase.steps[0].started_ats == ["2026-04-04T00:00:00+00:00"]
    assert phase.steps[0].completed_ats == ["2026-04-04T00:01:00+00:00"]
    assert phase.steps[0].tmux_sessions == []
    assert phase.steps[0].detail is None
    assert saved_iterations == [1]
    assert advanced == [1]
