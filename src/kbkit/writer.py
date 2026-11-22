"""Apply approved, hash-guarded maintenance proposals."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from uuid import UUID

from .prototype_lock import file_lock
from .state import StateStore
from .storage import metadata_dir
from .transaction import PendingTransactionError, TransactionError, apply_plan, plan_operations, recover_transaction


def apply_proposal(root: Path, proposal_id: str) -> dict:
    proposal_id = str(UUID(proposal_id))
    root = root.resolve()
    with closing(StateStore(root)) as state, file_lock(metadata_dir(root) / "maintenance.lock"):
        proposal = state.get_proposal(proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        _, risk, _, status, payload_json = proposal
        payload = json.loads(payload_json)
        if status == "applied":
            return {"proposal_id": proposal_id, "status": status, "path": payload["path"]}
        if status != "approved" or risk != "low":
            raise ValueError("approve a low-risk proposal before applying it")
        if payload.get("operation") not in {"append", "set_prop"} or not payload.get("expected_hash"):
            raise ValueError("this legacy finding has no executable fix; inspect it with kb_lint")
        journal = metadata_dir(root) / "transactions" / f"{proposal_id}.json"
        if journal.exists():
            outcome = recover_transaction(root, journal)
        else:
            try:
                operation = {key: value for key, value in payload.items() if key != "finding_rule"}
                plan = plan_operations(root, [operation], dry_run=False)
                plan["transaction_id"] = proposal_id
                outcome = apply_plan(root, plan)["state"]
            except PendingTransactionError:
                raise
            except (TransactionError, FileNotFoundError):
                state.set_proposal_status(proposal_id, "conflicted")
                raise
        if outcome != "applied":
            state.set_proposal_status(proposal_id, "conflicted")
            raise TransactionError("proposal conflicted; inspect the transaction journal")
        state.set_proposal_status(proposal_id, "applied")
        return {"proposal_id": proposal_id, "status": "applied", "path": payload["path"]}
