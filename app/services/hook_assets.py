from pathlib import Path

from ..config import settings
from ..schemas.hook import HookDetail, HookSummary
from . import git


def _root() -> Path:
    git.ensure_repo(settings.hooks_path)
    return settings.hooks_path


def _hook_file(name: str) -> Path:
    return _root() / (name if name.endswith(".py") or name.endswith(".sh") else f"{name}.py")


def _normalized_content(content: str) -> str:
    if not content:
        return ""
    return content if content.endswith("\n") else content + "\n"


def list_hooks() -> list[HookSummary]:
    root = _root()
    files = sorted(list(root.glob("*.py")) + list(root.glob("*.sh")))
    return [HookSummary(name=path.stem) for path in files]


def get_hook(name: str) -> HookDetail:
    path = _hook_file(name)
    if not path.is_file():
        raise FileNotFoundError(f"Hook asset not found: {name}")
    return HookDetail(name=path.stem, content=path.read_text())


def create_hook(name: str, content: str = "") -> HookDetail:
    path = _hook_file(name)
    if path.exists():
        raise FileExistsError(f"Hook asset already exists: {name}")
    path.write_text(_normalized_content(content))
    git.add_and_commit([path.name], f"Create hook asset: {path.stem}", cwd=_root())
    return HookDetail(name=path.stem, content=path.read_text())


def update_hook(name: str, content: str) -> HookDetail:
    path = _hook_file(name)
    if not path.is_file():
        raise FileNotFoundError(f"Hook asset not found: {name}")
    path.write_text(_normalized_content(content))
    git.add_and_commit([path.name], f"Update hook asset: {path.stem}", cwd=_root())
    return HookDetail(name=path.stem, content=path.read_text())


def delete_hook(name: str) -> None:
    path = _hook_file(name)
    if not path.is_file():
        raise FileNotFoundError(f"Hook asset not found: {name}")
    path.unlink()
    git.add_and_commit([path.name], f"Delete hook asset: {path.stem}", cwd=_root())
