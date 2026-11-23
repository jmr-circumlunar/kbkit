"""Portable schedule metadata; the Agent host owns timers and execution policy."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .storage import metadata_dir
from .transaction import write_atomic


def configure(
    root: Path,
    host: str,
    schedule: str,
    enabled: bool = True,
    auto_apply: str = "safe",
    generated_content: str = "disabled",
    generated_root: str = "_generated",
) -> dict:
    if not host.strip() or not schedule.strip():
        raise ValueError("host and schedule are required")
    if auto_apply not in {"none", "safe"}:
        raise ValueError("auto_apply must be 'none' or 'safe'")
    if generated_content not in {"disabled", "enabled"}:
        raise ValueError("generated_content must be 'disabled' or 'enabled'")
    if not generated_root.strip() or Path(generated_root).is_absolute() or ".." in Path(generated_root).parts:
        raise ValueError("generated_root must be a relative vault path")
    config = metadata_dir(root) / "automation.json"
    record = {
        "task_id": str(uuid.uuid4()),
        "host": host,
        "schedule": schedule,
        "enabled": enabled,
        "auto_apply": auto_apply,
        "generated_content": generated_content,
        "generated_root": generated_root,
        "version": 1,
    }
    write_atomic(config, json.dumps(record, indent=2).encode("utf-8"))
    return record


def load(root: Path) -> dict | None:
    config = metadata_dir(root) / "automation.json"
    try:
        record = json.loads(config.read_bytes())
    except FileNotFoundError:
        return None
    if not isinstance(record, dict) or type(record.get("enabled")) is not bool:
        raise ValueError("automation.json must contain a boolean enabled setting")
    if record.get("auto_apply") not in ("none", "safe"):
        raise ValueError("automation.json auto_apply must be 'none' or 'safe'")
    return record


def resolve_auto_apply(root: Path, override: str | None) -> str:
    if override is not None:
        if override not in ("none", "safe"):
            raise ValueError("auto_apply must be 'none' or 'safe'")
        return override
    record = load(root)
    return record["auto_apply"] if record and record["enabled"] else "none"
