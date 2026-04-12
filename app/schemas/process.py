from typing import Literal

from pydantic import BaseModel, Field, field_validator


HookFailurePolicy = Literal["fail", "warn_and_continue"]
PhaseType = Literal["ExecParallel", "ExecSerial"]
CompletionMode = Literal["execCount", "allPass"]
HookEventName = Literal[
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
]

HOOK_EVENT_NAMES: tuple[HookEventName, ...] = (
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
)

NotificationEventName = Literal["start", "done", "pass", "fail", "rfi", "progress"]
ProcessStatus = Literal["pending", "running", "paused", "completed", "failed"]
PhaseStatusName = Literal["pending", "running", "completed", "failed"]
StepStatusName = Literal["pending", "dispatched", "running", "completed", "pass", "failed", "rfi"]


class StepRuntimeDetails(BaseModel):
    name: str = Field(
        description=(
            "Step/skill name. Together with workflow_uuid and phase_number, this deterministically "
            "defines the tmux session id for the running step."
        )
    )
    config: dict = Field(default_factory=dict)
    model: str | None = None
    executor_label: str | None = None
    timeout_seconds: int | None = None
    user_overrides: dict = Field(default_factory=dict)


class WorkflowStateDict(BaseModel):
    workflow_uuid: str = Field(
        description=(
            "Workflow instance id for the running process. For step-scoped hooks, this is one part of "
            "the deterministic tmux session id contract: <workflow_uuid>-p<phase_number>-<slugified_step_name>."
        )
    )
    hook_event_name: HookEventName
    common_volume_root: str = Field(
        description=(
            "Resolved common-volume root for the current runtime environment. Hooks should use this value "
            "instead of assuming a fixed host or container path."
        )
    )
    orchestrator_url: str = Field(
        description="Resolved orchestrator base URL for the current runtime environment."
    )
    tmuxer_url: str = Field(
        description="Resolved tmuxer base URL for the current runtime environment."
    )
    interaction_service_url: str = Field(
        description="Resolved interaction-service base URL for the current runtime environment."
    )
    secrets_service_url: str = Field(
        description="Resolved secrets-service base URL for the current runtime environment."
    )
    pm_system_url: str = Field(
        description="Resolved PM-system base URL for the current runtime environment."
    )
    current_session_name: str | None = None
    project_identities_associated: list[str] = Field(default_factory=list)
    project_environment_variables_associated: list[str] = Field(default_factory=list)
    additional_caller_info: dict = Field(default_factory=dict)
    workflow_definition: dict = Field(
        default_factory=dict,
        description="Debug/included-expanded-context field. Make this toggleable later.",
    )
    phase_number: int | None = Field(
        default=None,
        description=(
            "Zero-based phase number for phase/step-scoped hooks. For step-scoped hooks, this is one part of "
            "the deterministic tmux session id contract: <workflow_uuid>-p<phase_number>-<slugified_step_name>."
        ),
    )
    phase_iteration: int | None = Field(
        default=None,
        description="Zero-based iteration counter for the current phase run.",
    )
    step_details: StepRuntimeDetails | None = None


class NotificationEvent(BaseModel):
    workflow_uuid: str = Field(
        description="Workflow instance id for the running process."
    )
    phase_number: int | None = Field(
        default=None,
        description="Zero-based phase number for phase/step-scoped notifications.",
    )
    step_name: str | None = Field(
        default=None,
        description=(
            "Step/skill name for step-scoped notifications. Together with workflow_uuid and phase_number, "
            "this identifies the deterministic tmux session id used by the step."
        ),
    )
    event: NotificationEventName
    detail: dict | None = None
    timestamp: str | None = None


class WorkflowHookEntry(BaseModel):
    asset_name: str
    failure_policy: HookFailurePolicy = "fail"


class WorkflowHookMap(BaseModel):
    pre_workflow: list[WorkflowHookEntry] = Field(default_factory=list)
    post_workflow: list[WorkflowHookEntry] = Field(default_factory=list)
    pre_phase: list[WorkflowHookEntry] = Field(default_factory=list)
    post_phase: list[WorkflowHookEntry] = Field(default_factory=list)
    pre_step: list[WorkflowHookEntry] = Field(default_factory=list)
    step: list[WorkflowHookEntry] = Field(default_factory=list)
    post_step: list[WorkflowHookEntry] = Field(default_factory=list)
    on_workflow_pause: list[WorkflowHookEntry] = Field(default_factory=list)
    on_workflow_continue: list[WorkflowHookEntry] = Field(default_factory=list)
    on_step_timeout: list[WorkflowHookEntry] = Field(default_factory=list)
    on_step_user_kill: list[WorkflowHookEntry] = Field(default_factory=list)


