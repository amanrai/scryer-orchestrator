from __future__ import annotations

from pathlib import Path


def test_detect_remote_for_http_gitea_remote(tmp_path, monkeypatch, git_helper_module):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    def fake_git_optional_output(repo, *args):
        assert repo == repo_path
        mapping = {
            ("config", "--get", "remote.origin.url"): "http://100.85.218.31:8088/amanrai/scryerTesterRepo",
            ("rev-parse", "--abbrev-ref", "HEAD"): "feature/workflow",
            ("symbolic-ref", "refs/remotes/origin/HEAD"): "refs/remotes/origin/main",
        }
        return mapping.get(args)

    monkeypatch.setattr(git_helper_module, "git_optional_output", fake_git_optional_output)

    remote = git_helper_module.detect_remote(repo_path)

    assert remote.provider == "gitea"
    assert remote.remote_url == "http://100.85.218.31:8088/amanrai/scryerTesterRepo"
    assert remote.repo_web_url == "http://100.85.218.31:8088/amanrai/scryerTesterRepo"
    assert remote.api_base_url == "http://100.85.218.31:8088/api/v1"
    assert remote.owner == "amanrai"
    assert remote.repo == "scryerTesterRepo"
    assert remote.branch == "feature/workflow"
    assert remote.base_branch == "main"


def test_find_pr_artifact_skips_agent_local_dirs(tmp_path, git_helper_module):
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)
    claude_dir = repo_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "pr.md").write_text("bad", encoding="utf-8")
    docs_dir = repo_path / "docs"
    docs_dir.mkdir(parents=True)
    expected = docs_dir / "pr.md"
    expected.write_text("# Good title\n\nUseful body", encoding="utf-8")

    found = git_helper_module.find_pr_artifact(repo_path)

    assert found == expected


def test_parse_pr_artifact_uses_heading_as_title(tmp_path, git_helper_module):
    pr_path = tmp_path / "pr.md"
    pr_path.write_text("# Ship workflow output\n\nBody text", encoding="utf-8")

    payload = git_helper_module.parse_pr_artifact(pr_path, "Fallback title")

    assert payload.title == "Ship workflow output"
    assert payload.body == "Body text"
    assert payload.head_branch == ""
    assert payload.base_branch == ""
