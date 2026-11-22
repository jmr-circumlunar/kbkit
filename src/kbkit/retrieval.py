"""Bounded retrieval over indexed Markdown and live governance state."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from contextlib import closing, contextmanager

from .core import _build_index
from .knowledge import KnowledgeVault
from .paging import integer, page, window
from .profile import QueryError, load_profile, matches_prefix, prefix, values
from .prototype_index import FtsIndex
from .prototype_lock import file_lock
from .storage import metadata_dir
from .vault_profile import index_path, vault_id


FORMATS = ("snippet", "path", "full", "json")
KINDS = {"note", "decision", "reference", "procedure", "meeting", "task", "code", "design"}
SYMBOL = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


@contextmanager
def _snapshot(root):
    if not (metadata_dir(root) / "profile.toml").is_file():
        raise ValueError("vault is not initialized; run kbc init first")
    with file_lock(metadata_dir(root) / "maintenance.lock"):
        _build_index(root, verify=False)
        with closing(sqlite3.connect(index_path(root))) as connection:
            yield connection


def _status(doc: dict, profile, override: dict | None) -> dict:
    if profile.require_state and "state" not in doc:
        return {"state": "unknown", "reason": "missing_state"}
    state = doc.get("state", "active")
    canonical = profile.canonical_state(state)
    if override and override["state"] != "active":
        return override
    if canonical != "active" or state != "active":
        return {"state": canonical, "source_state": state, "reason": "frontmatter"}
    return {"state": "active"}


def _rows(connection, knowledge, profile):
    statuses = knowledge.statuses(profile)
    for path, raw, source_hash in connection.execute("SELECT path, metadata, content_hash FROM documents ORDER BY path"):
        doc = json.loads(raw or "{}")
        status = _status(doc, profile, statuses.get(path))
        yield path, doc, status, source_hash


def _validate_enum(field, requested, allowed):
    invalid = set(requested) - allowed
    if invalid:
        raise QueryError(f"unsupported {field}: {', '.join(sorted(invalid))}", field=field, allowed=sorted(allowed))


def _excerpt(content: str, terms: list[str], max_chars: int, *, full: bool) -> tuple[str, int, bool]:
    match = next((m for term in terms if (m := re.search(re.escape(term), content, flags=re.IGNORECASE))), None)
    hit = match.start() if match else 0
    if len(content) <= max_chars:
        return content, hit, False
    start = 0 if full else max(0, hit - max_chars // 4)
    length = max_chars - 2
    end = start + length
    return ("…" if start else "") + content[start:end] + ("…" if end < len(content) else ""), hit, True


def search_page(root, query: str = "", include_inactive: bool = False, *, limit: int | None = 8,
                offset: int = 0, max_chars: int = 1200, max_bytes: int = 36_000,
                select: str = "snippet", path=None, kind=None, state=None, tags=None, symbols=None,
                exclude=None, budget_chars: int | None = None, include_excluded: bool = False) -> dict:
    if not isinstance(query, str) or len(query) > 2048:
        raise ValueError("query must be a string of at most 2048 characters")
    if type(include_inactive) is not bool:
        raise ValueError("include_inactive must be a boolean")
    if select not in FORMATS:
        raise QueryError("unsupported search result format", field="select", allowed=list(FORMATS))
    max_chars = integer(max_chars, "max_chars", 16, 16_000)
    if budget_chars is not None:
        integer(budget_chars, "budget_chars", 16, 200_000)
    paths = tuple(map(prefix, values(path, "path")))
    if type(include_excluded) is not bool:
        raise ValueError("include_excluded must be a boolean")
    if include_excluded and not paths:
        raise ValueError("historical search requires an explicit vault-relative path")
    exclusions = tuple(map(prefix, values(exclude, "exclude")))
    kinds, states, requested_tags = values(kind, "kind"), values(state, "state"), set(values(tags, "tags"))
    symbols = values(symbols, "symbols")
    if len(symbols) > 20 or any(not SYMBOL.fullmatch(symbol) or len(symbol) > 128 for symbol in symbols):
        raise ValueError("symbols must contain up to 20 identifiers, each at most 128 characters")
    query = query.strip()
    if not (query or paths or kinds or states or requested_tags or symbols):
        raise ValueError("supply a query or at least one positive search filter")
    page_limit = -1 if limit is None else window(integer(limit, "limit", 1, 50), offset, max_bytes)[0]
    profile = load_profile(root)
    states = tuple(profile.aliases.get(value.casefold(), value.casefold()) for value in states)
    _validate_enum("state", states, profile.inactive | {"active", "review_due"})
    with _snapshot(root) as connection:
        entries = list(_rows(connection, KnowledgeVault(root), profile))
        allowed_kinds = set(profile.kinds) or (KINDS | {doc["kind"] for _, doc, _, _ in entries if doc.get("kind")})
        _validate_enum("kind", kinds, allowed_kinds)
        candidates = {
            name: (doc, status, source_hash)
            for name, doc, status, source_hash in entries
            if (include_excluded or not profile.excluded(name))
            and (not paths or matches_prefix(name, paths))
            and not matches_prefix(name, exclusions)
            and (include_inactive or status["state"] not in profile.inactive or status["state"] in states)
            and (not states or status["state"] in states)
            and (not kinds or doc.get("kind") in kinds)
            and requested_tags <= set(doc.get("tags", ()))
        }
        connection.execute("CREATE TEMP TABLE search_paths(path TEXT PRIMARY KEY) WITHOUT ROWID")
        connection.executemany("INSERT INTO search_paths VALUES (?)", ((name,) for name in candidates))
        try:
            total, rows = FtsIndex(connection).page(query, symbols, limit=page_limit, offset=offset,
                                                   title_weight=profile.title_weight, body_weight=profile.body_weight)
        except sqlite3.OperationalError as exc:
            if "fts5:" in str(exc) or "syntax error" in str(exc) or "unterminated string" in str(exc) or "no such column" in str(exc):
                raise QueryError("invalid FTS query expression; try plain words or a quoted phrase", field="query") from exc
            raise
    terms = [*symbols, *re.findall(r'[\w]+', query)]
    hits = []
    used = 0
    identity = vault_id(root)
    for name, block_id, body, heading, start, end, heading_path, score in rows:
        doc, status, source_hash = candidates[name]
        hit = {"vault_id": identity, "path": name, "block_id": f"{block_id}@{source_hash[:32]}",
               "lines": [start, end], "line_start": start, "line_end": end,
               "heading_path": json.loads(heading_path), "score": -score, "stale": status["state"] == "stale", **status}
        if select != "path":
            content = FtsIndex._decode(body)
            remaining = max_chars if budget_chars is None else min(max_chars, budget_chars - used)
            if remaining < 16:
                break
            text, position, clipped = _excerpt(content, terms, (len(content) + 1) if limit is None else remaining, full=select == "full")
            hit.update(content=text, content_truncated=clipped,
                       hit_line=start + content[:position].count("\n"), heading=heading)
            used += len(text)
        if select == "json":
            hit.update(kind=doc.get("kind"), tags=doc.get("tags", []))
        hits.append(hit)
    if limit is None:
        return {"hits": hits}
    result = page(hits, key="hits", limit=limit, offset=offset, max_bytes=max_bytes, total=total,
                  presliced=True, context={"total_candidates": total})
    result["truncated"] |= any(hit.get("content_truncated") for hit in result["hits"])
    return result


def facets(root, *, path=None, dimension="all", limit=25, offset=0, max_bytes=36_000) -> dict:
    limit, offset, max_bytes = window(limit, offset, max_bytes)
    dimensions = ("path", "kind", "state", "tags")
    _validate_enum("dimension", (dimension,), set(dimensions) | {"all"})
    prefixes = tuple(map(prefix, values(path, "path")))
    profile = load_profile(root)
    counts = {name: Counter() for name in dimensions}
    with _snapshot(root) as connection:
        for name, doc, status, _ in _rows(connection, KnowledgeVault(root), profile):
            if profile.excluded(name) or (prefixes and not matches_prefix(name, prefixes)):
                continue
            counts["tags"].update(set(doc.get("tags", ())))
            counts["path"][name.split("/", 1)[0] if "/" in name else "."] += 1
            counts["kind"][doc.get("kind") or "(unset)"] += 1
            counts["state"][status["state"]] += 1

    def distribution(name):
        return [{"value": value, "count": count} for value, count in
                sorted(counts[name].items(), key=lambda row: (-row[1], row[0]))]

    if dimension == "all":
        items = [{"dimension": name, "values": distribution(name)[:5], "total_values": len(counts[name])}
                 for name in dimensions]
    else:
        items = distribution(dimension)
    return page(items, key="facets", limit=limit, offset=offset, max_bytes=max_bytes, context={"dimension": dimension})
