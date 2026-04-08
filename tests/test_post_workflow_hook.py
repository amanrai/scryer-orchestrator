from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _write_state(tmp_path: Path, *, identities: list[str] | None = None) -> dict:
    common_volume = tmp_path / "common-volume"
    state = {
        "workflow_uuid": "wf-456",
        "hook_event_name": "post_workflow",
        "common_volume_root": str(common_volume),
        "orchestrator_url": "http://orchestrator.test:8101",
        "tmuxer_url": "http://tmuxer.test:5678",
        "interaction_service_url": "http://interaction.test:8200",
        "secrets_service_url": "http://secrets.test:8211",
        "project_identities_associated": identities or [],
        "additional_caller_info": {
            "project_name": "Scryer",
            "ticket_name": "Post Workflow Testing",
            "task_id": "task-456",
        },
        "workflow_definition": {
            "name": "dummy workflow",
        },
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return state


def _repo_path(common_volume: Path, workflow_uuid: str) -> Path:
    repo_path = common_volume / "agent-sessions" / workflow_uuid
    (repo_path / ".git").mkdir(parents=True)
    return repo_path


def test_post_workflow_cleans_up_and_logs_noop_when_no_pr_artifact(
    tmp_path,
    monkeypatch,
    post_workflow_module,
):
    state = _write_state(tmp_path)
    common_volume = tmp_path / "common-volume"
    repo_path = _repo_path(common_volume, state["workflow_uuid"])

    removed = [repo_path / ".claude", repo_path / ".codex"]
    untrusted: list[Path] = []
    notified: list[tuple[str, dict]] = []

    fake_git_module = SimpleNamespace(
        cleanup_agent_directories=lambda repo: removed,
        detect_remote=lambda repo: None,
        find_pr_artifact=lambda repo: None,
    )

    def fake_load_module(root, module_name, filename):
        assert root == common_volume
        if filename == "scryer_git.py":
            return fake_git_module
        raise AssertionError(f"Unexpected module request: {filename}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(post_workflow_module, "_load_module", fake_load_module)
    monkeypatch.setattr(post_workflow_module, "untrust_session_path", lambda state_arg, repo, logger: untrusted.append(repo))
    monkeypatch.setattr(post_workflow_module, "notify", lambda state_arg, event, detail=None: notified.append((event, detail or {})))

    post_workflow_module.main()

    assert untrusted == [repo_path]
    assert notified == [
        (
            "done",
            {
                "source": "scryer-post-workflow.py",
                "hook_event_name": "post_workflow",
            },
        )
    ]


def test_post_workflow_creates_pr_when_artifact_remote_and_identity_are_available(
    tmp_path,
    monkeypatch,
    post_workflow_module,
):
    state = _write_state(tmp_path, identities=["forgejo"])
    common_volume = tmp_path / "common-volume"
    repo_path = _repo_path(common_volume, state["workflow_uuid"])
    pr_artifact = repo_path / "pr.md"
    pr_artifact.write_text("# Ship workflow output\n\nBody text", encoding="utf-8")

    created_payloads: list[tuple[dict, object, dict, object]] = []
    untrusted: list[Path] = []
    notified: list[tuple[str, dict]] = []
    remote = SimpleNamespace(
        provider="gitea",
        remote_url="http://forge.local/owner/repo",
        repo_web_url="http://forge.local/owner/repo",
        branch="feature/workflow",
        base_branch="main",
    )

    def parse_pr_artifact(path, fallback_title):
        assert path == pr_artifact
        assert fallback_title == "Post Workflow Testing (dummy workflow)"
        return SimpleNamespace(
            title="Ship workflow output",
            body="Body text",
            head_branch="",
            base_branch="",
        )

    def create_pull_request(repo, remote_info, identity, payload):
        created_payloads.append((repo, remote_info, identity, payload))
        return {"html_url": "http://forge.local/owner/repo/pulls/1"}

    fake_git_module = SimpleNamespace(
        cleanup_agent_directories=lambda repo: [],
        detect_remote=lambda repo: remote,
        find_pr_artifact=lambda repo: pr_artifact,
        ahead_commit_count=lambda repo, branch, base: 2,
        parse_pr_artifact=parse_pr_artifact,
        create_pull_request=create_pull_request,
    )
    fake_resolver_module = SimpleNamespace(
        resolve_identity=lambda identity_name: {
            "username": "forge-user",
            "access_token": "secret-token",
            "git_user_name": "Forge User",
            "git_user_email": "forge@example.com",
        }
    )

    def fake_load_module(root, module_name, filename):
        assert root == common_volume
        if filename == "scryer_git.py":
            return fake_git_module
        if filename == "scryer_resolver.py":
            return fake_resolver_module
        raise AssertionError(f"Unexpected module request: {filename}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(post_workflow_module, "_load_module", fake_load_module)
    monkeypatch.setattr(post_workflow_module, "untrust_session_path", lambda state_arg, repo, logger: untrusted.append(repo))
    monkeypatch.setattr(post_workflow_module, "notify", lambda state_arg, event, detail=None: notified.append((event, detail or {})))

    post_workflow_module.main()

    assert len(created_payloads) == 1
    created_repo, created_remote, created_identity, pr_payload = created_payloads[0]
    assert created_repo == repo_path
    assert created_remote is remote
    assert created_identity["username"] == "forge-user"
    assert pr_payload.title == "Ship workflow output"
    assert pr_payload.body == "Body text"
    assert pr_payload.head_branch == "feature/workflow"
    assert pr_payload.base_branch == "main"
    assert untrusted == [repo_path]
    assert notified[0][0] == "done"


def test_post_workflow_notifies_fail_when_pr_creation_errors(
    tmp_path,
    monkeypatch,
    post_workflow_module,
):
    state = _write_state(tmp_path, identities=["forgejo"])
    common_volume = tmp_path / "common-volume"
    repo_path = _repo_path(common_volume, state["workflow_uuid"])
    pr_artifact = repo_path / "pr.md"
    pr_artifact.write_text("# Ship workflow output\n\nBody text", encoding="utf-8")

    untrusted: list[Path] = []
    notified: list[tuple[str, dict]] = []
    remote = SimpleNamespace(
        provider="gitea",
        remote_url="http://forge.local/owner/repo",
        repo_web_url="http://forge.local/owner/repo",
        branch="feature/workflow",
        base_branch="main",
    )

    fake_git_module = SimpleNamespace(
        cleanup_agent_directories=lambda repo: [],
        detect_remote=lambda repo: remote,
        find_pr_artifact=lambda repo: pr_artifact,
        ahead_commit_count=lambda repo, branch, base: 2,
        parse_pr_artifact=lambda path, fallback_title: SimpleNamespace(
            title="Ship workflow output",
            body="Body text",
            head_branch="",
            base_branch="",
        ),
        create_pull_request=lambda repo, remote_info, identity, payload: (_ for _ in ()).throw(RuntimeError("remote create failed")),
    )
    fake_resolver_module = SimpleNamespace(
        resolve_identity=lambda identity_name: {
            "username": "forge-user",
            "access_token": "secret-token",
        }
    )

    def fake_load_module(root, module_name, filename):
        assert root == common_volume
        if filename == "scryer_git.py":
            return fake_git_module
        if filename == "scryer_resolver.py":
            return fake_resolver_module
        raise AssertionError(f"Unexpected module request: {filename}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(post_workflow_module, "_load_module", fake_load_module)
    monkeypatch.setattr(post_workflow_module, "untrust_session_path", lambda state_arg, repo, logger: untrusted.append(repo))
    monkeypatch.setattr(post_workflow_module, "notify", lambda state_arg, event, detail=None: notified.append((event, detail or {})))

    try:
        post_workflow_module.main()
    except RuntimeError as exc:
        assert str(exc) == "remote create failed"
    else:
        raise AssertionError("Expected post-workflow failure to propagate")

    assert untrusted == []
    assert notified == [
        (
            "fail",
            {
                "source": "scryer-post-workflow.py",
                "hook_event_name": "post_workflow",
                "error": "remote create failed",
            },
        )
    ]
