import json
import shutil
from pathlib import Path

from ..config import settings
from ..schemas.process import HookEventName, StepRuntimeDetails, WorkflowHookEntry, WorkflowInstanceRead
from .execution import launch_script_in_tmux
from .runtime import build_hook_fire_path, build_state_dict, workflow_log_path


def hook_asset_path(asset_name: str) -> Path:
    if asset_name.endswith(".py") or asset_name.endswith(".sh"):
        return settings.hooks_path / asset_name
    py_path = settings.hooks_path / f"{asset_name}.py"
    sh_path = settings.hooks_path / f"{asset_name}.sh"
    if py_path.exists():
        return py_path
    if sh_path.exists():
        return sh_path
    return py_path


def materialize_hook_fire(
    instance: WorkflowInstanceRead,
    hook_event_name: HookEventName,
    hook: WorkflowHookEntry,
    phase_number: int | None = None,
    phase_iteration: int | None = None,
    step: StepRuntimeDetails | None = None,
) -> tuple[Path, Path]:
    fire_root = build_hook_fire_path(
        workflow_uuid=instance.workflow_uuid,
        hook_event_name=hook_event_name,
        phase_number=phase_number,
        step_name=step.name if step else None,
    )
    fire_root.mkdir(parents=True, exist_ok=True)
    state = build_state_dict(
        workflow_uuid=instance.workflow_uuid,
        hook_event_name=hook_event_name,
        current_session_name=instance.current_session_name,
        project_identities_associated=instance.project_identities_associated,
        project_environment_variables_associated=instance.project_environment_variables_associated,
        additional_caller_info=instance.additional_caller_info,
        workflow_definition=instance.workflow_definition,
        phase_number=phase_number,
        phase_iteration=phase_iteration,
        step_details=step,
    )
    state_path = fire_root / "state.json"
    state_path.write_text(json.dumps(state.model_dump(), indent=2) + "\n")

    asset_source = hook_asset_path(hook.asset_name)
    if not asset_source.is_file():
        raise FileNotFoundError(f"Hook asset not found: {hook.asset_name}")
    asset_target = fire_root / asset_source.name
    shutil.copy2(asset_source, asset_target)
    return fire_root, asset_target


def fire_hook(
    instance: WorkflowInstanceRead,
    hook_event_name: HookEventName,
    hook: WorkflowHookEntry,
    phase_number: int | None = None,
    phase_iteration: int | None = None,
    step: StepRuntimeDetails | None = None,
) -> str:
    fire_root, script_path = materialize_hook_fire(
        instance,
        hook_event_name,
        hook,
        phase_number=phase_number,
        phase_iteration=phase_iteration,
        step=step,
    )
    return launch_script_in_tmux(script_path, fire_root, workflow_log_path(instance.workflow_uuid))
