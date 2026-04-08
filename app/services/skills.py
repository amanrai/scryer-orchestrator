import shutil
from pathlib import Path

import yaml

from ..config import settings
from ..schemas.skill import FileContent, FileVersions, SkillDetail, SkillMeta, SkillSummary
from . import git
from .errors import FileNotFoundInSkillError, SkillAlreadyExistsError, SkillNotFoundError
from .paths import safe_resolve

SKILL_FILE = "SKILL.md"
FRONTMATTER_SEP = "---"


def _root() -> Path:
    root = settings.skills_path
    git.ensure_repo(root)
    return root


def _roots() -> list[Path]:
    roots: list[Path] = []
    for root in settings.skills_paths:
        git.ensure_repo(root)
        roots.append(root)
    return roots


def _listable_skill_dir(skill_dir: Path) -> bool:
    return skill_dir.is_dir() and not skill_dir.name.startswith(".") and (skill_dir / SKILL_FILE).is_file()


def _skill_dir(name: str) -> Path:
    for root in _roots():
        skill_dir = safe_resolve(root, name)
        if skill_dir.is_dir():
            return skill_dir
    return safe_resolve(_root(), name)


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith(FRONTMATTER_SEP):
        return {}
    rest = text[len(FRONTMATTER_SEP) :]
    end = rest.find(f"\n{FRONTMATTER_SEP}")
    if end == -1:
        return {}
    block = rest[:end]
    return yaml.safe_load(block) or {}


def _meta_from_dir(skill_dir: Path) -> SkillMeta:
    skill_file = skill_dir / SKILL_FILE
    fm = _parse_frontmatter(skill_file.read_text()) if skill_file.exists() else {}
    return SkillMeta(
        name=fm.get("name", skill_dir.name),
        description=fm.get("description", ""),
        argument_hint=fm.get("argument-hint", ""),
        allowed_tools=[
            t.strip()
            for t in fm.get("allowed-tools", "").split(",")
            if t.strip()
        ]
        if isinstance(fm.get("allowed-tools"), str)
        else fm.get("allowed-tools", []),
        mode=fm.get("mode", "automated"),
    )


def _list_files(skill_dir: Path) -> list[str]:
    root = skill_dir.resolve()
    return sorted(str(path.resolve().relative_to(root)) for path in skill_dir.rglob("*") if path.is_file())


def list_skills() -> list[SkillSummary]:
    results: list[SkillSummary] = []
    seen_names: set[str] = set()
    for root in _roots():
        for path in sorted(root.iterdir()):
            if not _listable_skill_dir(path):
                continue
            skill_name = path.name
            if skill_name in seen_names:
                continue
            seen_names.add(skill_name)
            meta = _meta_from_dir(path)
            results.append(SkillSummary(name=skill_name, description=meta.description))
    return results


def get_skill(name: str) -> SkillDetail:
    skill_dir = _skill_dir(name)
    if not _listable_skill_dir(skill_dir):
        raise SkillNotFoundError(name)
    return SkillDetail(meta=_meta_from_dir(skill_dir), files=_list_files(skill_dir))


def create_skill(name: str, description: str = "", create_scripts_folder: bool = False) -> SkillDetail:
    skill_dir = _skill_dir(name)
    if skill_dir.exists():
        raise SkillAlreadyExistsError(name)
    skill_dir.mkdir(parents=True)
    frontmatter = yaml.dump({"name": name, "description": description}, default_flow_style=False)
    (skill_dir / SKILL_FILE).write_text(f"---\n{frontmatter}---\n")
    if create_scripts_folder:
        (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    git.add_and_commit([name], f"Create skill: {name}", cwd=_root())
    return get_skill(name)


def delete_skill(name: str) -> None:
    skill_dir = _skill_dir(name)
    if not skill_dir.is_dir():
        raise SkillNotFoundError(name)
    shutil.rmtree(skill_dir)
    git.add_and_commit([name], f"Delete skill: {name}", cwd=_root())


def read_file(name: str, path: str) -> FileContent:
    skill_dir = _skill_dir(name)
    if not skill_dir.is_dir():
        raise SkillNotFoundError(name)
    file_path = safe_resolve(skill_dir, path)
    if not file_path.is_file():
        raise FileNotFoundInSkillError(name, path)
    return FileContent(content=file_path.read_text())


def write_file(name: str, path: str, content: str) -> None:
    skill_dir = _skill_dir(name)
    if not skill_dir.is_dir():
        raise SkillNotFoundError(name)
    file_path = safe_resolve(skill_dir, path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    git.add_and_commit([f"{name}/{path}"], f"Write {path} in skill {name}", cwd=_root())


def delete_file(name: str, path: str) -> None:
    skill_dir = _skill_dir(name)
    if not skill_dir.is_dir():
        raise SkillNotFoundError(name)
    file_path = safe_resolve(skill_dir, path)
    if not file_path.is_file():
        raise FileNotFoundInSkillError(name, path)
    file_path.unlink()
    git.add_and_commit([f"{name}/{path}"], f"Delete {path} from skill {name}", cwd=_root())


def upload_file(name: str, filename: str, data: bytes) -> None:
    skill_dir = _skill_dir(name)
    if not skill_dir.is_dir():
        raise SkillNotFoundError(name)
    file_path = safe_resolve(skill_dir, filename)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(data)
    git.add_and_commit([f"{name}/{filename}"], f"Upload {filename} to skill {name}", cwd=_root())


def file_versions(path: str) -> FileVersions:
    versions = git.file_versions(path, cwd=_root())
    return FileVersions(count=len(versions), versions=versions)
