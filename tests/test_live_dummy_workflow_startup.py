from __future__ import annotations

import json
import time
from pathlib import Path
from urllib import error, request


PM_API_BASE = "http://127.0.0.1:8000/api"
ORCHESTRATOR_API_BASE = "http://127.0.0.1:8101"
COMMON_VOLUME_ROOT = Path("/Users/amanrai/Code/common-volume")

TEST_PROJECT_ID = "029d3881-eb66-43f7-a424-a327e828793c"
TEST_TASK_ID = "509e2f63-0073-426d-a9c0-baddf13fcd1c"
TEST_WORKFLOW_NAME = "dummy workflow"

PROJECT_IDENTITIES_PROPERTY_KEY = "project_identities"
PROJECT_ENVIRONMENT_VARIABLES_PROPERTY_KEY = "project_environment_variables"


def _request_json(method: str, url: str, payload: dict | None = None) -> dict | list:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def _delete(url: str) -> None:
    req = request.Request(url, method="DELETE")
    with request.urlopen(req, timeout=30):
        pass


def _parse_string_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _wait_for_path(path: Path, timeout_seconds: int = 90) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists():
            return path
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for path to exist: {path}")


def _wait_for_process_state(workflow_uuid: str, timeout_seconds: int = 90) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        process = _request_json("GET", f"{ORCHESTRATOR_API_BASE}/processes/{workflow_uuid}")
        if process.get("status") in {"running", "completed", "failed"}:
            return process
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for process state for workflow {workflow_uuid}")


def _wait_for_process_status(workflow_uuid: str, expected_status: str, timeout_seconds: int = 90) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        process = _request_json("GET", f"{ORCHESTRATOR_API_BASE}/processes/{workflow_uuid}")
        if process.get("status") == expected_status:
            return process
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for workflow {workflow_uuid} status={expected_status}")


def _wait_for_logs_containing(workflow_uuid: str, needle: str, timeout_seconds: int = 90) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with request.urlopen(f"{ORCHESTRATOR_API_BASE}/processes/{workflow_uuid}/logs", timeout=30) as response:
            logs = response.read().decode("utf-8")
        if needle in logs:
            return logs
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for workflow logs to contain: {needle}")


