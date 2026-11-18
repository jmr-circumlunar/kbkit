"""E3 minimum core for vault initialization, indexing, search and read."""

from __future__ import annotations

import hashlib
import os
import sqlite3
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


def _index_path(root: Path) -> Path:
    configured = os.environ.get("KBKIT_INDEX_DIR")
    base = Path(configured) if configured else Path(os.environ.get("LOCALAPPDATA", root / ".kbkit")) / "kbkit" / "indexes"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{_vault_id(root)}.sqlite"


def _vault_id(root: Path) -> str:
    profile = root / ".kbkit" / "profile.toml"
    for line in profile.read_text(encoding="utf-8").splitlines():
        if line.startswith("vault_uuid"):
            return line.split('"', 2)[1]
    raise ValueError("vault is not initialized")


def _sync_index(root: Path, connection: sqlite3.Connection, state: StateStore, *, verify_hashes: bool) -> int:
    connection.execute("CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, document_id TEXT, mtime_ns INTEGER, size INTEGER)")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    if "document_id" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN document_id TEXT")
    if "mtime_ns" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN mtime_ns INTEGER")
    if "size" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN size INTEGER")
    index = FtsIndex(connection)
    count = 0
    documents = {
        path: (content_hash, document_id, mtime_ns, size)
        for path, content_hash, document_id, mtime_ns, size in connection.execute(
            "SELECT path, content_hash, document_id, mtime_ns, size FROM documents"
        )
    }
    paths = {
        relative.as_posix(): path
        for path in sorted(root.rglob("*.md"))
        if not {".kbkit", ".git"}.intersection((relative := path.relative_to(root)).parts)
        and not path.is_symlink() and path.is_file()
    }
    missing = documents.keys() - paths.keys()
    missing_by_hash: dict[str, list[str]] = defaultdict(list)
    for relative in sorted(missing):
        missing_by_hash[documents[relative][0]].append(relative)
    moved_from: set[str] = set()
    for relative, path in paths.items():
        stat = path.stat()
        previous = documents.get(relative)
        if not verify_hashes and previous and previous[2:] == (stat.st_mtime_ns, stat.st_size):
            continue
        data = path.read_bytes()
        content_hash = _hash(data)
        if previous and previous[0] == content_hash:
            if previous[2:] != (stat.st_mtime_ns, stat.st_size):
                connection.execute("UPDATE documents SET mtime_ns = ?, size = ? WHERE path = ?", (stat.st_mtime_ns, stat.st_size, relative))
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
        connection.execute("INSERT OR REPLACE INTO documents(path, content_hash, document_id, mtime_ns, size) VALUES (?, ?, ?, ?, ?)", (relative, content_hash, document_id or str(uuid.uuid4()), stat.st_mtime_ns, stat.st_size))
        if previous:
            connection.execute("DELETE FROM blocks WHERE path = ?", (relative,))
        for block in _blocks(relative, data):
            index.insert_block(block.path, block.block_id, f"{block.heading}\n{block.content}", commit=False)
            count += 1
    for relative in sorted(missing):
        if relative not in moved_from:
            state.record_event("vault", relative, documents[relative][0], None, "deleted", commit=False)
        connection.execute("DELETE FROM documents WHERE path = ?", (relative,))
        connection.execute("DELETE FROM blocks WHERE path = ?", (relative,))
    return count


def _build_index(root: Path, *, verify_hashes: bool = True) -> int:
    with closing(sqlite3.connect(_index_path(root))) as connection, closing(StateStore(root)) as state:
        with state.connection, connection:
            return _sync_index(root, connection, state, verify_hashes=verify_hashes)


def build_index(root: Path) -> int:
    init_vault(root)
    with file_lock(root / ".kbkit" / "maintenance.lock"):
        return _build_index(root)


def search(root: Path, query: str) -> list[tuple[str, str, str]]:
    init_vault(root)
    with file_lock(root / ".kbkit" / "maintenance.lock"):
        _build_index(root, verify_hashes=False)
        with closing(sqlite3.connect(_index_path(root))) as connection:
            return FtsIndex(connection).search(query)


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
            blocks = _build_index(root)
            graph = build_graph(root)
            findings = lint(root)
            for finding in findings:
                risk = {"low": "low", "medium": "medium", "high": "high"}.get(finding.get("severity", "low"), "low")
                if not state.has_open_proposal(finding["message"], finding):
                    state.create_proposal(risk, finding["message"], finding)
            expired = state.expire_missing_findings(findings)
            with closing(sqlite3.connect(_index_path(root))) as connection:
                indexed_blocks = connection.execute("SELECT count(*) FROM blocks").fetchone()[0]
            report = {"run_id": run_id, "status": "succeeded", "blocks": indexed_blocks, "changed_blocks": blocks, "graph": graph, "findings": findings, "expired_proposals": expired, "proposals": len(state.list_proposals("pending"))}
            report_path = root / ".kbkit" / "reports" / f"{run_id}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            state.finish_task(run_id, "succeeded", str(report_path.relative_to(root)))
            return {**report, "report_path": str(report_path)}
        except Exception as exc:
            state.finish_task(run_id, "failed")
            report_path = root / ".kbkit" / "reports" / f"{run_id}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({"run_id": run_id, "status": "failed", "error": str(exc)}), encoding="utf-8")
            raise
        finally:
            state.close()
