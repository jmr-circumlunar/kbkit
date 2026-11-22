"""Optional Git adapter with shell-free subprocess calls."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GitUnavailable(RuntimeError):
    pass


def read_objects(root: Path, args: list[str]) -> bytes:
    """Read local Git objects without fetching or modifying the worktree."""
    if shutil.which("git") is None:
        raise GitUnavailable("git is unavailable")
    result = subprocess.run(
        ["git", "--literal-pathspecs", *args], cwd=root, capture_output=True, timeout=30, check=False
    )
    if result.returncode:
        raise GitUnavailable(result.stderr.decode("utf-8", errors="replace").strip() or "git command failed")
    return result.stdout
