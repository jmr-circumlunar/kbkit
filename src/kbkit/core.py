"""E3 minimum core for vault initialization, indexing, search and read."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
import json
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .storage import markdown_files, metadata_dir

from .prototype_index import FtsIndex
from .state import StateStore
from .graph import build_graph
from .lint import lint
from .prototype_lock import file_lock
from .prototype_markdown import parse_document
from .knowledge import KnowledgeVault
from .selector import blocks as select_blocks, headings, markdown_path, source_lines
from .code_sync import refresh_code
from .transaction import write_atomic
from .vault_profile import index_path


@dataclass(frozen=True)
class Block:
    path: str
    block_id: str
    heading: tuple[str, ...]
    content: str
    line_start: int
    line_end: int


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def init_vault(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    profile = metadata_dir(root) / "profile.toml"
    if profile.exists():
        return profile
    profile.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_atomic(profile, f'vault_uuid = "{uuid.uuid4()}"\nschema_version = 1\n'.encode("utf-8"), exclusive=True)
    except FileExistsError:
        pass
    return profile


def _blocks(relative: str, data: bytes) -> list[Block]:
    lines = source_lines(data)
    sections = headings(data)
    names = {heading.start: heading.path for heading in sections}
    return [
        Block(relative, f"{relative}:{ordinal}", names.get(section.start, ()),
              b"".join(lines[section.start:section.end]).decode("utf-8-sig"),
              section.start + 1, section.end)
        for ordinal, section in enumerate(select_blocks(data, sections=sections, line_count=len(lines)))
    ]


def _document_metadata(data: bytes) -> dict:
    document = parse_document(data)
    metadata = {key: document.fields[key] for key in ("state", "kind") if key in document.fields}
    if "tags" in document.fields:
        metadata["tags"] = document.lists.get("tags", tuple(value.strip() for value in document.fields["tags"].split(",") if value.strip()))
    return metadata


def _sync_index(root: Path, connection: sqlite3.Connection, state: StateStore) -> int:
    connection.execute("CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, document_id TEXT, mtime_ns INTEGER, size INTEGER, lifecycle TEXT, metadata TEXT)")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    if "document_id" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN document_id TEXT")
    if "mtime_ns" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN mtime_ns INTEGER")
    if "size" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN size INTEGER")
    if "lifecycle" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN lifecycle TEXT")
    if "metadata" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN metadata TEXT")
    index = FtsIndex(connection)
    count = 0
    documents = {
        path: (content_hash, document_id, mtime_ns, size, lifecycle, fields_json)
        for path, content_hash, document_id, mtime_ns, size, lifecycle, fields_json in connection.execute(
            "SELECT path, content_hash, document_id, mtime_ns, size, lifecycle, metadata FROM documents"
        )
    }
    paths = markdown_files(root)
    missing = documents.keys() - paths.keys()
    missing_by_hash: dict[str, list[str]] = defaultdict(list)
    for relative in sorted(missing):
        missing_by_hash[documents[relative][0]].append(relative)
    moved_from: set[str] = set()
    for relative, (path, info) in sorted(paths.items()):
        previous = documents.get(relative)
        metadata = (info.st_mtime_ns, info.st_size)
        data = path.read_bytes()
        content_hash = _hash(data)
        if previous and previous[0] == content_hash:
            if previous[2:4] != metadata or previous[5] is None:
                fields = _document_metadata(data)
                connection.execute("UPDATE documents SET mtime_ns = ?, size = ?, lifecycle = ?, metadata = ? WHERE path = ?",
                                   (*metadata, fields.get("state", "active"), json.dumps(fields), relative))
            if index.rebuild_required:
                for block in _blocks(relative, data):
                    index.insert_block(block.path, block.block_id, block.content, commit=False,
                                       heading=block.heading, title=block.heading[-1] if block.heading else Path(relative).stem,
                                       line_start=block.line_start, line_end=block.line_end)
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
        fields = _document_metadata(data)
        connection.execute("INSERT OR REPLACE INTO documents(path, content_hash, document_id, mtime_ns, size, lifecycle, metadata)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (relative, content_hash, document_id or str(uuid.uuid4()), *metadata,
                            fields.get("state", "active"), json.dumps(fields)))
        if previous:
            index.delete_blocks(relative)
        for block in _blocks(relative, data):
            index.insert_block(block.path, block.block_id, block.content, commit=False,
                                       heading=block.heading, title=block.heading[-1] if block.heading else Path(relative).stem,
                                       line_start=block.line_start, line_end=block.line_end)
            count += 1
    for relative in sorted(missing):
        if relative not in moved_from:
            state.record_event("vault", relative, documents[relative][0], None, "deleted", commit=False)
        connection.execute("DELETE FROM documents WHERE path = ?", (relative,))
        index.delete_blocks(relative)
    return count


def _build_index(root: Path) -> int:
    with closing(sqlite3.connect(index_path(root, create=True))) as connection, closing(StateStore(root)) as state:
        with state.connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            return _sync_index(root, connection, state)


def build_index(root: Path) -> int:
    init_vault(root)
    with file_lock(metadata_dir(root) / "maintenance.lock"):
        return _build_index(root)


def search_details(root: Path, query: str, include_inactive: bool = False) -> list[dict]:
    from .retrieval import search_page

    return search_page(root, query, include_inactive, limit=None, select="full")["hits"]


def search(root: Path, query: str) -> list[tuple[str, str, str]]:
    return [(hit["path"], hit["block_id"], hit["content"]) for hit in search_details(root, query)]


def read(root: Path, relative_path: str) -> str:
    return markdown_path(root, relative_path).read_text(encoding="utf-8-sig")


def maintain(root: Path) -> dict:
    init_vault(root)
    lock_path = metadata_dir(root) / "maintenance.lock"
    with file_lock(lock_path):
        state = StateStore(root)
        run_id = state.start_task("maintenance")
        try:
            knowledge = KnowledgeVault(root)
            code_sync = refresh_code(knowledge)
            blocks = _build_index(root)
            graph = build_graph(root)
            protected = set(knowledge.data["pages"]) | {entry["page"] for entry in knowledge.data["code"].values()}
            findings = lint(root, graph=graph, protected=protected)
            fixes = [finding["fix"] for finding in findings if "fix" in finding]
            expired = state.expire_missing_findings(fixes)
            for finding in findings:
                if "fix" in finding and not state.has_open_proposal(finding["message"], finding["fix"]):
                    state.create_proposal("low", finding["message"], finding["fix"])
            with closing(sqlite3.connect(index_path(root))) as connection:
                indexed_blocks = FtsIndex(connection).count()
            status = "partial" if any(row["status"] in {"conflicted", "unverified"} for row in code_sync) else "succeeded"
            report = {"run_id": run_id, "status": status, "blocks": indexed_blocks, "changed_blocks": blocks, "graph": graph, "findings": findings, "expired_proposals": expired, "proposals": state.proposal_page("pending", 1, 0)[0],
                      "code_sync": code_sync, "knowledge": knowledge.statuses()}
            report_path = metadata_dir(root) / "reports" / f"{run_id}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            state.finish_task(run_id, status, str(report_path))
            return {**report, "report_path": str(report_path)}
        except Exception as exc:
            state.finish_task(run_id, "failed")
            report_path = metadata_dir(root) / "reports" / f"{run_id}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({"run_id": run_id, "status": "failed", "error": str(exc)}), encoding="utf-8")
            raise
        finally:
            state.close()
