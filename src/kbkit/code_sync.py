"""Refresh scoped implementation evidence from committed Git objects."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from subprocess import TimeoutExpired

from .git_adapter import GitUnavailable, read_objects
from .knowledge import KnowledgeVault
from .transaction import PlannedChange, apply_plan, digest


def bind_code(vault: KnowledgeVault, source: str, repo: Path, ref: str, scopes: list[str]) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", source):
        raise ValueError("source ID must use lowercase letters, numbers and hyphens")
    if not ref.startswith(("refs/heads/", "refs/remotes/", "refs/tags/")):
        raise ValueError("use a full local Git ref, for example refs/heads/main")
    repo = repo.resolve(strict=True)
    git_root = read_objects(repo, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
    if Path(git_root).resolve() != repo:
        raise ValueError("bind the repository root")
    read_objects(repo, ["show-ref", "--verify", "--", ref])
    if not scopes or any(not Path(scope).parts or Path(scope).anchor or
                         ".." in Path(scope).parts or "\\" in scope for scope in scopes):
        raise ValueError("choose explicit repo-relative source paths using forward slashes")
    page = vault.markdown_path(f"_generated/code/{source}.md")
    sources = vault.data["code"]
    previous = sources.get(source, {})
    if page in vault.data["pages"] or (not previous and (vault.root / page).exists()):
        raise ValueError("generated page path is already in use")
    entry = {**previous, "repository": str(repo), "ref": ref, "scopes": sorted(set(scopes)), "page": page}
    if entry != previous:
        sources[source] = {**entry, "issue": "binding_changed"}
        vault.save()
    return {"source": source, "page": page, "ref": ref, "scopes": entry["scopes"]}


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace(chr(96), "\\u0060")


def _implementation_page(source: str, repo: Path, ref: str, commit: str, entries: list[tuple]) -> bytes:
    lines = [
        "---", "type: reference", "state: active", f"source: git:{source}@{commit}", "---",
        "", f"# Implementation map: {source}", "", f"Git ref: {_literal(ref)}",
        f"Commit: {commit}", "", "## Committed files and Python entry points", "",
    ]
    if not entries:
        lines.append("No regular files currently match the authorized paths.")
    for path, blob, size in entries[:60]:
        label = f"- {_literal(path)} (blob {blob[:12]})"
        if path.endswith(".py") and size <= 262144:
            try:
                tree = ast.parse(read_objects(repo, ["cat-file", "blob", blob]))
            except (SyntaxError, UnicodeError, ValueError):
                label += " — Python symbols unavailable"
            else:
                symbols = [
                    f"{node.name} (line {node.lineno})" for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and not node.name.startswith("_")
                ]
                if symbols:
                    label += " — " + ", ".join(symbols[:8])
                    if len(symbols) > 8:
                        label += f"; {len(symbols) - 8} more symbols in Git"
        lines.append(label)
    if len(entries) > 60:
        lines.append(f"- {len(entries) - 60} more scoped files in Git.")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _refresh(vault: KnowledgeVault, source: str, entry: dict) -> dict:
    import uuid

    repo = Path(entry["repository"])
    ref = entry["ref"]
    page = entry["page"]
    target = vault.root / vault.markdown_path(page)
    before = target.read_bytes() if target.exists() else None
    before_hash = digest(before) if before is not None else None
    git_root = read_objects(repo, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
    if Path(git_root).resolve() != repo:
        raise GitUnavailable("bound repository root changed")
    commit = read_objects(repo, ["rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"]).decode("ascii").strip()
    if commit == entry.get("checked_commit") and before_hash == entry.get("page_hash") and before is not None and not entry.get("issue"):
        return {"source": source, "page": page, "status": "unchanged", "commit": commit}
    raw = read_objects(repo, ["ls-tree", "-rlz", commit, "--", *entry["scopes"]])
    entries = []
    for row in raw.rstrip(b"\0").split(b"\0") if raw else ():
        header, filename = row.split(b"\t", 1)
        mode, kind, blob, size = header.split()
        if kind == b"blob" and mode in {b"100644", b"100755"}:
            entries.append((filename.decode("utf-8"), blob.decode("ascii"), int(size)))
    source_hash = digest(raw)
    previous_commit = entry.get("page_commit")
    previous_hash = entry.get("page_hash")
    if source_hash == entry.get("source_hash") and before is not None and before_hash == previous_hash and entry.get("issue") != "binding_changed":
        entry.update(checked_commit=commit, issue=None)
        return {"source": source, "page": page, "status": "unchanged", "commit": commit}
    after = _implementation_page(source, repo, ref, commit, entries)
    after_hash = digest(after)
    if before_hash != previous_hash and before_hash != after_hash:
        entry["issue"] = "generated_page_changed"
        return {"source": source, "page": page, "status": "conflicted", "commit": commit}
    if before_hash != after_hash:
        target.parent.mkdir(parents=True, exist_ok=True)
        plan = {
            "transaction_id": str(uuid.uuid4()), "dry_run": False,
            "changes": [PlannedChange(page, before_hash, after, "code_refresh")],
        }
        result = apply_plan(vault.root, plan)
        if result["state"] != "applied":
            entry["issue"] = "generated_page_changed"
            return {"source": source, "page": page, "status": "conflicted", "commit": commit}
        transaction_id = result["transaction_id"]
    else:
        transaction_id = None
    entry.update(checked_commit=commit, page_commit=commit, page_hash=after_hash, source_hash=source_hash, issue=None)
    return {"source": source, "page": page, "status": "updated", "commit": commit, "previous_commit": previous_commit,
            "before_hash": previous_hash, "after_hash": after_hash, "source_hash": source_hash,
            "transaction_id": transaction_id}


def refresh_code(vault: KnowledgeVault) -> list[dict]:
    results = []
    for source, entry in sorted(vault.data["code"].items()):
        previous = entry.copy()
        try:
            result = _refresh(vault, source, entry)
        except (GitUnavailable, OSError, TimeoutExpired, ValueError) as exc:
            entry["issue"] = "source_unavailable"
            result = {"source": source, "page": entry["page"], "status": "unverified", "error": str(exc)}
        if entry != previous:
            vault.save()
        results.append(result)
    return results
