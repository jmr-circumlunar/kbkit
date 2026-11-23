"""WorkBuddy lifecycle code embedded in cli.json by the package builder."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen


def install_root() -> Path:
    configured = os.environ.get("KBKIT_WORKBUDDY_DIR")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".kbkit-workbuddy"


def connection(root: Path) -> dict | None:
    try:
        state = json.loads((root / "connection.json").read_bytes())
        if (isinstance(state["connector_version"], str) and Path(state["python"]).is_file()
                and Path(state["archive"]).stat().st_size == state["bytes"]):
            return state
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None


def valid(runtime: bytes, release: dict) -> bool:
    return len(runtime) == release["bytes"] and hashlib.sha256(runtime).hexdigest() == release["sha256"]


def download(release: dict) -> bytes:
    failures = []
    for url in release["urls"]:
        try:
            with urlopen(url, timeout=10) as response:
                if urlsplit(response.geturl()).scheme != "https":
                    raise ValueError("download redirected to a non-HTTPS address")
                runtime = response.read(release["bytes"] + 1)
            if valid(runtime, release):
                return runtime
            raise ValueError("runtime checksum or size mismatch")
        except (OSError, HTTPException, ValueError) as error:
            failures.append(f"{urlsplit(url).netloc}: {error}")
    raise OSError("No published kbkit runtime could be verified. " + " | ".join(failures))


def atomic_write(path: Path, data: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".kbkit-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        if executable:
            temporary.chmod(temporary.stat().st_mode | stat.S_IXUSR)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def runtime_check(archive: Path, release: dict) -> None:
    command = [sys.executable, "-I", "-X", "utf8", str(archive)]
    for arguments, expected in [(["--version"], f"kbc {release['kbkit_version']}"),
                                (["doctor"], "FTS5: available")]:
        result = subprocess.run([*command, *arguments], capture_output=True, text=True, encoding="utf-8", timeout=30)
        if result.returncode or expected not in result.stdout.splitlines():
            message = (result.stderr or result.stdout).strip()
            raise RuntimeError(message or f"kbkit did not report {expected}")


def initialize(root: Path, release: dict) -> None:
    archive = root / "runtimes" / release["sha256"] / "kbkit.pyz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file() or not valid(archive.read_bytes(), release):
        runtime = download(release)
        with tempfile.TemporaryDirectory(dir=archive.parent) as temporary:
            staged = Path(temporary) / "kbkit.pyz"
            staged.write_bytes(runtime)
            runtime_check(staged, release)
            staged.replace(archive)
    else:
        runtime_check(archive, release)
    receipt = root / "connection.json"
    if os.name != "nt":
        launcher = f"""#!/bin/sh
if [ ! -f {shlex.quote(str(receipt))} ]; then
    echo 'Reconnect the kbkit connector in WorkBuddy.' >&2
    exit 1
fi
exec {shlex.quote(sys.executable)} -I -X utf8 {shlex.quote(str(archive))} "$@"
"""
        atomic_write(root / "kbc", launcher.encode("utf-8"), executable=True)
    state = {key: release[key] for key in ("connector_version", "kbkit_version", "commit", "sha256", "bytes")}
    state.update(python=sys.executable, archive=str(archive))
    atomic_write(receipt, json.dumps(state, indent=2).encode("utf-8"))


def main(release: dict, action: str) -> int:
    root = install_root()
    try:
        if action == "init":
            initialize(root, release)
        elif action == "disconnect":
            (root / "connection.json").unlink(missing_ok=True)
        else:
            state = connection(root)
            if action == "version":
                print(state["connector_version"] if state else "0.0.0")
            else:
                print("KBKIT_READY" if state else "KBKIT_DISCONNECTED")
                return 0 if state else 1
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"kbkit connector: {error}", file=sys.stderr)
        return 1
