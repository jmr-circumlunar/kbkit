"""E3 minimum core for vault initialization, indexing, search and read."""

from __future__ import annotations

import sqlite3
import uuid
import json
from collections import defaultdict
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path

from .storage import change_tokens, markdown_files, metadata_dir

from .prototype_index import FtsIndex
from .state import StateStore
from .graph import build_graph
from .lint import lint
from .prototype_lock import file_lock
from .prototype_markdown import parse_document
from .knowledge import KnowledgeVault
from .selector import blocks as select_blocks, headings, markdown_path, source_lines
from .code_sync import refresh_code
from .transaction import digest
from .vault_profile import index_path, init_vault


@dataclass(frozen=True)
class Block:
    path: str
    block_id: str
    heading: tuple[str, ...]
    content: str
    line_start: int
    line_end: int


def _blocks(relative: str, data: bytes) -> list[Block]:
    lines = source_lines(data)
    sections = headings(data, lines=lines)
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


def _sync_index(root: Path, connection: sqlite3.Connection, record_event, *, verify: bool,
                selected: tuple[str, ...] | None) -> int:
    connection.execute("CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, document_id TEXT, mtime_ns INTEGER, size INTEGER, lifecycle TEXT, metadata TEXT, change_token TEXT)")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    for column, kind in {"document_id": "TEXT", "mtime_ns": "INTEGER", "size": "INTEGER",
                         "lifecycle": "TEXT", "metadata": "TEXT", "change_token": "TEXT"}.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE documents ADD COLUMN {column} {kind}")
            selected = None
    index = FtsIndex(connection)
    count = 0
    if index.rebuild_required:
        selected = None
    condition, arguments = document_scope(selected)
    documents = {
        path: (content_hash, document_id, mtime_ns, size, lifecycle, token)
        for path, content_hash, document_id, mtime_ns, size, lifecycle, token in connection.execute(
            "SELECT path, content_hash, document_id, mtime_ns, size, lifecycle, change_token FROM documents" + condition,
            arguments,
        )
    }
    paths = index_sources(root, selected)
    tokens = change_tokens(paths)
    missing = documents.keys() - paths.keys()
    missing_by_hash: dict[str, list[str]] = defaultdict(list)
    for relative in sorted(missing):
        missing_by_hash[documents[relative][0]].append(relative)
    moved_from: set[str] = set()
    for relative, (path, info) in sorted(paths.items()):
        previous = documents.get(relative)
        metadata = (info.st_mtime_ns, info.st_size)
        token = tokens.get(relative)
        if (not verify and not index.rebuild_required and token and previous and previous[4] is not None
                and previous[2:4] == metadata and previous[5] == token):
            continue
        data = path.read_bytes()
        content_hash = digest(data)
        if previous and previous[0] == content_hash:
            if previous[2:4] != metadata or previous[4] is None or previous[5] != token:
                fields = _document_metadata(data)
                connection.execute("UPDATE documents SET mtime_ns = ?, size = ?, lifecycle = ?, metadata = ?, change_token = ? WHERE path = ?",
                                   (*metadata, fields.get("state", "active"), json.dumps(fields), token, relative))
            if index.rebuild_required:
                count += _insert_blocks(index, relative, data)
            continue
        document_id = previous[1] if previous else None
        if previous is None:
            candidates = missing_by_hash.pop(content_hash, [])
            if len(candidates) == 1:
                old_path = candidates[0]
                document_id = documents[old_path][1]
                moved_from.add(old_path)
                record_event("vault", old_path, content_hash, None, "moved")
        record_event("vault", relative, previous[0] if previous else None, content_hash,
                     "moved" if previous is None and document_id else content_hash)
        fields = _document_metadata(data)
        connection.execute("INSERT OR REPLACE INTO documents(path, content_hash, document_id, mtime_ns, size, lifecycle, metadata, change_token)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (relative, content_hash, document_id or str(uuid.uuid4()), *metadata,
                            fields.get("state", "active"), json.dumps(fields), token))
        if previous:
            index.delete_blocks(relative)
        count += _insert_blocks(index, relative, data)
    for relative in sorted(missing):
        if relative not in moved_from:
            record_event("vault", relative, documents[relative][0], None, "deleted")
        connection.execute("DELETE FROM documents WHERE path = ?", (relative,))
        index.delete_blocks(relative)
    return count


