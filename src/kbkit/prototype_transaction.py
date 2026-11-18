"""E2 prototype for a recoverable single-file redo journal."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_with_journal(target: Path, replacement: bytes, journal: Path) -> None:
    before = target.read_bytes() if target.exists() else b""
    record = {"target": str(target), "before_hash": _digest(before), "after_hash": _digest(replacement), "state": "pending"}
    journal.write_text(json.dumps(record), encoding="utf-8")
    temporary = target.with_name(target.name + ".kbkit-staging")
    temporary.write_bytes(replacement)
    os.replace(temporary, target)
    record["state"] = "applied"
    journal.write_text(json.dumps(record), encoding="utf-8")


def recover(journal: Path) -> str:
    record = json.loads(journal.read_text(encoding="utf-8"))
    target = Path(record["target"])
    current = target.read_bytes() if target.exists() else b""
    current_hash = _digest(current)
    if current_hash == record["after_hash"]:
        record["state"] = "applied"
        journal.write_text(json.dumps(record), encoding="utf-8")
        return "applied"
    if current_hash == record["before_hash"]:
        return "pending"
    record["state"] = "divergent"
    journal.write_text(json.dumps(record), encoding="utf-8")
    return "divergent"
