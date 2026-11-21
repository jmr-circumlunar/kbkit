"""Per-vault paths for kbkit state."""

import hashlib
import os
import stat
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
