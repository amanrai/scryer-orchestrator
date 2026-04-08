from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_state(tmp_path: Path, secrets_service_url: str = "http://secrets.local:8211") -> None:
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "workflow_uuid": "wf-resolver",
                "hook_event_name": "pre_workflow",
                "common_volume_root": str(tmp_path / "common-volume"),
                "orchestrator_url": "http://orchestrator.test:8101",
                "tmuxer_url": "http://tmuxer.test:5678",
                "interaction_service_url": "http://interaction.test:8200",
                "secrets_service_url": secrets_service_url,
                "phase_number": 2,
                "step_details": {"name": "Say Hello / Test"},
                "project_identities_associated": ["forgejo"],
                "project_environment_variables_associated": ["SAMPLE_ENV_VARIABLE"],
                "additional_caller_info": {},
                "workflow_definition": {},
            }
        ),
        encoding="utf-8",
    )


def test_resolve_identity_and_variable_when_unlocked(tmp_path, monkeypatch, resolver_module):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_request_json(method: str, url: str) -> dict:
        if url.endswith("/status"):
            return {"initialized": True, "locked": False}
        if url.endswith("/secrets"):
            return {
                "secrets": [
                    {
                        "name": "forgejo",
                        "user_defined_type": "git_identity",
                        "secret_id": "id-1",
                        "value": {"username": "aman", "access_token": "token-123"},
                    },
                    {
                        "name": "SAMPLE_ENV_VARIABLE",
                        "user_defined_type": "environment_variable",
                        "secret_id": "id-2",
                        "value": {"SAMPLE_ENV_VARIABLE": "hello-world"},
                    },
                ]
            }
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(resolver_module, "_request_json", fake_request_json)

    assert resolver_module.resolve_identity("forgejo") == {"username": "aman", "access_token": "token-123"}
    assert resolver_module.resolve_variable("SAMPLE_ENV_VARIABLE") == "hello-world"


def test_resolve_fails_immediately_when_vault_locked(tmp_path, monkeypatch, resolver_module):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_request_json(method: str, url: str) -> dict:
        if url.endswith("/status"):
            return {"initialized": True, "locked": True}
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(resolver_module, "_request_json", fake_request_json)

    with pytest.raises(resolver_module.SecretsVaultLockedError):
        resolver_module.resolve_identity("forgejo")

    with pytest.raises(resolver_module.SecretsVaultLockedError):
        resolver_module.resolve_variable("SAMPLE_ENV_VARIABLE")


def test_derives_canonical_step_session_name_from_runtime_state(tmp_path, monkeypatch, resolver_module):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "common-volume").mkdir()

    state = resolver_module.read_state()

    assert resolver_module.slugify("Say Hello / Test") == "Say-Hello-Test"
    assert resolver_module.derive_step_session_name("wf-resolver", 2, "Say Hello / Test") == "wf-resolver-p2-Say-Hello-Test"
    assert resolver_module.resolve_step_session_name_from_state(state) == "wf-resolver-p2-Say-Hello-Test"


def test_step_session_resolution_fails_with_precise_state_error(tmp_path, monkeypatch, resolver_module):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "workflow_uuid": "wf-resolver",
                "hook_event_name": "step",
                "common_volume_root": str(tmp_path / "common-volume"),
                "orchestrator_url": "http://orchestrator.test:8101",
                "tmuxer_url": "http://tmuxer.test:5678",
                "interaction_service_url": "http://interaction.test:8200",
                "secrets_service_url": "http://secrets.local:8211",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(resolver_module.StateResolutionError, match="phase_number"):
        resolver_module.resolve_step_session_name_from_state(resolver_module.read_state())


def test_resolve_variable_rejects_object_without_matching_key(tmp_path, monkeypatch, resolver_module):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_request_json(method: str, url: str) -> dict:
        if url.endswith("/status"):
            return {"initialized": True, "locked": False}
        if url.endswith("/secrets"):
            return {
                "secrets": [
                    {
                        "name": "SAMPLE_ENV_VARIABLE",
                        "user_defined_type": "environment_variable",
                        "secret_id": "id-2",
                        "value": {"OTHER_KEY": "hello-world"},
                    },
                ]
            }
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(resolver_module, "_request_json", fake_request_json)

    with pytest.raises(resolver_module.SecretTypeMismatchError, match="without a matching key"):
        resolver_module.resolve_variable("SAMPLE_ENV_VARIABLE")


def test_resolves_runtime_urls_and_common_volume_from_state(tmp_path, monkeypatch, resolver_module):
    _write_state(tmp_path)
    monkeypatch.chdir(tmp_path)
    common_volume = tmp_path / "common-volume"
    common_volume.mkdir()

    state = resolver_module.read_state()

    assert resolver_module.resolve_common_volume_root(state) == common_volume
    assert resolver_module.orchestrator_url(state) == "http://orchestrator.test:8101"
    assert resolver_module.tmuxer_url(state) == "http://tmuxer.test:5678"
    assert resolver_module.interaction_service_url(state) == "http://interaction.test:8200"
