"""Vault identity and location-bound derived index paths."""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
import uuid
from pathlib import Path

from .transaction import write_atomic


def vault_id(root: Path) -> str:
    profile = root / ".kbkit" / "profile.toml"
    with profile.open("rb") as stream:
        data = tomllib.load(stream)
    try:
        return str(uuid.UUID(data["vault_uuid"]))
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("vault profile has no valid vault_uuid") from exc


def assign_copy_id(root: Path) -> str:
    profile = root / ".kbkit" / "profile.toml"
    value = str(uuid.uuid4())
    original = vault_id(root)
    pattern = rb"(?m)^([ \t]*vault_uuid[ \t]*=[ \t]*)([\"'])([^\r\n]+?)\2"
    data, count = re.subn(pattern, lambda match: match[1] + f'"{value}"'.encode("ascii"), profile.read_bytes(), count=1)
    if count != 1 or tomllib.loads(data.decode("utf-8")).get("vault_uuid") != value:
        raise ValueError(f"cannot update the UUID field of vault {original}")
    write_atomic(profile, data)
    return value


def index_path(root: Path, *, create: bool = False) -> Path:
    configured = os.environ.get("KBKIT_INDEX_DIR")
    base = Path(configured) if configured else Path(os.environ.get("LOCALAPPDATA", root / ".kbkit")) / "kbkit" / "indexes"
    location = os.path.normcase(str(root.resolve())).encode("utf-8")
    folder = base / vault_id(root)
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{hashlib.sha256(location).hexdigest()}.sqlite"
