"""Portable ZIP backup and restore helpers."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from .storage import markdown_files, metadata_dir


def create_backup(root: Path, destination: Path) -> dict:
    files = []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, (path, _) in sorted(markdown_files(root).items()):
            archive.write(path, relative)
            files.append(relative)
        metadata = metadata_dir(root)
        manifest = metadata / "knowledge.json"
        if manifest.is_file() and not manifest.is_symlink():
            relative = ".kbkit/knowledge.json"
            archive.writestr(relative, manifest.read_bytes())
            files.append(relative)
            snapshots = sorted((metadata / "history").glob("*.md"))
            for path in snapshots:
                if path.is_file() and not path.is_symlink():
                    relative = f".kbkit/history/{path.name}"
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
            name = Path(member.filename)
            base = metadata_dir(destination).resolve() if name.parts[:1] == (".kbkit",) else destination.resolve()
            relative = name.parts[1:] if name.parts[:1] == (".kbkit",) else name.parts
            target = base.joinpath(*relative).resolve()
            if base not in target.parents and not (member.is_dir() and target == base):
                raise ValueError("backup contains a path outside destination")
            if member.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            restored.append(member.filename)
    return {"destination": str(destination), "files": restored}