class StepStatus(BaseModel):
    name: str
    config: dict = Field(default_factory=dict)
    model: str | None = None
    executor_label: str | None = None
    timeout_seconds: int | None = None
    user_overrides: dict = Field(default_factory=dict)
    status: StepStatusName = "pending"
    tmux_sessions: list[str] = Field(
        default_factory=list,
        description=(
            "Recorded tmux session ids for this step. The canonical step session id is derived as "
            "<workflow_uuid>-p<phase_number>-<slugified_step_name>."
        ),
    )
    started_ats: list[str] = Field(default_factory=list)
    completed_ats: list[str] = Field(default_factory=list)
    detail: dict | None = None
    pending_hook_event: HookEventName | None = None


class PhaseStatus(BaseModel):
    number: int
    type: PhaseType = "ExecParallel"
    completionMode: CompletionMode = "execCount"
    maxTimes: int = 1
    phase_iteration: int = 0
    steps: list[StepStatus] = Field(default_factory=list)
    status: PhaseStatusName = "pending"
    pending_hook_event: HookEventName | None = None
    iteration_should_restart: bool = False

    @field_validator("maxTimes")
    @classmethod
    def validate_max_times(cls, value: int) -> int:
        if value < 1:
            raise ValueError("maxTimes must be at least 1.")
        return value


class WorkflowInstanceCreate(BaseModel):
    task_id: str | None = None
    workflow_name: str
    project_name: str
    project_base_repo_path_relative_to_common_volume: str
    project_identities_associated: list[str] = Field(default_factory=list)
    project_environment_variables_associated: list[str] = Field(default_factory=list)
    additional_caller_info: dict = Field(default_factory=dict)
    step_configs: dict[int, dict[str, dict]] = Field(default_factory=dict)
    post_step_on_fail: bool = False


class WorkflowInstanceCreateById(BaseModel):
    task_id: str | None = None
    workflow_def_id: str
    project_name: str
    project_base_repo_path_relative_to_common_volume: str
    project_identities_associated: list[str] = Field(default_factory=list)
    project_environment_variables_associated: list[str] = Field(default_factory=list)
    additional_caller_info: dict = Field(default_factory=dict)
    step_configs: dict[int, dict[str, dict]] = Field(default_factory=dict)
    post_step_on_fail: bool = False


class WorkflowInstanceRead(BaseModel):
    workflow_uuid: str
    workflow_def_id: str
    task_id: str | None = None
    workflow_name: str
    workflow_definition: dict = Field(default_factory=dict)
    project_name: str
    project_base_repo_path_relative_to_common_volume: str
    project_identities_associated: list[str] = Field(default_factory=list)
    project_environment_variables_associated: list[str] = Field(default_factory=list)
    current_session_name: str | None = None
    additional_caller_info: dict = Field(default_factory=dict)
    status: ProcessStatus = "pending"
    current_phase: int = 0
    phases: list[PhaseStatus] = Field(default_factory=list)
    hooks: WorkflowHookMap = Field(default_factory=WorkflowHookMap)
    pending_messages: list[str] = Field(default_factory=list)
    post_step_on_fail: bool = False
    pending_hook_event: HookEventName | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WorkflowInstanceSummary(BaseModel):
    workflow_uuid: str
    workflow_def_id: str
    task_id: str | None = None
    workflow_name: str
    project_name: str
    status: ProcessStatus
    current_phase: int
    total_phases: int
    current_session_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WorkflowStepTarget(BaseModel):
    phase_number: int
    step_name: str


class WorkflowStepConfigUpdate(WorkflowStepTarget):
    config: dict = Field(default_factory=dict)
    model: str | None = None


class WorkflowPhaseInsert(BaseModel):
    insert_index: int


class WorkflowStepMove(BaseModel):
    from_phase_number: int
    to_phase_number: int
    step_name: str


class WorkflowStepInsert(BaseModel):
    phase_number: int
    step_name: str
    config: dict = Field(default_factory=dict)
    model: str | None = None
    executor_label: str | None = None
    timeout_seconds: int | None = None
    user_overrides: dict = Field(default_factory=dict)
