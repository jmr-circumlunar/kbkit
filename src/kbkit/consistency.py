"""Post-write consistency checks for E4."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from .vault_profile import index_path


def check_consistency(root: Path) -> dict:
    profile = root / ".kbkit" / "profile.toml"
    if not profile.exists():
        return {"ok": False, "errors": ["vault is not initialized"]}
    database = index_path(root)
    if not database.exists():
        return {"ok": False, "errors": ["index is missing"]}
    errors: list[str] = []
    with closing(sqlite3.connect(database)) as connection:
        for relative, expected in connection.execute("SELECT path, content_hash FROM documents"):
            path = root / relative
            if not path.exists():
                errors.append(f"missing document: {relative}")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                errors.append(f"hash mismatch: {relative}")
    return {"ok": not errors, "errors": errors}
