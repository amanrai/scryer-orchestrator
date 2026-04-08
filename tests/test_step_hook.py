from __future__ import annotations

import json
from pathlib import Path

import pytest


class _FakeResponse:
    def __init__(self, body: str = ""):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _write_step_state(tmp_path: Path, *, selected_agent: str = "codex", selected_model: str = "gpt-5.4") -> dict:
    common_volume = tmp_path / "common-volume"
    state = {
        "workflow_uuid": "wf-step-123",
        "hook_event_name": "step",
        "common_volume_root": str(common_volume),
        "orchestrator_url": "http://orchestrator.test:8101",
        "tmuxer_url": "http://tmuxer.test:5678",
        "interaction_service_url": "http://interaction.test:8200",
        "secrets_service_url": "http://secrets.test:8211",
        "phase_number": 2,
        "step_details": {
            "name": "dummy",
            "executor_label": selected_agent,
            "model": selected_model,
        },
        "additional_caller_info": {
            "project_name": "scryer testing",
            "ticket_name": "Sample testing task",
            "selected_agent": selected_agent,
            "selected_model": selected_model,
        },
        "workflow_definition": {
            "name": "dummy workflow",
        },
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return state


def _prepare_session_root(common_volume: Path, workflow_uuid: str, *, step_name: str = "dummy", agent: str = "codex") -> Path:
    session_root = common_volume / "agent-sessions" / workflow_uuid
    (session_root / "interactor").mkdir(parents=True)
    (session_root / f"prompt-{step_name}.txt").write_text("say hello", encoding="utf-8")
    (session_root / f"agents-{step_name}.md").write_text("# agent instructions", encoding="utf-8")
    (session_root / "interactor" / "interactor.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    skill_root = {
        "claude": session_root / ".claude" / "skills",
        "codex": session_root / ".agents" / "skills",
        "gemini": session_root / ".gemini" / "skills",
    }[agent]
    (skill_root / step_name).mkdir(parents=True, exist_ok=True)
    return session_root


def test_step_launches_tmux_session_and_notifies_start(tmp_path, monkeypatch, step_module, resolver_module):
    state = _write_step_state(tmp_path, selected_agent="codex", selected_model="gpt-5.4")
    common_volume = tmp_path / "common-volume"
    session_root = _prepare_session_root(common_volume, state["workflow_uuid"], agent="codex")
    expected_session_name = "wf-step-123-p2-dummy"

    requests_seen: list[tuple[str, dict]] = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode("utf-8")) if req.data else {}
        requests_seen.append((req.full_url, payload))
        if req.full_url.endswith("/start/with-command-in-path"):
            return _FakeResponse(json.dumps({"session_name": expected_session_name}))
        if req.full_url.endswith("/processes/notify"):
            return _FakeResponse("{}")
        raise AssertionError(f"Unexpected urlopen target: {req.full_url}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(step_module, "load_scryer_helper", lambda _root: resolver_module)
    monkeypatch.setattr(step_module.request, "urlopen", fake_urlopen)

    step_module.main()

    env_file = session_root / ".env.dummy"
    env_contents = env_file.read_text(encoding="utf-8")
    assert 'export WORKFLOW_UUID=wf-step-123' in env_contents
    assert 'export PHASE_NUMBER=2' in env_contents
    assert 'export STEP_NAME=dummy' in env_contents
    assert f'export SESSION_NAME={expected_session_name}' in env_contents
    assert 'export PROJECT_NAME='"'"'scryer testing'"'"'' in env_contents
    assert 'export TASK_TITLE='"'"'Sample testing task'"'"'' in env_contents

    tmuxer_url, tmuxer_payload = requests_seen[0]
    assert tmuxer_url.endswith("/start/with-command-in-path")
    assert tmuxer_payload["path"] == "agent-sessions/wf-step-123"
    assert tmuxer_payload["session_name"] == expected_session_name
    assert "source .env.dummy" in tmuxer_payload["command"]
    assert "codex --model gpt-5.4" in tmuxer_payload["command"]

    notify_url, notify_payload = requests_seen[1]
    assert notify_url.endswith("/processes/notify")
    assert notify_payload["event"] == "start"
    assert notify_payload["workflow_uuid"] == "wf-step-123"
    assert notify_payload["phase_number"] == 2
    assert notify_payload["step_name"] == "dummy"
    assert notify_payload["detail"]["session_name"] == expected_session_name


def test_step_fails_when_prompt_file_missing(tmp_path, monkeypatch, step_module, resolver_module):
    state = _write_step_state(tmp_path, selected_agent="claude", selected_model="sonnet")
    common_volume = tmp_path / "common-volume"
    session_root = _prepare_session_root(common_volume, state["workflow_uuid"], agent="claude")
    (session_root / "prompt-dummy.txt").unlink()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(step_module, "load_scryer_helper", lambda _root: resolver_module)

    with pytest.raises(RuntimeError, match="prompt-dummy.txt"):
        step_module.main()


def test_step_notifies_fail_when_tmuxer_launch_errors(tmp_path, monkeypatch, step_module, resolver_module):
    state = _write_step_state(tmp_path, selected_agent="gemini", selected_model="gemini-2.5-pro")
    common_volume = tmp_path / "common-volume"
    _prepare_session_root(common_volume, state["workflow_uuid"], agent="gemini")

    notify_payloads: list[dict] = []

    class _FakeHttpError(step_module.urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="http://tmuxer.test:5678/start/with-command-in-path",
                code=500,
                msg="Internal Server Error",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return b"tmuxer exploded"

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode("utf-8")) if req.data else {}
        if req.full_url.endswith("/start/with-command-in-path"):
            raise _FakeHttpError()
        if req.full_url.endswith("/processes/notify"):
            notify_payloads.append(payload)
            return _FakeResponse("{}")
        raise AssertionError(f"Unexpected urlopen target: {req.full_url}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(step_module, "load_scryer_helper", lambda _root: resolver_module)
    monkeypatch.setattr(step_module.request, "urlopen", fake_urlopen)

    with pytest.raises(step_module.urllib.error.HTTPError):
        step_module.main()

    assert notify_payloads == [
        {
            "workflow_uuid": "wf-step-123",
            "phase_number": 2,
            "step_name": "dummy",
            "event": "fail",
            "detail": {
                "source": "scryer-step.py",
                "hook_event_name": "step",
                "error": "tmuxer exploded",
                "session_name": "wf-step-123-p2-dummy",
            },
        }
    ]
