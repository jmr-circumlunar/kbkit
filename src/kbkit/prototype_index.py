"""E2 SQLite FTS5 prototype with explicit runtime probing."""

from __future__ import annotations

import json
import re
import sqlite3
import zlib
from functools import lru_cache


_HAN_RUN = re.compile(r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\U00030000-\U000323af]+)")


@lru_cache(maxsize=8192)
def _gram(left: str, right: str) -> str:
    return f"b{ord(left):x}x{ord(right):x}"


def _han_phrase(text: str) -> str:
    return " ".join(_gram(left, right) for left, right in zip(text, text[1:]))


def _han_run(text: str) -> str:
    # Index the final character too, so a one-character query can match anywhere.
    grams = _han_phrase(text)
    last = _gram(text[-1], "\0")
    return f"{grams} {last}" if grams else last


_cached_han_run = lru_cache(maxsize=8192)(_han_run)


def _search_tokens(content: str) -> tuple[str, str]:
    parts = _HAN_RUN.split(content)
    han = " boundary ".join(_cached_han_run(part) if len(part) <= 64 else _han_run(part) for part in parts[1::2])
    return " ".join(parts[::2]), han


def _match_expression(query: str) -> str:
    if not _HAN_RUN.search(query):
        return "{path block_id title content}: (" + query + ")"
    terms = []
    for position, part in enumerate(_HAN_RUN.split(query)):
        if position % 2:
            expression = f"b{ord(part):x}x*" if len(part) == 1 else f'"{_han_phrase(part)}"'
            terms.append(f"{{han_bigrams han_title_bigrams}}:{expression}")
        else:
            terms.extend(f'{{content title}}:"{word}"' for word in re.findall(r"\w+", part))
    return " AND ".join(terms)


class FtsIndex:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        schema = dict(connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name IN ('blocks', 'block_text')"
        ))
        existing = schema.get("blocks", "")
        self.rebuild_required = "content=''" not in existing or "han_title_bigrams" not in existing or "heading_path" not in schema.get("block_text", "")
        if self.rebuild_required:
            self.connection.execute("DROP TABLE IF EXISTS blocks")
            self.connection.execute("DROP TABLE IF EXISTS block_text")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS block_text (id INTEGER PRIMARY KEY, path TEXT NOT NULL, "
            "block_id TEXT NOT NULL, body BLOB NOT NULL, title TEXT NOT NULL, "
            "line_start INTEGER NOT NULL, line_end INTEGER NOT NULL, heading_path TEXT NOT NULL)"
        )
        self.connection.execute("CREATE INDEX IF NOT EXISTS block_text_path ON block_text(path, block_id)")
        self.connection.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS blocks USING fts5(
                path, block_id, content, han_bigrams, title, han_title_bigrams,
                content='', tokenize = 'unicode61 tokenchars ''_'''
            )"""
        )

    def replace_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        self.delete_blocks(path, block_id)
        self.insert_block(path, block_id, content, commit=False)
        if commit:
            self.connection.commit()

    def insert_block(self, path: str, block_id: str, content: str, commit: bool = True, *, title: str = "",
                     line_start: int = 1, line_end: int = 1, heading: tuple[str, ...] = ()) -> None:
        raw = content.encode("utf-8")
        compressed = zlib.compress(raw, level=1)
        body = b"z" + compressed if len(compressed) < len(raw) else b"r" + raw
        row = self.connection.execute(
            "INSERT INTO block_text(path, block_id, body, title, line_start, line_end, heading_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (path, block_id, body, title, line_start, line_end, json.dumps(heading, ensure_ascii=False))
        )
        self.connection.execute(
            "INSERT INTO blocks(rowid, path, block_id, content, han_bigrams, title, han_title_bigrams) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row.lastrowid, path, block_id, *_search_tokens(content), *_search_tokens(title)),
        )
        if commit:
            self.connection.commit()

    def delete_blocks(self, path: str, block_id: str | None = None) -> None:
        predicate = "path = ?" if block_id is None else "path = ? AND block_id = ?"
        values = (path,) if block_id is None else (path, block_id)
        for rowid, old_id, body, title in self.connection.execute(
            f"SELECT id, block_id, body, title FROM block_text WHERE {predicate}", values,
        ):
            content = self._decode(body)
            self.connection.execute(
                "INSERT INTO blocks(blocks, rowid, path, block_id, content, han_bigrams, title, han_title_bigrams) "
                "VALUES ('delete', ?, ?, ?, ?, ?, ?, ?)",
                (rowid, path, old_id, *_search_tokens(content), *_search_tokens(title)),
            )
        self.connection.execute(f"DELETE FROM block_text WHERE {predicate}", values)

    @staticmethod
    def _decode(body: bytes) -> str:
        data = zlib.decompress(body[1:]) if body[:1] == b"z" else body[1:]
        return data.decode("utf-8")

    def search(self, query: str) -> list[tuple[str, str, str]]:
        rows = self.connection.execute(
            "SELECT t.path, t.block_id, t.body FROM blocks JOIN block_text AS t ON t.id = blocks.rowid "
            "WHERE blocks MATCH ? ORDER BY blocks.rank, t.path, t.block_id",
            (_match_expression(query),),
        )
        return [(path, block_id, self._decode(body)) for path, block_id, body in rows]

    def page(self, query: str, symbols: tuple[str, ...], *, limit: int, offset: int,
             title_weight: float, body_weight: float) -> tuple[int, list]:
        expressions = [_match_expression(query)] if query else []
        expressions.extend(f'{{content title}}:"{symbol}"' for symbol in symbols)
        predicate = "JOIN search_paths AS p ON p.path = t.path"
        if expressions:
            predicate += " JOIN blocks ON blocks.rowid = t.id WHERE blocks MATCH ?"
        if symbols:
            patterns = [re.compile(rf"(?<![A-Za-z_0-9]){re.escape(symbol)}(?![A-Za-z_0-9])") for symbol in symbols]

            def has_symbols(body, title):
                content = title + "\n" + self._decode(body)
                return all(pattern.search(content) for pattern in patterns)

            self.connection.create_function("kb_has_symbols", 2, has_symbols)
            predicate += " AND kb_has_symbols(t.body, t.title)"
        bindings = (" AND ".join(f"({term})" for term in expressions),) if expressions else ()
        source = " FROM block_text AS t " + predicate
        total = self.connection.execute("SELECT count(*)" + source, bindings).fetchone()[0]
        score = "bm25(blocks, 1.0, 0.0, ?, ?, ?, ?)" if expressions else "0.0"
        weights = (body_weight, body_weight, title_weight, title_weight) if expressions else ()
        rows = self.connection.execute(
            "SELECT t.path, t.block_id, t.body, t.title, t.line_start, t.line_end, t.heading_path, " + score + " AS score" +
            source + " ORDER BY score, t.path, t.line_start LIMIT ? OFFSET ?",
            (*weights, *bindings, limit, offset),
        ).fetchall()
        return total, rows

    def count(self) -> int:
        return self.connection.execute("SELECT count(*) FROM block_text").fetchone()[0]


def fts5_available() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
    except sqlite3.Error:
        return False
    finally:
        connection.close()
    return True
