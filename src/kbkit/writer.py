"""Apply approved, hash-guarded maintenance proposals."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from uuid import UUID

from .prototype_lock import file_lock
from .state import StateStore
from .storage import metadata_dir
from .transaction import PendingTransactionError, TransactionError, apply_plan, find_journal, plan_operations, recover_transaction


def apply_proposal(root: Path, proposal_id: str) -> dict:
    proposal_id = str(UUID(proposal_id))
    root = root.resolve()
    with closing(StateStore(root)) as state, file_lock(metadata_dir(root) / "maintenance.lock"):
        return _apply_proposal_locked(root, state, proposal_id)


def is_automatic_fix(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and set(payload) == {"finding_rule", "operation", "path", "content", "expected_hash"}
        and payload["finding_rule"] == "FM-FINAL-NEWLINE"
        and payload["operation"] == "append"
        and payload["content"] in ("\n", "\r\n")
        and isinstance(payload["expected_hash"], str)
        and isinstance(payload["path"], str)
    )


def _apply_proposal_locked(root: Path, state: StateStore, proposal_id: str, *, automatic: bool = False) -> dict:
    proposal = state.get_proposal(proposal_id)
    if proposal is None:
        raise ValueError("proposal not found")
    _, risk, _, status, payload_json = proposal
    payload = json.loads(payload_json)
    if status == "applied":
        return {"proposal_id": proposal_id, "status": status, "path": payload["path"]}
    eligible = automatic and status == "pending" and is_automatic_fix(payload)
    if risk != "low" or (status != "approved" and not eligible):
        raise ValueError("approve a low-risk proposal before applying it")
    if automatic and not is_automatic_fix(payload):
        raise ValueError("proposal is outside the automatic maintenance rules")
    if payload.get("operation") not in {"append", "set_prop"} or not payload.get("expected_hash"):
        raise ValueError("this legacy finding has no executable fix; inspect it with kb_lint")
    journal = find_journal(root, proposal_id)
    if journal is not None:
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
    result = {"proposal_id": proposal_id, "status": "applied", "path": payload["path"]}
    if automatic:
        journal = find_journal(root, proposal_id)
        if journal is None:
            raise FileNotFoundError(f"transaction receipt not found: {proposal_id}")
        change = json.loads(journal.read_bytes())["changes"][0]
        result.update(transaction_id=proposal_id, before_hash=change["before_hash"], after_hash=change["after_hash"],
                      rule=payload["finding_rule"], append=payload["content"])
    state.set_proposal_status(proposal_id, "applied")
    return result
