"""Portable ZIP backup and restore helpers."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


def create_backup(root: Path, destination: Path) -> dict:
    files = []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*.md")):
            if ".kbkit" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            archive.write(path, relative)
            files.append(relative)
    return {"path": str(destination), "files": files}


def verify_backup(backup: Path) -> dict:
    with zipfile.ZipFile(backup) as archive:
        bad = archive.testzip()
        return {"ok": bad is None, "first_bad": bad, "files": archive.namelist()}


def restore_backup(backup: Path, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    restored = []
    with zipfile.ZipFile(backup) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError("backup contains a path outside destination")
            if member.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            restored.append(member.filename)
    return {"destination": str(destination), "files": restored}