def test_live_dummy_workflow_startup_uses_project_runtime_selections():
    project = _request_json("GET", f"{PM_API_BASE}/projects/{TEST_PROJECT_ID}")
    task = _request_json("GET", f"{PM_API_BASE}/tasks/{TEST_TASK_ID}")
    project_properties = _request_json("GET", f"{PM_API_BASE}/projects/{TEST_PROJECT_ID}/properties")
    repo_link = _request_json("GET", f"{PM_API_BASE}/projects/{TEST_PROJECT_ID}/repo-link")
    secrets_status = _request_json("GET", "http://127.0.0.1:8211/status")

    property_map = {item["key"]: item["value"] for item in project_properties}
    selected_identities = _parse_string_list(property_map.get(PROJECT_IDENTITIES_PROPERTY_KEY))
    selected_environment_variables = _parse_string_list(property_map.get(PROJECT_ENVIRONMENT_VARIABLES_PROPERTY_KEY))
    runtime_project_properties = {
        key: value
        for key, value in property_map.items()
        if key not in {PROJECT_IDENTITIES_PROPERTY_KEY, PROJECT_ENVIRONMENT_VARIABLES_PROPERTY_KEY}
    }

    assert selected_identities == ["forgejo"]
    assert selected_environment_variables == ["SAMPLE_ENV_VARIABLE"]
    assert repo_link["clone_status"] == "ready"
    assert repo_link["relative_repo_path"] == "repos/scryer-testing"

    created_process = _request_json(
        "POST",
        f"{ORCHESTRATOR_API_BASE}/processes",
        {
            "task_id": task["id"],
            "workflow_name": TEST_WORKFLOW_NAME,
            "project_name": project["name"],
            "project_base_repo_path_relative_to_common_volume": repo_link["relative_repo_path"],
            "project_identities_associated": selected_identities,
            "project_environment_variables_associated": selected_environment_variables,
            "additional_caller_info": {
                "project_name": project["name"],
                "ticket_name": task["title"],
                "task_description": task.get("description_md") or "",
                "task_id": task["id"],
                "project_base_repo_path_relative_to_common_volume": repo_link["relative_repo_path"],
                "project_identities_associated": selected_identities,
                "project_environment_variables_associated": selected_environment_variables,
                "project_properties": runtime_project_properties,
            },
            "step_configs": {},
        },
    )

    workflow_uuid = created_process["workflow_uuid"]
    process_path = COMMON_VOLUME_ROOT / "hook-fires" / workflow_uuid
    state_path = process_path / "pre_workflow" / "state.json"
    session_root = COMMON_VOLUME_ROOT / "agent-sessions" / workflow_uuid

    try:
        _wait_for_path(state_path)
        _wait_for_path(session_root)
        if secrets_status.get("locked", True):
            process = _wait_for_process_status(workflow_uuid, "failed")
            logs = _wait_for_logs_containing(workflow_uuid, "Secrets vault is locked.")
        else:
            process = _wait_for_process_state(workflow_uuid)
            logs = _wait_for_logs_containing(
                workflow_uuid,
                "Resolved environment variable SAMPLE_ENV_VARIABLE='sample environment variable value.'",
            )

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["workflow_uuid"] == workflow_uuid
        assert state["hook_event_name"] == "pre_workflow"
        assert state["secrets_service_url"] == "http://host.docker.internal:8211"
        assert state["project_identities_associated"] == ["forgejo"]
        assert state["project_environment_variables_associated"] == ["SAMPLE_ENV_VARIABLE"]
        assert state["additional_caller_info"]["project_name"] == "scryer testing"
        assert state["additional_caller_info"]["ticket_name"] == "Sample testing task"
        assert state["additional_caller_info"]["task_id"] == TEST_TASK_ID
        assert state["additional_caller_info"]["project_base_repo_path_relative_to_common_volume"] == "repos/scryer-testing"
        assert state["additional_caller_info"]["project_properties"] == {"remote_repo": "http://100.85.218.31:8088/amanrai/scryerTesterRepo"}

        assert session_root.exists()
        assert (session_root / ".git").exists()
        assert (session_root / ".claude").exists()
        assert (session_root / ".codex").exists()
        assert (session_root / ".gemini").exists()
        assert (session_root / "interactor").exists()

        git_dir_pointer = (session_root / ".git").read_text(encoding="utf-8").strip()
        assert git_dir_pointer == f"gitdir: /workspace/common-volume/repos/scryer-testing/.git/worktrees/{workflow_uuid}"
        worktree_metadata_root = Path(repo_link["absolute_repo_path"]) / ".git" / "worktrees" / workflow_uuid
        assert worktree_metadata_root.exists()
        assert (worktree_metadata_root / "HEAD").exists()
        assert (worktree_metadata_root / "gitdir").exists()

        assert process["workflow_uuid"] == workflow_uuid
        assert process["project_identities_associated"] == ["forgejo"]
        assert process["project_environment_variables_associated"] == ["SAMPLE_ENV_VARIABLE"]
        assert process["additional_caller_info"]["project_properties"] == {"remote_repo": "http://100.85.218.31:8088/amanrai/scryerTesterRepo"}
        if secrets_status.get("locked", True):
            assert process["status"] == "failed"
            assert "Secrets vault is locked." in logs
        else:
            assert "Resolved environment variable SAMPLE_ENV_VARIABLE='sample environment variable value.'" in logs
    finally:
        try:
            _delete(f"{ORCHESTRATOR_API_BASE}/processes/{workflow_uuid}")
        except error.HTTPError:
            pass
