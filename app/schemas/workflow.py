from pydantic import BaseModel, Field, field_validator

from .process import CompletionMode, HookFailurePolicy, PhaseType


class WorkflowHookEntry(BaseModel):
    asset_name: str
    failure_policy: HookFailurePolicy = "fail"


class WorkflowHooks(BaseModel):
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

    @field_validator("*")
    @classmethod
    def validate_no_duplicate_assets_per_scope(cls, entries: list[WorkflowHookEntry]) -> list[WorkflowHookEntry]:
        seen: set[str] = set()
        for entry in entries:
            if entry.asset_name in seen:
                raise ValueError(f"Duplicate hook asset in same scope: {entry.asset_name}")
            seen.add(entry.asset_name)
        return entries


class WorkflowSummary(BaseModel):
    workflow_def_id: str
    name: str
    description: str = ""


class WorkflowPhaseDefinition(BaseModel):
    type: PhaseType = "ExecParallel"
    completionMode: CompletionMode = "execCount"
    maxTimes: int = 1
    steps: list[str] = Field(default_factory=list)

    @field_validator("maxTimes")
    @classmethod
    def validate_max_times(cls, value: int) -> int:
        if value < 1:
            raise ValueError("maxTimes must be at least 1.")
        return value

    @field_validator("steps")
    @classmethod
    def validate_unique_step_names(cls, steps: list[str]) -> list[str]:
        seen: set[str] = set()
        for step_name in steps:
            if step_name in seen:
                raise ValueError(f"Duplicate step name in phase: {step_name}")
            seen.add(step_name)
        return steps


class WorkflowDetail(BaseModel):
    workflow_def_id: str
    name: str
    description: str = ""
    phases: list[WorkflowPhaseDefinition] = Field(default_factory=list)
    hooks: WorkflowHooks = Field(default_factory=WorkflowHooks)


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    phases: list[WorkflowPhaseDefinition] = Field(default_factory=list)
    hooks: WorkflowHooks = Field(default_factory=WorkflowHooks)


class WorkflowUpdate(BaseModel):
    description: str | None = None
    phases: list[WorkflowPhaseDefinition] | None = None
    hooks: WorkflowHooks | None = None
