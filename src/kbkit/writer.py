"""Apply approved, hash-guarded maintenance proposals."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from uuid import UUID

from .graph import link_edit
from .profile import load_profile
from .prototype_lock import file_lock
from .selector import markdown_path
from .state import StateStore
from .storage import metadata_dir
from .transaction import PendingTransactionError, TransactionError, apply_plan, digest, find_journal, plan_operations, recover_transaction


def apply_proposal(root: Path, proposal_id: str) -> dict:
    proposal_id = str(UUID(proposal_id))
    root = root.resolve()
    with closing(StateStore(root)) as state, file_lock(metadata_dir(root) / "maintenance.lock"):
        return _apply_proposal_locked(root, state, proposal_id)


def is_automatic_fix(payload: object) -> bool:
    if (not isinstance(payload, dict) or not isinstance(payload.get("path"), str)
            or not isinstance(payload.get("expected_hash"), str)):
        return False
    fields = {"finding_rule", "operation", "path", "expected_hash"}
    if (payload.get("finding_rule"), payload.get("operation")) == ("FM-FINAL-NEWLINE", "append"):
        return set(payload) == fields | {"content"} and payload["content"] in ("\n", "\r\n")
    targets = payload.get("link_targets")
    return (set(payload) == fields | {"link_targets"} and payload["finding_rule"] == "LINT-L01"
            and payload["operation"] == "replace" and isinstance(targets, dict) and 1 <= len(targets) <= 32
            and all(isinstance(value, str) for value in targets.values()))


def _validate_link_policy(root: Path, payload: dict) -> None:
    profile = load_profile(root)
    if "LINT-L01" in profile.disabled_rules or profile.gates.area(payload["path"]) != "active":
        raise ValueError("configured link repair is no longer authorized for this path")
    for old, target in payload["link_targets"].items():
        if profile.gates.link_targets.get(old) != target:
            raise ValueError("configured link target changed; inspect the current gate report")
        markdown_path(root, target)


def _proposal_operation(root: Path, payload: dict) -> dict:
    if "link_targets" not in payload:
        return {key: value for key, value in payload.items() if key != "finding_rule"}
    raw = markdown_path(root, payload["path"]).read_bytes()
    if digest(raw) != payload["expected_hash"]:
        raise TransactionError(f"hash conflict: {payload['path']}")
    edit = link_edit(raw, payload["link_targets"])
    if edit is None:
        raise TransactionError("no safe Markdown link replacement matches the current note")
    lines, content, _ = edit
    return {"operation": "replace", "selector": {"path": payload["path"], "line_range": lines},
            "expected_hash": payload["expected_hash"], "content": content}


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
    if payload.get("operation") not in ("append", "set_prop", "replace") or not payload.get("expected_hash"):
        raise ValueError("this legacy finding has no executable fix; inspect it with kb_lint")
    if payload.get("operation") == "replace":
        if not is_automatic_fix(payload):
            raise ValueError("only verified link repairs can be performed through this proposal")
        _validate_link_policy(root, payload)
    journal = find_journal(root, proposal_id)
    if journal is not None:
        outcome = recover_transaction(root, journal)
    else:
        try:
            operation = _proposal_operation(root, payload)
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
                      rule=payload["finding_rule"])
        if "link_targets" in payload:
            result["link_targets"] = payload["link_targets"]
        else:
            result["append"] = payload["content"]
    state.set_proposal_status(proposal_id, "applied")
    return result
