"""E4 multi-file operation planning and recovery primitives."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from .selector import resolve_selector


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PlannedChange:
    relative_path: str
    before_hash: str
    after: bytes


class TransactionError(ValueError):
    pass


def delete_to_trash(root: Path, relative_path: str) -> dict:
    target = (root / relative_path).resolve()
    if root.resolve() not in target.parents or target.suffix.lower() != ".md":
        raise TransactionError("path is outside the vault")
    if not target.exists():
        raise TransactionError("delete target does not exist")
    entry_id = str(uuid.uuid4())
    trash_dir = root / ".kbkit" / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    trash_path = trash_dir / f"{entry_id}-{target.name}"
    before_hash = digest(target.read_bytes())
    target.replace(trash_path)
    manifest = trash_dir / f"{entry_id}.json"
    manifest.write_text(json.dumps({"entry_id": entry_id, "original": relative_path, "trash": str(trash_path), "before_hash": before_hash}), encoding="utf-8")
    return {"entry_id": entry_id, "status": "trashed", "path": relative_path}


def restore_from_trash(root: Path, entry_id: str) -> dict:
    trash_dir = root / ".kbkit" / "trash"
    manifest = trash_dir / f"{entry_id}.json"
    if not manifest.exists():
        raise TransactionError("trash entry not found")
    record = json.loads(manifest.read_text(encoding="utf-8"))
    target = (root / record["original"]).resolve()
    if target.exists():
        raise TransactionError("restore target already exists")
    trash_path = Path(record["trash"])
    if digest(trash_path.read_bytes()) != record["before_hash"]:
        raise TransactionError("trash content hash mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    trash_path.replace(target)
    manifest.unlink()
    return {"entry_id": entry_id, "status": "restored", "path": record["original"]}


def plan_append(root: Path, operations: list[dict], dry_run: bool = True) -> dict:
    changes: list[PlannedChange] = []
    seen: set[str] = set()
    for operation in operations:
        if operation.get("operation") != "append":
            raise TransactionError("unsupported operation")
        selector = operation.get("selector") or {"path": operation.get("path", "")}
        target = resolve_selector(root, selector)
        relative = target.relative_to(root).as_posix()
        if not relative or root.resolve() not in target.parents or target.suffix.lower() != ".md":
            raise TransactionError("path is outside the vault")
        if relative in seen:
            raise TransactionError("ambiguous repeated selector")
        seen.add(relative)
        before = target.read_bytes() if target.exists() else b""
        expected = operation.get("expected_hash")
        if expected and expected != digest(before):
            raise TransactionError(f"hash conflict: {relative}")
        after = before + operation.get("content", "").encode("utf-8")
        changes.append(PlannedChange(relative, digest(before), after))
    return {"transaction_id": str(uuid.uuid4()), "dry_run": dry_run, "changes": changes}


def plan_operations(root: Path, operations: list[dict], dry_run: bool = True) -> dict:
    changes: list[PlannedChange] = []
    seen: set[str] = set()
    for operation in operations:
        kind = operation.get("operation")
        selector = operation.get("selector") or {"path": operation.get("path", "")}
        target = resolve_selector(root, selector)
        relative = target.relative_to(root).as_posix()
        if not relative or root.resolve() not in target.parents or target.suffix.lower() != ".md":
            raise TransactionError("path is outside the vault")
        if relative in seen:
            raise TransactionError("ambiguous repeated selector")
        seen.add(relative)
        before = target.read_bytes() if target.exists() else b""
        if operation.get("expected_hash") and operation["expected_hash"] != digest(before):
            raise TransactionError(f"hash conflict: {relative}")
        if kind == "append":
            after = before + operation.get("content", "").encode("utf-8")
            changes.append(PlannedChange(relative, digest(before), after))
        elif kind == "delete":
            changes.append(PlannedChange(relative, digest(before), b""))
        elif kind in {"move", "rename"}:
            destination = operation.get("destination", "")
            destination_path = (root / destination).resolve()
            if root.resolve() not in destination_path.parents or destination_path.suffix.lower() != ".md":
                raise TransactionError("destination is outside the vault")
            if destination_path.exists():
                raise TransactionError("destination already exists")
            changes.append(PlannedChange(relative, digest(before), b""))
            changes.append(PlannedChange(destination, digest(b""), before))
        else:
            raise TransactionError("unsupported operation")
    return {"transaction_id": str(uuid.uuid4()), "dry_run": dry_run, "changes": changes}


def apply_plan(root: Path, plan: dict, fail_after: int | None = None) -> dict:
    changes: list[PlannedChange] = plan["changes"]
    for change in changes:
        target = (root / change.relative_path).resolve()
        current = target.read_bytes() if target.exists() else b""
        if digest(current) != change.before_hash:
            raise TransactionError(f"concurrent edit: {change.relative_path}")
    transaction_dir = root / ".kbkit" / "transactions"
    journal = transaction_dir / f"{plan['transaction_id']}.json"
    staging_dir = transaction_dir / plan["transaction_id"]
    staging_dir.mkdir(parents=True, exist_ok=True)
    journal_changes = []
    for index, change in enumerate(changes):
        staging = staging_dir / f"{index}.after"
        staging.write_bytes(change.after)
        journal_changes.append({"path": change.relative_path, "before_hash": change.before_hash, "after_hash": digest(change.after), "staging": str(staging)})
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"state": "pending", "transaction_id": plan["transaction_id"], "changes": journal_changes}), encoding="utf-8")
    if fail_after is not None:
        for index, change in enumerate(changes):
            if index >= fail_after:
                raise RuntimeError("fault injection")
            (root / change.relative_path).write_bytes(change.after)
        recover_transaction(root, journal)
    else:
        recover_transaction(root, journal)
    return {"transaction_id": plan["transaction_id"], "state": "applied", "paths": [c.relative_path for c in changes]}


def recover_transaction(root: Path, journal: Path) -> str:
    record = json.loads(journal.read_text(encoding="utf-8"))
    if record["state"] == "applied":
        return "applied"
    for change in record["changes"]:
        target = (root / change["path"]).resolve()
        current = target.read_bytes() if target.exists() else b""
        current_hash = digest(current)
        if current_hash == change["after_hash"]:
            continue
        if current_hash != change["before_hash"]:
            record["state"] = "divergent"
            journal.write_text(json.dumps(record), encoding="utf-8")
            return "divergent"
        target.write_bytes(Path(change["staging"]).read_bytes())
    record["state"] = "applied"
    journal.write_text(json.dumps(record), encoding="utf-8")
    return "applied"
