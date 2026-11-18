"""Unified application service used by CLI and MCP adapters."""

from __future__ import annotations

from pathlib import Path

from .core import build_index, init_vault, maintain, read, search
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
        registry = VaultRegistry()
        vault_uuid = registry.add(self.vault)
        registry.close()
        return {"vault_uuid": vault_uuid, "profile": str(profile)}

    def index(self) -> dict:
        return {"blocks": build_index(self.vault)}

    def search(self, query: str) -> dict:
        return {"hits": [{"path": path, "block_id": block_id, "content": content} for path, block_id, content in search(self.vault, query)]}

    def read(self, relative_path: str) -> dict:
        return {"path": relative_path, "content": read(self.vault, relative_path)}

    def status(self) -> dict:
        return {"vault": str(self.vault), "initialized": (self.vault / ".kbkit" / "profile.toml").exists()}

    def maintain(self) -> dict:
        return maintain(self.vault)

    def proposals(self, status: str | None = None) -> dict:
        store = StateStore(self.vault)
        rows = store.list_proposals(status)
        store.close()
        return {"proposals": rows}

    def apply_proposal(self, proposal_id: str) -> dict:
        result = apply_proposal(self.vault, proposal_id)
        build_index(self.vault)
        return result

    def plan_operations(self, operations: list[dict]) -> dict:
        plan = plan_operations(self.vault, operations, dry_run=True)
        return {"transaction_id": plan["transaction_id"], "dry_run": True, "changes": [change.relative_path for change in plan["changes"]]}

    def apply_operations(self, operations: list[dict]) -> dict:
        plan = plan_operations(self.vault, operations, dry_run=False)
        result = apply_plan(self.vault, plan)
        build_index(self.vault)
        result["consistency"] = check_consistency(self.vault)
        return result

    def graph(self) -> dict:
        return build_graph(self.vault)

    def outline(self, relative_path: str) -> dict:
        return {"path": relative_path, "outline": outline(self.vault, relative_path)}

    def lint(self) -> dict:
        return {"findings": lint(self.vault)}
