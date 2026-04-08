import logging
import subprocess
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cwd = cwd or settings.workflows_path
    cmd = ["git", *args]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        log.error("git failed: %s\nstderr: %s", " ".join(cmd), result.stderr.strip())
    return result


def ensure_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if (root / ".git").exists():
        return
    _run("init", cwd=root)
    _run("add", "-A", cwd=root)
    _run("commit", "-m", "Initial commit", cwd=root)


def add_and_commit(paths: list[str], message: str, cwd: Path) -> None:
    _run("add", "--", *paths, cwd=cwd)
    _run("commit", "-m", message, cwd=cwd)


def add_all_and_commit(message: str, cwd: Path) -> None:
    _run("add", "-A", cwd=cwd)
    _run("commit", "-m", message, cwd=cwd)


def file_versions(path: str, cwd: Path) -> list[dict]:
    result = _run("log", "--follow", "--format=%H%n%ai%n%s", "--", path, cwd=cwd)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    lines = result.stdout.strip().split("\n")
    versions = []
    for index in range(0, len(lines), 3):
        versions.append(
            {
                "sha": lines[index],
                "date": lines[index + 1],
                "message": lines[index + 2],
            }
        )
    return versions
