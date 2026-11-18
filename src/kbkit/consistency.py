"""Post-write consistency checks for E4."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def check_consistency(root: Path) -> dict:
    profile = root / ".kbkit" / "profile.toml"
    if not profile.exists():
        return {"ok": False, "errors": ["vault is not initialized"]}
    uuid_value = next(line.split('"', 2)[1] for line in profile.read_text(encoding="utf-8").splitlines() if line.startswith("vault_uuid"))
    import os

    base = Path(os.environ.get("KBKIT_INDEX_DIR", Path(os.environ.get("LOCALAPPDATA", root / ".kbkit")) / "kbkit" / "indexes"))
    database = base / f"{uuid_value}.sqlite"
    if not database.exists():
        return {"ok": False, "errors": ["index is missing"]}
    connection = sqlite3.connect(database)
    errors: list[str] = []
    for relative, expected in connection.execute("SELECT path, content_hash FROM documents"):
        path = root / relative
        if not path.exists():
            errors.append(f"missing document: {relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"hash mismatch: {relative}")
    connection.close()
    return {"ok": not errors, "errors": errors}
