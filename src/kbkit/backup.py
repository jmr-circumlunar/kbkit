"""Archive a vault and publish a restore only after validating its contents."""

from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sqlite3
import tempfile
import unicodedata
from zipfile import ZipFile, ZIP_DEFLATED

from .prototype_lock import file_lock
from .storage import metadata_dir, vault_files


def create_backup(root: Path, destination: Path) -> dict:
    root, destination = root.resolve(), destination.resolve()
    if not root.is_dir():
        raise ValueError("vault directory does not exist")
    if destination.exists():
        raise FileExistsError(f"backup already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    state = metadata_dir(root)
    state.mkdir(parents=True, exist_ok=True)
    names = []
    with file_lock(state / "maintenance.lock"), file_lock(state / "write.lock"):
        for journal in sorted((state / "transactions").glob("*.json")):
            try:
                settled = json.loads(journal.read_bytes()).get("state") == "applied"
            except (ValueError, AttributeError):
                settled = False
            if not settled:
                raise ValueError(f"resolve the pending or damaged transaction before backup: {journal.name}")
        sources = [(path, path.relative_to(root).as_posix()) for path in vault_files(root)
                   if path != state and state not in path.parents and not path.name.startswith(".kbkit-")]
        for name in ("profile.toml", "knowledge.json", "automation.json"):
            sources.append((state / name, f".kbkit/{name}"))
        for name in ("history", "trash", "reports", "artifacts"):
            directory = state / name
            if directory.is_dir() and not directory.is_symlink():
                sources.extend((path, f".kbkit/{path.relative_to(state).as_posix()}") for path in vault_files(directory))
        with tempfile.TemporaryDirectory(prefix=".kbkit-backup-", dir=destination.parent) as folder:
            temporary = Path(folder) / "vault.zip"
            database = state / "state.sqlite"
            if database.is_file() and not database.is_symlink():
                snapshot = Path(folder) / "state.sqlite"
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as live, \
                        closing(sqlite3.connect(snapshot)) as copy:
                    live.backup(copy)
                sources.append((snapshot, ".kbkit/state.sqlite"))
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
                for path, relative in sources:
                    if path.is_file() and path != destination and not path.is_symlink():
                        archive.write(path, relative)
                        names.append(relative)
            os.link(temporary, destination)
    return {"path": str(destination), "files": names}


def _members(archive: ZipFile):
    seen = set()
    for member in archive.infolist():
        name = member.filename
        path = PurePosixPath(name)
        if "\\" in name or ":" in name or path.is_absolute() or PureWindowsPath(name).drive or ".." in path.parts or not path.parts:
            raise ValueError("backup contains an invalid relative path")
        key = unicodedata.normalize("NFC", path.as_posix()).casefold()
        if key in seen:
            raise ValueError(f"backup contains duplicate paths: {name}")
        seen.add(key)
        yield member, path.parts


def verify_backup(backup: Path) -> dict:
    with ZipFile(backup) as archive:
        list(_members(archive))
        bad = archive.testzip()
        return {"ok": bad is None, "first_bad": bad, "files": archive.namelist()}


def restore_backup(backup: Path, destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("restore destination must be new or empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    external = metadata_dir(destination)
    external_state = external != destination / ".kbkit"
    restored = []
    with ZipFile(backup) as archive, tempfile.TemporaryDirectory(prefix=".kbkit-restore-", dir=destination.parent) as folder:
        members = list(_members(archive))
        staged = Path(folder) / "vault"
        staged.mkdir()
        for member, parts in members:
            if member.is_dir():
                continue
            target = staged.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as stream, target.open("xb") as file:
                shutil.copyfileobj(stream, file)
            restored.append(member.filename)
        staged_state = staged / ".kbkit"
        published_state = False
        try:
            if external_state and staged_state.is_dir():
                if external.exists():
                    raise ValueError("restore destination already has external kbkit state")
                external.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=".kbkit-state-", dir=external.parent) as state_folder:
                    copy = Path(state_folder) / "state"
                    shutil.copytree(staged_state, copy)
                    copy.rename(external)
                published_state = True
                shutil.rmtree(staged_state)
            if destination.exists():
                destination.rmdir()
            staged.rename(destination)
        except BaseException:
            if published_state:
                with tempfile.TemporaryDirectory(prefix=".kbkit-rollback-", dir=external.parent) as rollback:
                    external.rename(Path(rollback) / "state")
            raise
    return {"destination": str(destination), "files": restored}
