"""Optional Git adapter with shell-free subprocess calls."""

from __future__ import annotations

from contextlib import suppress
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4


class GitUnavailable(RuntimeError):
    pass


def read_objects(root: Path, args: list[str]) -> bytes:
    """Read local Git objects without fetching or modifying the worktree."""
    if shutil.which("git") is None:
        raise GitUnavailable("git is unavailable")
    return _run(root, args, timeout=30)


def _run(root: Path, args: list[str], *, timeout: int) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", *args], cwd=root, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GitUnavailable(f"git {args[0]} exceeded {timeout} seconds") from error
    if result.returncode:
        raise GitUnavailable(result.stderr.decode("utf-8", errors="replace").strip() or "git command failed")
    return result.stdout


def sync_worktree(root: Path, remote: str, branch: str) -> dict:
    def git(*args, timeout=30):
        return _run(root, list(args), timeout=timeout).decode("utf-8", errors="replace").strip()

    if shutil.which("git") is None:
        raise GitUnavailable("git is unavailable")
    if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
        raise GitUnavailable("the vault must be the root of its own Git worktree")
    ref = f"refs/heads/{branch}"
    git("check-ref-format", ref)
    if remote not in git("remote").splitlines():
        raise GitUnavailable("git.remote must name a configured remote in the vault repository")

    def check_worktree():
        if git("symbolic-ref", "-q", "HEAD") != ref:
            raise GitUnavailable(f"check out the configured vault branch {branch} before syncing")
        if git("status", "--porcelain", "--untracked-files=normal"):
            raise GitUnavailable("vault worktree has local changes; review or commit them before syncing")

    check_worktree()
    before = git("rev-parse", "HEAD")
    fetched_ref = f"refs/kbkit/sync/{uuid4().hex}"
    try:
        git("fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head",
            "--", remote, f"{ref}:{fetched_ref}", timeout=60)
        upstream = git("rev-parse", "--verify", f"{fetched_ref}^{{commit}}")
        check_worktree()
        if git("rev-parse", "HEAD") != before:
            raise GitUnavailable("vault HEAD changed during fetch; check the worktree and retry")
        if git("ls-tree", "--name-only", before, "--", ".kbkit") or git("ls-tree", "--name-only", upstream, "--", ".kbkit"):
            raise GitUnavailable("vault Git sync requires .kbkit metadata to be excluded from Git history")
        git("merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", "--", upstream)
        after = git("rev-parse", "HEAD")
        state = "updated" if after != before else ("up_to_date" if after == upstream else "ahead")
        return {"git_status": state, "before_commit": before, "after_commit": after}
    finally:
        # This ref is private to the attempt and is not the branch the user sees.
        with suppress(GitUnavailable, OSError):
            _run(root, ["update-ref", "-d", fetched_ref], timeout=30)
