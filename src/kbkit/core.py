"""E3 minimum core for vault initialization, indexing, search and read."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import uuid
import json
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .prototype_index import FtsIndex
from .state import StateStore
from .graph import build_graph
from .lint import lint
from .prototype_lock import file_lock
from .prototype_markdown import parse_document
from .knowledge import INACTIVE_STATES, KnowledgeVault
from .code_sync import refresh_code
from .vault_profile import index_path


@dataclass(frozen=True)
class Block:
    path: str
    block_id: str
    heading: str
    content: str


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def init_vault(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    profile = root / ".kbkit" / "profile.toml"
    if profile.exists():
        return profile
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(
        f'vault_uuid = "{uuid.uuid4()}"\nschema_version = 1\n', encoding="utf-8"
    )
    return profile


def _blocks(relative: str, data: bytes) -> list[Block]:
    lines = data.decode("utf-8-sig").splitlines()
    blocks: list[Block] = []
    heading = Path(relative).stem
    current: list[str] = []
    ordinal = 0
    for line in lines:
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            if current:
                blocks.append(Block(relative, f"{relative}:{ordinal}", heading, "\n".join(current)))
                ordinal += 1
                current = []
            heading = line.lstrip("#").strip()
        current.append(line)
    if current:
        blocks.append(Block(relative, f"{relative}:{ordinal}", heading, "\n".join(current)))
    return blocks


def _markdown_files(root: Path) -> dict[str, tuple[Path, os.stat_result]]:
    paths = {}
    folders = [root]
    while folders:
        with os.scandir(folders.pop()) as entries:
            for entry in entries:
                if entry.name.lower() in {".kbkit", ".git"} or entry.is_symlink():
                    continue
                is_directory = entry.is_dir(follow_symlinks=False)
                if not is_directory and not entry.name.lower().endswith(".md"):
                    continue
                info = entry.stat(follow_symlinks=False)
                if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                path = Path(entry.path)
                if is_directory:
                    folders.append(path)
                elif stat.S_ISREG(info.st_mode):
                    paths[path.relative_to(root).as_posix()] = (path, info)
    return paths


def _sync_index(root: Path, connection: sqlite3.Connection, state: StateStore, *, verify_hashes: bool) -> int:
    connection.execute("CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, document_id TEXT, mtime_ns INTEGER, size INTEGER, lifecycle TEXT)")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    if "document_id" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN document_id TEXT")
    if "mtime_ns" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN mtime_ns INTEGER")
    if "size" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN size INTEGER")
    if "lifecycle" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN lifecycle TEXT")
    index = FtsIndex(connection)
    count = 0
    documents = {
        path: (content_hash, document_id, mtime_ns, size, lifecycle)
        for path, content_hash, document_id, mtime_ns, size, lifecycle in connection.execute(
            "SELECT path, content_hash, document_id, mtime_ns, size, lifecycle FROM documents"
        )
    }
    paths = _markdown_files(root)
    missing = documents.keys() - paths.keys()
    missing_by_hash: dict[str, list[str]] = defaultdict(list)
    for relative in sorted(missing):
        missing_by_hash[documents[relative][0]].append(relative)
    moved_from: set[str] = set()
    for relative, (path, info) in sorted(paths.items()):
        previous = documents.get(relative)
        metadata = (info.st_mtime_ns, info.st_size)
        if not index.rebuild_required and not verify_hashes and previous and previous[4] is not None and previous[2:4] == metadata:
            continue
        data = path.read_bytes()
        content_hash = _hash(data)
        if previous and previous[0] == content_hash:
            if previous[2:4] != metadata or previous[4] is None:
                lifecycle = previous[4] or parse_document(data).fields.get("state", "active")
                connection.execute("UPDATE documents SET mtime_ns = ?, size = ?, lifecycle = ? WHERE path = ?", (*metadata, lifecycle, relative))
            if index.rebuild_required:
                for block in _blocks(relative, data):
                    index.insert_block(block.path, block.block_id, f"{block.heading}\n{block.content}", commit=False)
                    count += 1
            continue
        document_id = previous[1] if previous else None
        if previous is None:
            candidates = missing_by_hash.pop(content_hash, [])
            if len(candidates) == 1:
                old_path = candidates[0]
                document_id = documents[old_path][1]
                moved_from.add(old_path)
                state.record_event("vault", old_path, content_hash, None, "moved", commit=False)
        state.record_event("vault", relative, previous[0] if previous else None, content_hash, "moved" if previous is None and document_id else content_hash, commit=False)
        lifecycle = parse_document(data).fields.get("state", "active")
        connection.execute("INSERT OR REPLACE INTO documents(path, content_hash, document_id, mtime_ns, size, lifecycle) VALUES (?, ?, ?, ?, ?, ?)", (relative, content_hash, document_id or str(uuid.uuid4()), *metadata, lifecycle))
        if previous:
            index.delete_blocks(relative)
        for block in _blocks(relative, data):
            index.insert_block(block.path, block.block_id, f"{block.heading}\n{block.content}", commit=False)
            count += 1
    for relative in sorted(missing):
        if relative not in moved_from:
            state.record_event("vault", relative, documents[relative][0], None, "deleted", commit=False)
        connection.execute("DELETE FROM documents WHERE path = ?", (relative,))
        index.delete_blocks(relative)
    return count


def _build_index(root: Path, *, verify_hashes: bool = True) -> int:
    with closing(sqlite3.connect(index_path(root, create=True))) as connection, closing(StateStore(root)) as state:
        with state.connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            return _sync_index(root, connection, state, verify_hashes=verify_hashes)


def build_index(root: Path) -> int:
    init_vault(root)
    with file_lock(root / ".kbkit" / "maintenance.lock"):
        return _build_index(root)


def search_details(root: Path, query: str, include_inactive: bool = False) -> list[dict]:
    if not (root / ".kbkit" / "profile.toml").is_file():
        raise ValueError("vault is not initialized")
    with file_lock(root / ".kbkit" / "maintenance.lock"):
        _build_index(root, verify_hashes=False)
        with closing(sqlite3.connect(index_path(root))) as connection:
            statuses = KnowledgeVault(root).statuses()
            placeholders = ", ".join("?" for _ in INACTIVE_STATES)
            for path, lifecycle in connection.execute(
                f"SELECT path, lifecycle FROM documents WHERE lifecycle IN ({placeholders})", tuple(INACTIVE_STATES)
            ):
                statuses.setdefault(path, {"state": lifecycle, "reason": "frontmatter"})
            return [
                {"path": path, "block_id": block_id, "content": content, **statuses.get(path, {"state": "active"})}
                for path, block_id, content in FtsIndex(connection).search(query)
                if include_inactive or statuses.get(path, {}).get("state") not in INACTIVE_STATES
            ]


def search(root: Path, query: str) -> list[tuple[str, str, str]]:
    return [(hit["path"], hit["block_id"], hit["content"]) for hit in search_details(root, query)]


def read(root: Path, relative_path: str) -> str:
    candidate = (root / relative_path).resolve()
    if root.resolve() not in candidate.parents or candidate.suffix.lower() != ".md":
        raise ValueError("path is outside the vault")
    return candidate.read_text(encoding="utf-8")


def maintain(root: Path) -> dict:
    init_vault(root)
    lock_path = root / ".kbkit" / "maintenance.lock"
    with file_lock(lock_path):
        state = StateStore(root)
        run_id = state.start_task("maintenance")
        try:
            knowledge = KnowledgeVault(root)
            code_sync = refresh_code(knowledge)
            blocks = _build_index(root)
            graph = build_graph(root)
            findings = lint(root)
            for finding in findings:
                risk = {"low": "low", "medium": "medium", "high": "high"}.get(finding.get("severity", "low"), "low")
                if not state.has_open_proposal(finding["message"], finding):
                    state.create_proposal(risk, finding["message"], finding)
            expired = state.expire_missing_findings(findings)
            with closing(sqlite3.connect(index_path(root))) as connection:
                indexed_blocks = FtsIndex(connection).count()
            status = "partial" if any(row["status"] in {"conflicted", "unverified"} for row in code_sync) else "succeeded"
            report = {"run_id": run_id, "status": status, "blocks": indexed_blocks, "changed_blocks": blocks, "graph": graph, "findings": findings, "expired_proposals": expired, "proposals": len(state.list_proposals("pending")),
                      "code_sync": code_sync, "knowledge": knowledge.statuses()}
            report_path = root / ".kbkit" / "reports" / f"{run_id}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            state.finish_task(run_id, status, str(report_path.relative_to(root)))
            return {**report, "report_path": str(report_path)}
        except Exception as exc:
            state.finish_task(run_id, "failed")
            report_path = root / ".kbkit" / "reports" / f"{run_id}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({"run_id": run_id, "status": "failed", "error": str(exc)}), encoding="utf-8")
            raise
        finally:
            state.close()
