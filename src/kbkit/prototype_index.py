"""E2 SQLite FTS5 prototype with explicit runtime probing."""

from __future__ import annotations

import re
import sqlite3


_HAN_RUN = re.compile(r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\U00030000-\U000323af]+)")


def _han_phrase(text: str) -> str:
    return " ".join(f"h{ord(char):x}" for char in text)


def _search_tokens(content: str) -> tuple[str, str]:
    parts = _HAN_RUN.split(content)
    han = " boundary ".join(_han_phrase(part) for part in parts[1::2])
    mixed = []
    for index, part in enumerate(parts[::2]):
        if not part:
            continue
        left = re.match(r"\w+", part) if index else None
        right = re.search(r"\w+\Z", part) if index < len(parts) // 2 else None
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
        columns = {row[1] for row in connection.execute("PRAGMA table_info(blocks)")}
        self.rebuild_required = bool(columns and "mixed_tokens" not in columns)
        if self.rebuild_required:
            self.connection.execute("DROP TABLE blocks")
        self.connection.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS blocks USING fts5(
                path, block_id, content, han_tokens, mixed_tokens, tokenize = 'unicode61 tokenchars ''_'''
            )"""
        )

    def replace_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        self.connection.execute("DELETE FROM blocks WHERE path = ? AND block_id = ?", (path, block_id))
        self.insert_block(path, block_id, content, commit=False)
        if commit:
            self.connection.commit()

    def insert_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        self.connection.execute(
            "INSERT INTO blocks(path, block_id, content, han_tokens, mixed_tokens) VALUES (?, ?, ?, ?, ?)",
            (path, block_id, content, *_search_tokens(content)),
        )
        if commit:
            self.connection.commit()

    def search(self, query: str) -> list[tuple[str, str, str]]:
        rows = self.connection.execute(
            "SELECT path, block_id, content FROM blocks WHERE blocks MATCH ? ORDER BY rank, path, block_id", (_match_expression(query),)
        )
        return list(rows)


def fts5_available() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
    except sqlite3.Error:
        return False
    finally:
        connection.close()
    return True
