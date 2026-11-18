"""Optional Git adapter with shell-free subprocess calls."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GitUnavailable(RuntimeError):
    pass


def _run(root: Path, args: list[str]) -> str:
    if shutil.which("git") is None:
        raise GitUnavailable("git is unavailable")
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def status(root: Path) -> dict:
    try:
        output = _run(root, ["status", "--short"])
    except (GitUnavailable, RuntimeError):
        return {"available": False, "changes": []}
    return {"available": True, "changes": output.splitlines()}


def commit(root: Path, message: str) -> dict:
    _run(root, ["add", "--", "."])
    _run(root, ["commit", "-m", message])
    return {"available": True, "committed": True}