def _insert_blocks(index: FtsIndex, relative: str, data: bytes) -> int:
    blocks = _blocks(relative, data)
    for block in blocks:
        index.insert_block(block.path, block.block_id, block.content, commit=False,
                           heading=block.heading, title=block.heading[-1] if block.heading else Path(relative).stem,
                           line_start=block.line_start, line_end=block.line_end)
    return len(blocks)


def document_scope(selected: tuple[str, ...] | None, column: str = "path") -> tuple[str, tuple]:
    if selected is None:
        return "", ()
    if not selected:
        return " WHERE 0", ()
    placeholders = ", ".join("?" for _ in selected)
    return f" WHERE {column} IN ({placeholders})", selected


def index_sources(root: Path, selected: tuple[str, ...] | None) -> dict:
    if selected is None:
        return markdown_files(root)
    files = {}
    for relative in selected:
        target = markdown_path(root, relative, allow_missing=True)
        try:
            files[relative] = (target, target.stat())
        except FileNotFoundError:
            continue
    return files


def _index_is_damaged(path: Path) -> bool:
    try:
        with closing(sqlite3.connect(path)) as connection:
            return any(row != ("ok",) for row in connection.execute("PRAGMA quick_check"))
    except sqlite3.DatabaseError as error:
        return getattr(error, "sqlite_errorcode", 0) & 255 in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB)


def _build_index(root: Path, *, verify: bool = True, selected: tuple[str, ...] | None = None) -> int:
    path = index_path(root, create=True)
    if not path.is_file():
        selected = None
    for attempt in range(2):
        try:
            with closing(sqlite3.connect(path)) as connection, ExitStack() as audit:
                connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                state = None

                def record_event(*fields):
                    nonlocal state
                    if state is None:
                        state = audit.enter_context(closing(StateStore(root)))
                        audit.enter_context(state.connection)
                    state.record_event(*fields, commit=False)

                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    return _sync_index(root, connection, record_event, verify=verify, selected=selected)
        except sqlite3.DatabaseError as error:
            if attempt or getattr(error, "sqlite_errorcode", 0) & 255 not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                raise
            if not _index_is_damaged(path):
                raise
        selected = None
        suffix = f".damaged-{uuid.uuid4().hex[:8]}"
        path.rename(path.with_suffix(suffix))
        for extension in ("-wal", "-shm", "-journal"):
            sidecar = path.with_name(path.name + extension)
            if sidecar.is_file():
                sidecar.rename(sidecar.with_suffix(suffix + extension))
    raise RuntimeError("index recovery did not complete")


def build_index(root: Path) -> int:
    init_vault(root)
    with file_lock(metadata_dir(root) / "maintenance.lock"):
        return _build_index(root)


def maintain(root: Path) -> dict:
    from .consistency import check_consistency

    init_vault(root)
    lock_path = metadata_dir(root) / "maintenance.lock"
    with file_lock(lock_path):
        state = StateStore(root)
        run_id = state.start_task("maintenance")
        try:
            knowledge = KnowledgeVault(root)
            code_sync = refresh_code(knowledge)
            blocks = _build_index(root)
            consistency = check_consistency(root)
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
            incomplete = not consistency["ok"] or any(row["status"] in {"conflicted", "unverified"} for row in code_sync)
            status = "partial" if incomplete else "succeeded"
            report = {"run_id": run_id, "status": status, "blocks": indexed_blocks, "changed_blocks": blocks, "graph": graph, "findings": findings, "expired_proposals": expired, "proposals": state.proposal_page("pending", 1, 0)[0],
                      "consistency": consistency, "code_sync": code_sync, "knowledge": knowledge.statuses()}
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
