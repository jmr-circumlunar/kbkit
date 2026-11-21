"""Atomic file writes and recoverable multi-file Markdown transactions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Callable

from .prototype_lock import file_lock
from .prototype_markdown import parse_document, set_frontmatter_field
from .selector import markdown_path, resolve_source, source_lines
from .storage import metadata_dir


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: Path, data: bytes, *, exclusive: bool = False, verify: Callable[[], None] | None = None) -> None:
    """Publish a complete file on the target volume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".kbkit-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if verify is not None:
            verify()
        if exclusive:
            os.link(name, path)
        else:
            Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def _save_json(path: Path, record: dict) -> None:
    write_atomic(path, json.dumps(record, ensure_ascii=False).encode("utf-8"))


@dataclass(frozen=True)
class PlannedChange:
    relative_path: str
    before_hash: str | None
    after: bytes | None
    operation: str
    position: dict | None = None
    preview: dict | None = None


class TransactionError(ValueError):
    pass


def _current_hash(target: Path) -> str | None:
    try:
        return digest(target.read_bytes())
    except FileNotFoundError:
        return None


def delete_to_trash(root: Path, relative_path: str) -> dict:
    plan = plan_operations(root, [{"operation": "delete", "path": relative_path}])
    result = apply_plan(root, plan)
    if result["state"] != "applied":
        raise TransactionError("delete diverged; inspect the transaction journal")
    return {"entry_id": result["trash"][0]["entry_id"], "status": "trashed", "path": relative_path}


def restore_from_trash(root: Path, entry_id: str) -> dict:
    if str(uuid.UUID(entry_id)) != entry_id:
        raise TransactionError("invalid trash entry ID")
    trash_dir = metadata_dir(root) / "trash"
    with file_lock(_lock_path(root)):
        manifest = trash_dir / f"{entry_id}.json"
        if not manifest.is_file():
            raise TransactionError("trash entry not found")
        record = json.loads(manifest.read_bytes())
        target = markdown_path(root, record["original"], allow_missing=True)
        trash_path = trash_dir / Path(record["trash"]).name
        data = trash_path.read_bytes()
        if digest(data) != record["before_hash"]:
            raise TransactionError("trash content hash mismatch")
        try:
            write_atomic(target, data, exclusive=True)
        except FileExistsError as exc:
            raise TransactionError("restore target already exists") from exc
        manifest.unlink()
        trash_path.unlink()
    return {"entry_id": entry_id, "status": "restored", "path": record["original"]}


def _append_preview(before: bytes, end: int, content: str, *, targeted: bool) -> tuple[bytes, dict, dict]:
    lines = source_lines(before)
    offset = sum(map(len, lines[:end]))
    prefix, suffix = before[:offset], before[offset:]
    inserted = content.encode("utf-8")
    if targeted and inserted:
        newline = b"\r\n" if lines[end - 1].endswith(b"\r\n") else b"\n"
        if prefix and not prefix.endswith((b"\n", b"\r")) and not inserted.startswith((b"\n", b"\r")):
            inserted = newline + inserted
        if suffix and not inserted.endswith((b"\n", b"\r")):
            inserted += newline
    position = {"after_line": end, "byte_offset": offset, "inserted_bytes": len(inserted)}
    preview = {
        "before": b"".join(lines[max(0, end - 3):end])[-360:].decode("utf-8", errors="replace"),
        "insert": inserted[:360].decode("utf-8", errors="replace"),
        "after": b"".join(lines[end:end + 3])[:360].decode("utf-8", errors="replace"),
    }
    preview["diff"] = _diff(preview["before"] + preview["after"],
                            preview["before"] + preview["insert"] + preview["after"])
    return prefix + inserted + suffix, position, preview


def _diff(before: str, after: str) -> str:
    changes = unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=3)
    return "\n".join(changes)[:450]


def plan_append(root: Path, operations: list[dict], dry_run: bool = True) -> dict:
    if any(operation.get("operation") != "append" for operation in operations):
        raise TransactionError("unsupported operation")
    return plan_operations(root, operations, dry_run)


