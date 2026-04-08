from pathlib import Path

from .errors import PathTraversalError


def safe_resolve(base: Path, untrusted: str) -> Path:
    resolved = (base / untrusted).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise PathTraversalError(untrusted)
    return resolved
