from pathlib import Path

import pytest

from app.services import skills
from app.services.errors import SkillNotFoundError


@pytest.fixture
def skill_roots(tmp_path, monkeypatch):
    local_root = tmp_path / "my-skills"
    downloaded_root = tmp_path / "downloaded-skills"
    local_root.mkdir()
    downloaded_root.mkdir()
    monkeypatch.setattr(skills.settings, "skills_paths", [local_root, downloaded_root])
    return local_root, downloaded_root


def _write_skill(root: Path, name: str, description: str = ""):
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n")
    return skill_dir


def test_list_skills_only_includes_subfolders_with_skill_md(skill_roots):
    local_root, _ = skill_roots
    _write_skill(local_root, "mine", "My skill")
    (local_root / "not-a-skill").mkdir()
    (local_root / ".hidden").mkdir()
    (local_root / ".hidden" / "SKILL.md").write_text("---\nname: hidden\n---\n")

    listed = skills.list_skills()

    assert [(item.name, item.description) for item in listed] == [("mine", "My skill")]


def test_list_skills_prefers_first_root_on_name_collision(skill_roots):
    local_root, downloaded_root = skill_roots
    _write_skill(local_root, "shared", "Local version")
    _write_skill(downloaded_root, "shared", "Downloaded version")
    _write_skill(downloaded_root, "downloaded-only", "Downloaded only")

    listed = skills.list_skills()

    assert [(item.name, item.description) for item in listed] == [
        ("shared", "Local version"),
        ("downloaded-only", "Downloaded only"),
    ]


def test_get_skill_reads_first_matching_root(skill_roots):
    local_root, downloaded_root = skill_roots
    _write_skill(downloaded_root, "external", "External skill")
    _write_skill(local_root, "external", "Preferred local skill")
    (local_root / "external" / "extra.txt").write_text("hello")

    detail = skills.get_skill("external")

    assert detail.meta.description == "Preferred local skill"
    assert "extra.txt" in detail.files


def test_get_skill_rejects_directory_without_skill_md(skill_roots):
    local_root, _ = skill_roots
    (local_root / "junk-folder").mkdir()

    with pytest.raises(SkillNotFoundError):
        skills.get_skill("junk-folder")