def plan_operations(root: Path, operations: list[dict], dry_run: bool = True) -> dict:
    root = root.resolve()
    if not isinstance(operations, list) or not 1 <= len(operations) <= 50:
        raise TransactionError("supply between 1 and 50 operations")
    changes: list[PlannedChange] = []
    seen: set[str] = set()

    def reserve(target: Path) -> str:
        relative = target.relative_to(root).as_posix()
        if len(relative.encode("utf-8")) > 512:
            raise TransactionError("transaction paths must be at most 512 UTF-8 bytes")
        key = os.path.normcase(relative)
        if key in seen:
            raise TransactionError(f"repeated transaction path: {relative}")
        seen.add(key)
        return relative

    for operation in operations:
        if not isinstance(operation, dict):
            raise TransactionError("each operation must be an object")
        kind = operation.get("operation")
        if kind not in ("create", "append", "delete", "move", "rename", "set_prop"):
            raise TransactionError("unsupported operation")
        by_kind = {
            "create": {"content"}, "append": {"content"}, "delete": set(),
            "move": {"destination"}, "rename": {"destination"}, "set_prop": {"property", "value"},
        }
        unknown = operation.keys() - {"operation", "path", "selector", "expected_hash"} - by_kind[kind]
        if unknown:
            raise TransactionError(f"unexpected fields for {kind}: {', '.join(sorted(unknown))}")
        if ("selector" in operation) == ("path" in operation):
            raise TransactionError("supply exactly one of path or selector")
        selector = operation["selector"] if "selector" in operation else {"path": operation["path"]}
        target, selection, before = resolve_source(root, selector, allow_missing_path=kind == "create")
        relative = reserve(target)
        expected = operation.get("expected_hash")
        if expected is not None and expected != digest(before):
            raise TransactionError(f"hash conflict: {relative}")
        before_hash = digest(before)
        targeted = set(selector) != {"path"}
        if targeted and kind != "append":
            raise TransactionError("section, block and line selectors are supported for append only")
        if targeted and selection.end < len(source_lines(parse_document(before).prefix)):
            raise TransactionError("append would modify the frontmatter; use set_prop for a scalar field")
        if kind in {"create", "append"}:
            content = operation.get("content")
            if not isinstance(content, str) or not content:
                raise TransactionError(f"{kind} requires nonempty text content")
            if kind == "create":
                if target.exists() or not target.parent.is_dir():
                    raise TransactionError("create requires a new Markdown path in an existing directory")
                before_hash = None
            after, position, preview = _append_preview(before, selection.end, content, targeted=targeted)
            changes.append(PlannedChange(relative, before_hash, after, kind, position, preview))
        elif kind == "set_prop":
            after = set_frontmatter_field(before, operation.get("property"), operation.get("value"))
            old_lines, new_lines = source_lines(before), source_lines(after)
            row = next((index for index, (old, new) in enumerate(zip(old_lines, new_lines)) if old != new), 0)
            previous = b"".join(old_lines[max(0, row-3):row+4])[:360].decode("utf-8", errors="replace")
            updated = b"".join(new_lines[max(0, row-3):row+4])[:360].decode("utf-8", errors="replace")
            changes.append(PlannedChange(relative, before_hash, after, kind, preview={
                "before": previous, "after": updated, "diff": _diff(previous, updated),
            }))
        elif kind == "delete":
            changes.append(PlannedChange(relative, before_hash, None, kind))
        else:
            destination = markdown_path(root, operation.get("destination"), allow_missing=True)
            if destination.exists():
                raise TransactionError("destination already exists")
            changes.append(PlannedChange(reserve(destination), None, before, kind))
            changes.append(PlannedChange(relative, before_hash, None, kind))
    fingerprint = [[c.relative_path, c.before_hash, None if c.after is None else digest(c.after), c.operation, c.position] for c in changes]
    return {"transaction_id": str(uuid.uuid4()), "plan_hash": digest(json.dumps(fingerprint).encode()),
            "dry_run": dry_run, "changes": changes}


def _lock_path(root: Path) -> Path:
    path = metadata_dir(root) / "write.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def apply_plan(root: Path, plan: dict, fail_after: int | None = None) -> dict:
    with file_lock(_lock_path(root)):
        return _apply_plan(root.resolve(), plan, fail_after)


