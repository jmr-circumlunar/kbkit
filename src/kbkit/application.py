"""Unified application service used by CLI and MCP adapters."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .core import build_index, init_vault, maintain, read, search_details
from .knowledge import KnowledgeVault
from .registry import VaultRegistry
from .state import StateStore
from .writer import apply_proposal
from .transaction import apply_plan, plan_operations
from .consistency import check_consistency
from .graph import build_graph, outline
from .lint import lint


class ApplicationService:
    def __init__(self, vault: Path) -> None:
        self.vault = vault.resolve()

    def initialize(self) -> dict:
        profile = init_vault(self.vault)
        with closing(VaultRegistry()) as registry:
            vault_uuid = registry.add(self.vault)
        return {"vault_uuid": vault_uuid, "profile": str(profile)}

    def index(self) -> dict:
        return {"blocks": build_index(self.vault)}

    def search(self, query: str, include_inactive: bool = False) -> dict:
        return {"hits": search_details(self.vault, query, include_inactive)}

    def read(self, relative_path: str) -> dict:
        return {"path": relative_path, "content": read(self.vault, relative_path),
                **KnowledgeVault(self.vault).statuses().get(Path(relative_path).as_posix(), {})}

    def status(self) -> dict:
        return {"vault": str(self.vault), "initialized": (self.vault / ".kbkit" / "profile.toml").exists(),
                "knowledge": KnowledgeVault(self.vault).statuses()}

    def maintain(self) -> dict:
        return maintain(self.vault)

    def proposals(self, status: str | None = None) -> dict:
        store = StateStore(self.vault)
        rows = store.list_proposals(status)
        store.close()
        return {"proposals": rows}

    def apply_proposal(self, proposal_id: str) -> dict:
        return self._refresh_after_write(apply_proposal(self.vault, proposal_id))

    def plan_operations(self, operations: list[dict]) -> dict:
        plan = plan_operations(self.vault, operations, dry_run=True)
        return {"transaction_id": plan["transaction_id"], "dry_run": True, "changes": [change.relative_path for change in plan["changes"]]}

    def apply_operations(self, operations: list[dict]) -> dict:
        plan = plan_operations(self.vault, operations, dry_run=False)
        return self._refresh_after_write(apply_plan(self.vault, plan))

    def _refresh_after_write(self, result: dict) -> dict:
        try:
            build_index(self.vault)
            result["consistency"] = check_consistency(self.vault)
        except (OSError, sqlite3.Error, ValueError) as error:
            result["consistency"] = {"ok": False, "errors": [str(error)]}
        result["index_dirty"] = not result["consistency"]["ok"]
        if result["index_dirty"]:
            result["index_hint"] = "The transaction state is reported separately. Fix the index error and run kb_index."
        return result

    def graph(self) -> dict:
        return build_graph(self.vault)

    def outline(self, relative_path: str) -> dict:
        return {"path": relative_path, "outline": outline(self.vault, relative_path)}

    def lint(self) -> dict:
        return {"findings": lint(self.vault)}
