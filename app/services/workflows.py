import json
from pathlib import Path

from ..config import settings
from ..schemas.workflow import WorkflowDetail, WorkflowHooks, WorkflowPhaseDefinition, WorkflowSummary
from . import git
from .errors import WorkflowAlreadyExistsError, WorkflowNotFoundError


def _root() -> Path:
    git.ensure_repo(settings.workflows_path)
    return settings.workflows_path


def _workflow_file(name: str) -> Path:
    return _root() / f"{name}.json"


def _read_workflow(path: Path) -> WorkflowDetail:
    data = json.loads(path.read_text())
    data.setdefault("hooks", {})
    return WorkflowDetail(**data)


def list_workflows() -> list[WorkflowSummary]:
    root = _root()
    results = []
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text())
        results.append(
            WorkflowSummary(
                name=data["name"],
                description=data.get("description", ""),
            )
        )
    return results


def get_workflow(name: str) -> WorkflowDetail:
    path = _workflow_file(name)
    if not path.is_file():
        raise WorkflowNotFoundError(name)
    return _read_workflow(path)


def create_workflow(
    name: str,
    description: str = "",
    phases: list[WorkflowPhaseDefinition] | None = None,
    hooks: WorkflowHooks | None = None,
) -> WorkflowDetail:
    path = _workflow_file(name)
    if path.exists():
        raise WorkflowAlreadyExistsError(name)
    data = {
        "name": name,
        "description": description,
        "phases": [phase.model_dump() for phase in (phases or [])],
        "hooks": (hooks or WorkflowHooks()).model_dump(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
    git.add_and_commit([path.name], f"Create workflow: {name}", cwd=_root())
    return _read_workflow(path)


def update_workflow(
    name: str,
    description: str | None = None,
    phases: list[WorkflowPhaseDefinition] | None = None,
    hooks: WorkflowHooks | None = None,
) -> WorkflowDetail:
    path = _workflow_file(name)
    if not path.is_file():
        raise WorkflowNotFoundError(name)
    data = json.loads(path.read_text())
    if description is not None:
        data["description"] = description
    if phases is not None:
        data["phases"] = [phase.model_dump() for phase in phases]
    if hooks is not None:
        data["hooks"] = hooks.model_dump()
    path.write_text(json.dumps(data, indent=2) + "\n")
    git.add_and_commit([path.name], f"Update workflow: {name}", cwd=_root())
    return _read_workflow(path)