def _apply_plan(root: Path, plan: dict, fail_after: int | None) -> dict:
    changes = plan["changes"]
    for change in changes:
        target = markdown_path(root, change.relative_path, allow_missing=True)
        if _current_hash(target) != change.before_hash:
            raise TransactionError(f"concurrent edit or creation: {change.relative_path}")
    transaction_id = plan["transaction_id"]
    transaction_dir = metadata_dir(root) / "transactions"
    journal = transaction_dir / f"{transaction_id}.json"
    staging_dir = transaction_dir / transaction_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, change in enumerate(changes):
        record = {"path": change.relative_path, "before_hash": change.before_hash}
        if change.after is not None:
            staging = staging_dir / f"{index}.after"
            write_atomic(staging, change.after)
            record.update(staging=str(staging), after_hash=digest(change.after))
        else:
            record["after_hash"] = None
            record["quarantine"] = f".kbkit-{transaction_id}-{index}.removed"
        if change.operation == "delete":
            record["trash_id"] = str(uuid.uuid5(uuid.UUID(transaction_id), change.relative_path))
        records.append(record)
    data = {"version": 2, "state": "pending", "transaction_id": transaction_id, "changes": records}
    _save_json(journal, data)
    state = _recover(root, journal, data, fail_after)
    result = {"transaction_id": transaction_id, "state": state, "paths": [c.relative_path for c in changes]}
    if state == "applied":
        result["positions"] = [{"path": c.relative_path, **c.position} for c in changes if c.position is not None]
        result["trash"] = [{"path": c["path"], "entry_id": c["trash_id"]} for c in records if "trash_id" in c]
    return result


def _trash(root: Path, data: bytes, change: dict) -> None:
    entry_id = change["trash_id"]
    trash = metadata_dir(root) / "trash"
    filename = f"{entry_id}.md"
    write_atomic(trash / filename, data)
    _save_json(trash / f"{entry_id}.json", {
        "entry_id": entry_id, "original": change["path"], "trash": filename, "before_hash": change["before_hash"],
    })


def recover_transaction(root: Path, journal: Path) -> str:
    with file_lock(_lock_path(root)):
        record = json.loads(journal.read_bytes())
        if "target" in record:
            from .prototype_transaction import recover

            return recover(journal)
        return _recover(root.resolve(), journal, record)


def _divergent(journal: Path, record: dict) -> str:
    record["state"] = "divergent"
    _save_json(journal, record)
    return "divergent"


def _restore_quarantine(parked: Path, target: Path) -> None:
    """Restore an externally edited file without ever overwriting a new one."""
    try:
        os.link(parked, target)
    except FileExistsError:
        return
    parked.unlink()


def _recover(root: Path, journal: Path, record: dict, fail_after: int | None = None) -> str:
    if record["state"] == "applied":
        return "applied"
    work = []
    legacy = record.get("version") != 2
    for change in record["changes"]:
        target = markdown_path(root, change["path"], allow_missing=True)
        before_hash, after_hash = change["before_hash"], change["after_hash"]
        if change.get("create_only"):
            before_hash = None
        current = _current_hash(target)
        quarantine = target.with_name(change["quarantine"]) if "quarantine" in change else None
        if quarantine and quarantine.exists():
            if current is not None:
                return _divergent(journal, record)
            current = _current_hash(quarantine)
            if current != before_hash:
                _restore_quarantine(quarantine, target)
                return _divergent(journal, record)
        if after_hash is None and current is None and "trash_id" in change:
            manifest = metadata_dir(root) / "trash" / f"{change['trash_id']}.json"
            if not manifest.is_file():
                return _divergent(journal, record)
        if legacy and current is None and before_hash == digest(b""):
            current = before_hash
        if current not in (before_hash, after_hash):
            return _divergent(journal, record)
        work.append((target, change, current, after_hash, quarantine))
    for index, (target, change, current, after_hash, quarantine) in enumerate(work):
        if fail_after is not None and index >= fail_after:
            raise RuntimeError("fault injection")
        if current == after_hash:
            continue
        if after_hash is None:
            if not quarantine.exists():
                try:
                    target.replace(quarantine)
                except FileNotFoundError:
                    return _divergent(journal, record)
            data = quarantine.read_bytes()
            if digest(data) != current:
                _restore_quarantine(quarantine, target)
                return _divergent(journal, record)
            if "trash_id" in change:
                _trash(root, data, change)
            quarantine.unlink()
        else:
            after = Path(change["staging"]).read_bytes()
            if digest(after) != after_hash:
                raise TransactionError("staged image hash mismatch")

            def recheck():
                actual = _current_hash(target)
                if actual != current and not (legacy and actual is None and current == digest(b"")):
                    raise TransactionError(f"concurrent edit: {change['path']}")

            try:
                write_atomic(target, after, exclusive=current is None, verify=recheck if current is not None else None)
            except (FileExistsError, TransactionError):
                return _divergent(journal, record)
    if any(_current_hash(target) != after_hash for target, _, _, after_hash, _ in work):
        return _divergent(journal, record)
    record["state"] = "applied"
    _save_json(journal, record)
    return "applied"
