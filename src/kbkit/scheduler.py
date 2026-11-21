"""Agent-host scheduler configuration records."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .storage import metadata_dir


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
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def load(root: Path) -> dict | None:
    config = metadata_dir(root) / "automation.json"
    return json.loads(config.read_text(encoding="utf-8")) if config.exists() else None
