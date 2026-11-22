"""Per-vault paths for kbkit state."""

import hashlib
import os
import stat
import sys
from pathlib import Path


def metadata_dir(root: Path) -> Path:
    configured = os.environ.get("KBKIT_HOME")
    if not configured:
        return root / ".kbkit"
    root = root.resolve()
    base = Path(configured).expanduser().resolve()
    if base == root or root in base.parents:
        raise ValueError("KBKIT_HOME must point outside the vault")
    location = os.path.normcase(str(root)).encode("utf-8")
    return base / hashlib.sha256(location).hexdigest()[:32]


def markdown_files(root: Path) -> dict[str, tuple[Path, os.stat_result]]:
    paths = {}
    root = root.resolve()
    folders = [root]
    while folders:
        with os.scandir(folders.pop()) as entries:
            for entry in entries:
                if entry.name.lower() in {".kbkit", ".git"} or entry.is_symlink():
                    continue
                is_directory = entry.is_dir(follow_symlinks=False)
                if not is_directory and not entry.name.lower().endswith(".md"):
                    continue
                info = entry.stat(follow_symlinks=False)
                if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                path = Path(entry.path)
                if is_directory:
                    folders.append(path)
                elif stat.S_ISREG(info.st_mode):
                    paths[path.relative_to(root).as_posix()] = (path, info)
    return paths

def change_tokens(files: dict[str, tuple[Path, os.stat_result]]) -> dict[str, str]:
    """Identify content changes even when a writer restores mtime and size."""
    if os.name != "nt":
        return {relative: f"posix:{info.st_dev}:{info.st_ino}:{info.st_ctime_ns}"
                for relative, (_, info) in files.items()}

    from .windows_changes import directory_changes

    directories: dict[Path, dict[str, str]] = {}
    result: dict[str, str] = {}
    for relative, (path, _) in files.items():
        if path.parent not in directories:
            directories[path.parent] = directory_changes(path.parent)
        token = directories[path.parent].get(path.name)
        if token:
            result[relative] = token
    return result

def app_data_dir(kind: str) -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / ("Caches" if kind == "cache" else "Application Support") / "kbkit"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", home)) / "kbkit"
    variable, fallback = ("XDG_CACHE_HOME", home / ".cache") if kind == "cache" else (
        "XDG_DATA_HOME", home / ".local" / "share")
    return Path(os.environ.get(variable, fallback)) / "kbkit"

def vault_files(root: Path):
    """Walk portable vault files without following symlinks or junctions."""
    for folder, dirs, files in os.walk(root):
        location = Path(folder)
        dirs[:] = sorted(name for name in dirs
                         if name.casefold() not in {".git", ".kbkit"}
                         and not (location / name).is_symlink()
                         and not getattr((location / name).lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        if location == root / ".obsidian":
            dirs[:] = [name for name in dirs if name == "snippets"]
            files = [name for name in files if not name.startswith("workspace")]
        for name in sorted(files):
            path = location / name
            if not path.is_symlink() and path.is_file():
                yield path
