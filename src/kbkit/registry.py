"""Local vault registry used by Agent and CLI entry points."""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path


class VaultRegistry:
    def __init__(self, location: Path | None = None) -> None:
        configured = os.environ.get("KBKIT_REGISTRY_DIR")
        base = location or (Path(configured) if configured else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "kbkit")
        base.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(base / "registry.sqlite")
        self.connection.execute("CREATE TABLE IF NOT EXISTS vaults (vault_uuid TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS active_vault (slot INTEGER PRIMARY KEY CHECK(slot = 1), vault_uuid TEXT)")
        self.connection.commit()

    def add(self, root: Path, name: str | None = None) -> str:
        profile = root / ".kbkit" / "profile.toml"
        if not profile.exists():
            raise ValueError("vault is not initialized")
        value = None
        for line in profile.read_text(encoding="utf-8").splitlines():
            if line.startswith("vault_uuid"):
                value = line.split('"', 2)[1]
                break
        if value is None:
            raise ValueError("vault profile has no vault_uuid")
        self.connection.execute("INSERT OR REPLACE INTO vaults VALUES (?, ?, ?)", (value, str(root.resolve()), name or root.name))
        self.connection.commit()
        self.connection.execute("INSERT OR REPLACE INTO active_vault(slot, vault_uuid) VALUES (1, ?)", (value,))
        self.connection.commit()
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
