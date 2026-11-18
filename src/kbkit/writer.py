"""E3 safe proposal application for low-risk append operations."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .prototype_transaction import apply_with_journal
from .state import StateStore


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_proposal(root: Path, proposal_id: str) -> dict:
    state = StateStore(root)
    proposal = state.get_proposal(proposal_id)
    if proposal is None:
        state.close()
        raise ValueError("proposal not found")
    _, risk_level, _, status, payload_json = proposal
    if status != "approved":
        state.close()
        raise ValueError("proposal must be approved")
    if risk_level != "low":
        state.close()
        raise ValueError("only low-risk proposals are supported")
    import json

    payload = json.loads(payload_json)
    if payload.get("operation") != "append":
        state.close()
        raise ValueError("unsupported proposal operation")
    target = (root / payload["path"]).resolve()
    if root.resolve() not in target.parents or target.suffix.lower() != ".md":
        state.close()
        raise ValueError("proposal path is outside the vault")
    current = target.read_bytes()
    if _hash(current) != payload["expected_hash"]:
        state.set_proposal_status(proposal_id, "conflicted")
        state.close()
        raise ValueError("proposal expected_hash does not match")
    journal = root / ".kbkit" / "transactions" / f"{proposal_id}.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    apply_with_journal(target, current + payload["content"].encode("utf-8"), journal)
    state.set_proposal_status(proposal_id, "applied")
    state.close()
    return {"proposal_id": proposal_id, "status": "applied", "path": payload["path"]}
