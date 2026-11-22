"""Local vault registry used by Agent and CLI entry points."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .storage import app_data_dir, metadata_dir

from .vault_profile import assign_copy_id, vault_id


class VaultRegistry:
    def __init__(self, location: Path | None = None) -> None:
        configured = os.environ.get("KBKIT_REGISTRY_DIR")
        base = location or (Path(configured).expanduser() if configured else app_data_dir("data"))
        legacy = Path.home() / "kbkit"
        if location is None and not configured and not (base / "registry.sqlite").exists() and (legacy / "registry.sqlite").is_file():
            base = legacy
        base.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(base / "registry.sqlite")
        self.connection.execute("CREATE TABLE IF NOT EXISTS vaults (vault_uuid TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS active_vault (slot INTEGER PRIMARY KEY CHECK(slot = 1), vault_uuid TEXT)")
        self.connection.commit()

    def add(self, root: Path, name: str | None = None, *, identity: str | None = None, moved_from: Path | None = None) -> str:
        if identity not in {None, "moved", "copy"}:
            raise ValueError("identity must be moved or copy")
        root = root.resolve()
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            if moved_from is not None and identity != "moved":
                raise ValueError("--from requires --identity moved")
            if identity == "moved" and not (metadata_dir(root) / "profile.toml").is_file():
                self._relocate_external_state(root, moved_from)
            value = vault_id(root)
            previous = self.connection.execute("SELECT path FROM vaults WHERE vault_uuid = ?", (value,)).fetchone()
            different_location = previous is not None and Path(previous[0]) != root
            if different_location and identity is None:
                raise ValueError("vault UUID already registered at a different path; choose --identity moved or --identity copy")
            if identity == "moved" and different_location and Path(previous[0]).is_dir() and (metadata_dir(Path(previous[0])) / "profile.toml").is_file():
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

    def _relocate_external_state(self, root: Path, moved_from: Path | None) -> None:
        target = metadata_dir(root)
        if target == root / ".kbkit" or not root.is_dir():
            raise ValueError("move the vault directory first and use its original KBKIT_HOME")
        paths = (
            [moved_from.resolve()] if moved_from is not None else
            [Path(row[0]) for row in self.connection.execute("SELECT path FROM vaults")]
        )
        present = [old for old in paths if old != root and not old.exists() and (metadata_dir(old) / "profile.toml").is_file()]
        if len(present) != 1:
            raise ValueError("cannot identify the previous external state; use --from with the original vault path")
        old = present[0]
        state = metadata_dir(old)
        previous = self.connection.execute("SELECT vault_uuid FROM vaults WHERE path = ?", (str(old),)).fetchone()
        if previous is None or vault_id(old) != previous[0]:
            raise ValueError("old path and vault UUID do not match the registry")
        if target.exists():
            if target.is_dir() and not any(target.iterdir()):
                target.rmdir()
            else:
                raise ValueError("destination already has a different metadata directory")
        state.rename(target)

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
