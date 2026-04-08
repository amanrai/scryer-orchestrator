import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_env_file() -> str:
    # Default to the repo-local .env, but allow host runs to point at .machine-env explicitly.
    return os.getenv("SCRYER_ENV_FILE", ".env")


class Settings(BaseSettings):
    common_volume_root: Path = Path("/workspace/common-volume")
    skills_paths: list[Path] = [Path("/workspace/common-volume/skills")]
    workflows_path: Path = Path("/workspace/common-volume/workflows")
    hooks_path: Path = Path("/workspace/common-volume/hooks")
    hook_fires_path: Path = Path("/workspace/common-volume/hook-fires")
    data_dir: Path = Path("/workspace/common-volume/new-orchestrator/data")
    cors_origins: list[str] = ["*"]

    valkey_url: str = "redis://valkey:6379"
    valkey_channel_agent_to_ui: str = "agent:to:ui"
    valkey_channel_notifications: str = "agent:notifications"

    process_timeout_seconds: int = 86400
    tmux_socket_name: str = "new-orchestrator"
    orchestrator_url: str = "http://new-orchestrator:8101"
    tmuxer_url: str = "http://host.docker.internal:5678"
    interaction_service_url: str = "http://interaction-service:8200"
    secrets_service_url: str = "http://host.docker.internal:8211"

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=_default_env_file(),
        env_file_encoding="utf-8",
    )

    @field_validator("skills_paths", mode="before")
    @classmethod
    def _normalize_skills_paths(cls, value):
        if value in (None, ""):
            return [Path("/workspace/common-volume/skills")]
        if isinstance(value, (str, Path)):
            return [value]
        return value

    @property
    def skills_path(self) -> Path:
        # The first configured skills root is the writable primary root used for edits.
        return self.skills_paths[0]


settings = Settings()
