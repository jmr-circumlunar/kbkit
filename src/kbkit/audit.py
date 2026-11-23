"""Record review results supplied by an Agent and link them to applied writes."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .profile import matches_prefix, prefix
from .prototype_lock import file_lock
from .selector import markdown_path
from .storage import metadata_dir
from .transaction import transaction_status, write_atomic
from .vault_profile import vault_id


AUDIT_CATEGORIES = ("stale", "incomplete", "incorrect")
AUDIT_DISPOSITIONS = ("pending", "applied", "dismissed", "failed")


def _text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} must contain 1–{limit} characters")
    return value.strip()


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a UUID")
    return str(UUID(value))


def _path(root: Path, run_id: str) -> Path:
    return metadata_dir(root) / "reports" / "audits" / f"{_uuid(run_id, 'run_id')}.json"


def _findings(root: Path, scope: tuple[str, ...], findings: list[dict], *, verify_receipts: bool) -> list[dict]:
    if not isinstance(findings, list) or len(findings) > 1000:
        raise ValueError("findings must be an array of at most 1000 entries")
    result = []
    transactions = {}
    for item in findings:
        if not isinstance(item, dict) or item.keys() - {"path", "category", "message", "disposition", "transaction_id"}:
            raise ValueError("each finding must contain path, category, message, disposition and optional transaction_id")
        path = markdown_path(root, item.get("path"), allow_missing=True).relative_to(root).as_posix()
        if "." not in scope and not matches_prefix(path, scope):
            raise ValueError(f"audit finding outside the declared scope: {path}")
        category, disposition = item.get("category"), item.get("disposition")
        if category not in AUDIT_CATEGORIES or disposition not in AUDIT_DISPOSITIONS:
            raise ValueError("each audit finding must have a supported category and disposition")
        record = {"path": path, "category": category, "message": _text(item.get("message"), "message", 1000),
                  "disposition": disposition}
        if disposition == "applied":
            identifier = _uuid(item.get("transaction_id"), "transaction_id")
            if verify_receipts:
                if identifier not in transactions:
                    transactions[identifier] = transaction_status(root, identifier)
                receipt = transactions[identifier]
                if receipt["state"] != "applied" or path not in receipt["paths"]:
                    raise ValueError(f"transaction did not apply a write to {path}")
            record["transaction_id"] = identifier
        elif "transaction_id" in item:
            raise ValueError("transaction_id is accepted for an applied finding")
        result.append(record)
    return result


def record_audit(root: Path, run_id: str, reviewer: str, scope: list[str], findings: list[dict]) -> dict:
    identity = vault_id(root)
    destination = _path(root, run_id)
    if not isinstance(scope, list) or not 1 <= len(scope) <= 50 or any(not isinstance(item, str) for item in scope):
        raise ValueError("scope must be a nonempty array of vault-relative prefixes or ['.']")
    areas = tuple(dict.fromkeys("." if item == "." else prefix(item) for item in scope))
    if sum(len(area.encode("utf-8")) for area in areas) > 2048:
        raise ValueError("audit scope exceeds 2048 UTF-8 bytes")
    person = _text(reviewer, "reviewer", 120)
    with file_lock(metadata_dir(root) / "maintenance.lock"):
        saved = json.loads(destination.read_bytes()) if destination.is_file() else None
        entries = _findings(root, areas, findings, verify_receipts=saved is None)
        content = {"run_id": _uuid(run_id, "run_id"), "vault_id": identity, "reviewer": person,
                   "scope": list(areas), "findings": entries}
        if saved is not None:
            if any(saved.get(key) != value for key, value in content.items()):
                raise ValueError("run_id already belongs to different audit results")
            return saved
        counts = Counter(item["disposition"] for item in entries)
        receipt = {**content, "recorded_at": datetime.now(timezone.utc).isoformat(),
                   "finding_counts": {name: counts[name] for name in AUDIT_DISPOSITIONS}}
        write_atomic(destination, json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8"), exclusive=True)
        return receipt


def read_audit(root: Path, run_id: str) -> dict:
    vault_id(root)
    return json.loads(_path(root, run_id).read_bytes())
