import shlex
import subprocess
import uuid
from pathlib import Path
from urllib import error, request

from ..config import settings


def infer_executor(script_path: Path) -> str:
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return "python3"
    if suffix == ".sh":
        return "bash"
    raise ValueError(f"Unsupported hook asset type: {script_path.name}")


def _tmux_base_cmd() -> list[str]:
    return ["tmux"]


def launch_script_in_tmux(script_path: Path, cwd: Path, log_path: Path) -> str:
    session_name = f"orch-{uuid.uuid4().hex[:12]}"
    executor = infer_executor(script_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = shlex.quote(str(log_path))
    command = (
        f"cd {shlex.quote(str(cwd))} && "
        f"{executor} {shlex.quote(script_path.name)} >> {log_file} 2>&1"
    )
    subprocess.run(
        [*_tmux_base_cmd(), "new-session", "-d", "-s", session_name, command],
        check=True,
        capture_output=True,
        text=True,
    )
    return session_name


def kill_tmux_session(session_name: str) -> None:
    req = request.Request(
        f"http://host.docker.internal:5678/sessions/{session_name}",
        method="DELETE",
    )
    try:
        with request.urlopen(req, timeout=10):
            return
    except error.HTTPError as exc:
        if exc.code != 404:
            raise
    except error.URLError:
        pass

    subprocess.run(
        [*_tmux_base_cmd(), "kill-session", "-t", session_name],
        check=False,
        capture_output=True,
        text=True,
    )
