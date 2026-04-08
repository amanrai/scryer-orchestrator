from __future__ import annotations

import json
from pathlib import Path


def _base_state(tmp_path: Path, base_repo: str = "") -> dict:
    common_volume = tmp_path / "common-volume"
    state = {
        "workflow_uuid": "wf-123",
        "hook_event_name": "pre_workflow",
        "common_volume_root": str(common_volume),
        "orchestrator_url": "http://orchestrator.test:8101",
        "tmuxer_url": "http://tmuxer.test:5678",
        "interaction_service_url": "http://interaction.test:8200",
        "secrets_service_url": "http://secrets.test:8211",
        "additional_caller_info": {
            "project_name": "Scryer",
            "ticket_name": "Bootstrap Testing",
            "task_description": "Test bootstrap behavior",
            "task_id": "task-123",
            "project_base_repo_path_relative_to_common_volume": base_repo,
        },
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return state


def test_pre_workflow_without_repo_link_initializes_git_repo(
    tmp_path,
    monkeypatch,
    pre_workflow_module,
):
    state = _base_state(tmp_path, base_repo="")

    common_volume = tmp_path / "common-volume"
    (common_volume / "skills").mkdir(parents=True)
    (common_volume / "interactor").mkdir(parents=True)

    calls: list[list[str]] = []
    notifications: list[tuple[str, dict]] = []
    def fake_run(cmd, check=False, **kwargs):
        calls.append(cmd)
        return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pre_workflow_module, "notify", lambda state_arg, event, detail=None: notifications.append((event, detail or {})))
    monkeypatch.setattr(pre_workflow_module, "trust_session_path", lambda state_arg, session_root, logger: None)
    monkeypatch.setattr(pre_workflow_module, "_copy_full_skills_library", lambda *args, **kwargs: None)
    monkeypatch.setattr(pre_workflow_module, "_resolve_selected_environment_variables", lambda *args, **kwargs: None)
    monkeypatch.setattr(pre_workflow_module.subprocess, "run", fake_run)

    pre_workflow_module.main()

    assert ["git", "-C", str(common_volume / "agent-sessions" / "wf-123"), "init"] in calls
    assert ["git", "-C", str(common_volume / "agent-sessions" / "wf-123"), "branch", "-m", "main"] in calls
    assert notifications == [
        (
            "done",
            {
                "source": "scryer-pre-workflow.py",
                "hook_event_name": "pre_workflow",
            },
        )
    ]


def test_pre_workflow_with_repo_link_creates_fresh_worktree(
    tmp_path,
    monkeypatch,
    pre_workflow_module,
):
    state = _base_state(tmp_path, base_repo="repos/my-repo")

    common_volume = tmp_path / "common-volume"
    source_repo = common_volume / "repos" / "my-repo"
    (source_repo / ".git").mkdir(parents=True)
    (common_volume / "skills").mkdir(parents=True)
    (common_volume / "interactor").mkdir(parents=True)

    calls: list[list[str]] = []
    notifications: list[tuple[str, dict]] = []

    def fake_run(cmd, check=False, **kwargs):
        calls.append(cmd)
        return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pre_workflow_module, "notify", lambda state_arg, event, detail=None: notifications.append((event, detail or {})))
    monkeypatch.setattr(pre_workflow_module, "trust_session_path", lambda state_arg, session_root, logger: None)
    monkeypatch.setattr(pre_workflow_module, "_copy_full_skills_library", lambda *args, **kwargs: None)
    monkeypatch.setattr(pre_workflow_module, "_resolve_selected_environment_variables", lambda *args, **kwargs: None)
    monkeypatch.setattr(pre_workflow_module.subprocess, "run", fake_run)

    pre_workflow_module.main()

    worktree_call = next(cmd for cmd in calls if cmd[:5] == ["git", "-C", str(source_repo), "worktree", "add"])
    assert worktree_call[5] == "-b"
    assert worktree_call[-1] == str(common_volume / "agent-sessions" / "wf-123")
    assert notifications[0][1]["hook_event_name"] == "pre_workflow"
