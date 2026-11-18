"""Local vault registry used by Agent and CLI entry points."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .vault_profile import assign_copy_id, vault_id


class VaultRegistry:
    def __init__(self, location: Path | None = None) -> None:
        configured = os.environ.get("KBKIT_REGISTRY_DIR")
        base = location or (Path(configured) if configured else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "kbkit")
        base.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(base / "registry.sqlite")
        self.connection.execute("CREATE TABLE IF NOT EXISTS vaults (vault_uuid TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS active_vault (slot INTEGER PRIMARY KEY CHECK(slot = 1), vault_uuid TEXT)")
        self.connection.commit()

    def add(self, root: Path, name: str | None = None, *, identity: str | None = None) -> str:
        if identity not in {None, "moved", "copy"}:
            raise ValueError("identity must be moved or copy")
        root = root.resolve()
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            value = vault_id(root)
            previous = self.connection.execute("SELECT path FROM vaults WHERE vault_uuid = ?", (value,)).fetchone()
            different_location = previous is not None and Path(previous[0]) != root
            if different_location and identity is None:
                raise ValueError("vault UUID already registered at a different path; choose --identity moved or --identity copy")
            if identity == "moved" and different_location and (Path(previous[0]) / ".kbkit" / "profile.toml").is_file():
                raise ValueError("the original vault still exists; register this as a copy")
            if identity == "copy" and (different_location or previous is None):
                registered = self.connection.execute("SELECT 1 FROM vaults WHERE path = ?", (str(root),)).fetchone()
                if registered:
                    raise ValueError("this path is already registered with a different UUID")
                value = assign_copy_id(root)
            self.connection.execute(
                "INSERT INTO vaults VALUES (?, ?, ?) ON CONFLICT(vault_uuid) DO UPDATE SET path = excluded.path, name = excluded.name",
                (value, str(root), name or root.name),
            )
            self.connection.execute("INSERT OR REPLACE INTO active_vault(slot, vault_uuid) VALUES (1, ?)", (value,))
        return value

    def current(self) -> Path | None:
        row = self.connection.execute("SELECT path FROM vaults WHERE vault_uuid = (SELECT vault_uuid FROM active_vault WHERE slot = 1)").fetchone()
        return Path(row[0]) if row else None

    def use(self, vault_uuid: str) -> Path:
        row = self.connection.execute("SELECT path FROM vaults WHERE vault_uuid = ?", (vault_uuid,)).fetchone()
        if row is None:
            raise ValueError("vault is not registered")
        self.connection.execute("INSERT OR REPLACE INTO active_vault(slot, vault_uuid) VALUES (1, ?)", (vault_uuid,))
        self.connection.commit()
        return Path(row[0])

    def close(self) -> None:
        self.connection.close()
