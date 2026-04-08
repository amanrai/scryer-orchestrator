from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib import error, request

import pytest


HOOKS_ROOT = Path("/Users/amanrai/Code/common-volume/hooks")
SECRETS_STATUS_URL = "http://127.0.0.1:8211/status"
VERIFICATION_MODALITIES = {
    "test_pre_workflow_hook.py": "adapter test with mocked subprocess/filesystem boundaries",
    "test_pre_step_step_integration.py": "hook integration test using real pre_step output and mocked tmuxer/orchestrator HTTP",
    "test_post_workflow_hook.py": "adapter test with mocked git/remote/resolver modules and session filesystem fixtures",
    "test_scryer_git.py": "git-helper unit test covering remote detection and PR artifact parsing",
    "test_scryer_resolver.py": "resolver unit test with mocked secrets-service responses",
    "test_step_hook.py": "adapter test with mocked tmuxer/orchestrator HTTP and session filesystem fixtures",
    "test_live_dummy_workflow_startup.py": "live integration test using PM API, orchestrator API, workflow logs, and filesystem artifacts",
}


def load_hook_module(filename: str):
    path = HOOKS_ROOT / filename
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load hook module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pre_workflow_module():
    return load_hook_module("scryer-pre-workflow.py")


@pytest.fixture
def post_workflow_module():
    return load_hook_module("scryer-post-workflow.py")


@pytest.fixture
def pre_step_module():
    return load_hook_module("scryer-pre-step.py")


@pytest.fixture
def step_module():
    return load_hook_module("scryer-step.py")


@pytest.fixture
def resolver_module():
    return load_hook_module("scryer_resolver.py")


@pytest.fixture
def git_helper_module():
    return load_hook_module("scryer_git.py")


def _vault_status_line() -> str:
    req = request.Request(SECRETS_STATUS_URL, method="GET")
    try:
        with request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        return f"Vault status before test run: unavailable ({exc.reason})"
    except Exception as exc:  # noqa: BLE001
        return f"Vault status before test run: unavailable ({exc})"

    if payload.get("locked", True):
        return "Vault status before test run: locked"
    unlocked_until = payload.get("unlocked_until") or "unknown"
    return f"Vault status before test run: unlocked (until {unlocked_until})"


def pytest_report_header(config):
    return [_vault_status_line()]


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.section("Verification Modality")
    for item in terminalreporter.stats.get("passed", []) + terminalreporter.stats.get("failed", []) + terminalreporter.stats.get("error", []):
        filename = Path(item.nodeid.split("::", 1)[0]).name
        modality = VERIFICATION_MODALITIES.get(filename)
        if modality:
            terminalreporter.write_line(f"{item.nodeid} -> {modality}")
