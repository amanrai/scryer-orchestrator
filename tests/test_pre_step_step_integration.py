from __future__ import annotations

import json
from pathlib import Path


class _FakeResponse:
    def __init__(self, body: str = ""):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _write_state(tmp_path: Path, hook_event_name: str) -> dict:
    common_volume = tmp_path / "common-volume"
    state = {
        "workflow_uuid": "wf-integration-123",
        "hook_event_name": hook_event_name,
        "common_volume_root": str(common_volume),
        "orchestrator_url": "http://orchestrator.test:8101",
        "tmuxer_url": "http://tmuxer.test:5678",
        "interaction_service_url": "http://interaction.test:8200",
        "secrets_service_url": "http://secrets.test:8211",
        "phase_number": 0,
        "step_details": {
            "name": "dummy",
            "executor_label": "codex",
            "model": "gpt-5.4",
        },
        "additional_caller_info": {
            "project_name": "scryer testing",
            "ticket_name": "Sample testing task",
            "task_description": "Write pi script",
            "task_id": "task-123",
            "selected_agent": "codex",
            "selected_model": "gpt-5.4",
        },
        "workflow_definition": {
            "name": "dummy workflow",
        },
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return state


def test_real_pre_step_outputs_are_consumed_by_real_step(tmp_path, monkeypatch, pre_step_module, step_module, resolver_module):
    common_volume = tmp_path / "common-volume"
    session_root = common_volume / "agent-sessions" / "wf-integration-123"
    templates_root = common_volume / "templates"
    (session_root / "interactor").mkdir(parents=True)
    (session_root / "interactor" / "interactor.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (session_root / ".agents" / "skills" / "dummy").mkdir(parents=True)
    templates_root.mkdir(parents=True)
    (templates_root / "agents.md").write_text(
        "# Agents\n\n- Process: {process_id}\n- Phase: {phase}\n- Step: {step}\n",
        encoding="utf-8",
    )

    pre_step_notifications: list[dict] = []

    def fake_pre_step_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode("utf-8")) if req.data else {}
        pre_step_notifications.append(payload)
        return _FakeResponse("{}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pre_step_module, "load_scryer_helper", lambda _root: resolver_module)
    monkeypatch.setattr(pre_step_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(pre_step_module.request, "urlopen", fake_pre_step_urlopen)

    _write_state(tmp_path, "pre_step")
    pre_step_module.main()

    assert (session_root / "task.md").exists()
    assert (session_root / "agents-dummy.md").exists()
    assert (session_root / "prompt-dummy.txt").exists()
    assert pre_step_notifications[0]["event"] == "done"

    step_requests: list[tuple[str, dict]] = []

    def fake_step_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode("utf-8")) if req.data else {}
        step_requests.append((req.full_url, payload))
        if req.full_url.endswith("/start/with-command-in-path"):
            return _FakeResponse(json.dumps({"session_name": "wf-integration-123-p0-dummy"}))
        if req.full_url.endswith("/processes/notify"):
            return _FakeResponse("{}")
        raise AssertionError(f"Unexpected urlopen target: {req.full_url}")

    monkeypatch.setattr(step_module, "load_scryer_helper", lambda _root: resolver_module)
    monkeypatch.setattr(step_module.request, "urlopen", fake_step_urlopen)

    _write_state(tmp_path, "step")
    step_module.main()

    env_contents = (session_root / ".env.dummy").read_text(encoding="utf-8")
    assert "export WORKFLOW_UUID=wf-integration-123" in env_contents
    assert "export STEP_NAME=dummy" in env_contents
    assert "export SESSION_NAME=wf-integration-123-p0-dummy" in env_contents

    tmuxer_url, tmuxer_payload = step_requests[0]
    assert tmuxer_url.endswith("/start/with-command-in-path")
    assert tmuxer_payload["path"] == "agent-sessions/wf-integration-123"
    assert tmuxer_payload["session_name"] == "wf-integration-123-p0-dummy"
    assert "source .env.dummy" in tmuxer_payload["command"]

    notify_url, notify_payload = step_requests[1]
    assert notify_url.endswith("/processes/notify")
    assert notify_payload["event"] == "start"
    assert notify_payload["detail"]["session_name"] == "wf-integration-123-p0-dummy"
