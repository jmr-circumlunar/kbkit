"""E2 SQLite FTS5 prototype with explicit runtime probing."""

from __future__ import annotations

import re
import sqlite3
import zlib


_HAN_RUN = re.compile(r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\U00030000-\U000323af]+)")


class _HanTokens(dict[int, str]):
    def __missing__(self, codepoint: int) -> str:
        token = f"h{codepoint:x} "
        self[codepoint] = token
        return token


_HAN_TOKENS = _HanTokens()


def _han_phrase(text: str) -> str:
    return text.translate(_HAN_TOKENS).rstrip(" ")


def _search_tokens(content: str) -> tuple[str, str]:
    parts = _HAN_RUN.split(content)
    han = " boundary ".join(_han_phrase(part) for part in parts[1::2])
    mixed = []
    for index, part in enumerate(parts[::2]):
        if not part:
            continue
        left = re.match(r"\w+", part) if index else None
        right = re.search(r"\b\w+\Z", part) if index < len(parts) // 2 else None
        mixed.extend(match[0] for match in (left, right) if match)
    return han, " ".join(mixed)


def _match_expression(query: str) -> str:
    if not _HAN_RUN.search(query):
        return "{path block_id content mixed_tokens}: (" + query + ")"
    terms = []
    for position, part in enumerate(_HAN_RUN.split(query)):
        if position % 2:
            terms.append(f'han_tokens:"{_han_phrase(part)}"')
        else:
            terms.extend(f'{{content mixed_tokens}}:"{word}"' for word in re.findall(r"\w+", part))
    return " AND ".join(terms)


class FtsIndex:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        schema = dict(connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name IN ('blocks', 'block_text')"
        ))
        self.rebuild_required = "content=''" not in schema.get("blocks", "") or "block_text" not in schema
        if self.rebuild_required:
            self.connection.execute("DROP TABLE IF EXISTS blocks")
            self.connection.execute("DROP TABLE IF EXISTS block_text")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS block_text (id INTEGER PRIMARY KEY, path TEXT NOT NULL, "
            "block_id TEXT NOT NULL, body BLOB NOT NULL)"
        )
        self.connection.execute("CREATE INDEX IF NOT EXISTS block_text_path ON block_text(path, block_id)")
        self.connection.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS blocks USING fts5(
                path, block_id, content, han_tokens, mixed_tokens,
                content='', tokenize = 'unicode61 tokenchars ''_'''
            )"""
        )

    def replace_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        self.delete_blocks(path, block_id)
        self.insert_block(path, block_id, content, commit=False)
        if commit:
            self.connection.commit()

    def insert_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        raw = content.encode("utf-8")
        compressed = zlib.compress(raw, level=1)
        body = b"z" + compressed if len(compressed) < len(raw) else b"r" + raw
        row = self.connection.execute(
            "INSERT INTO block_text(path, block_id, body) VALUES (?, ?, ?)", (path, block_id, body)
        )
        self.connection.execute(
            "INSERT INTO blocks(rowid, path, block_id, content, han_tokens, mixed_tokens) VALUES (?, ?, ?, ?, ?, ?)",
            (row.lastrowid, path, block_id, content, *_search_tokens(content)),
        )
        if commit:
            self.connection.commit()

    def delete_blocks(self, path: str, block_id: str | None = None) -> None:
        predicate = "path = ?" if block_id is None else "path = ? AND block_id = ?"
        values = (path,) if block_id is None else (path, block_id)
        for rowid, old_id, body in self.connection.execute(
            f"SELECT id, block_id, body FROM block_text WHERE {predicate}", values,
        ):
            content = self._decode(body)
            self.connection.execute(
                "INSERT INTO blocks(blocks, rowid, path, block_id, content, han_tokens, mixed_tokens) "
                "VALUES ('delete', ?, ?, ?, ?, ?, ?)",
                (rowid, path, old_id, content, *_search_tokens(content)),
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
