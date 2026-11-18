"""E2 SQLite FTS5 prototype with explicit runtime probing."""

from __future__ import annotations

import sqlite3


class FtsIndex:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS blocks USING fts5(path, block_id, content)"
        )

    def replace_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        self.connection.execute("DELETE FROM blocks WHERE path = ? AND block_id = ?", (path, block_id))
        self.insert_block(path, block_id, content, commit=False)
        if commit:
            self.connection.commit()

    def insert_block(self, path: str, block_id: str, content: str, commit: bool = True) -> None:
        self.connection.execute("INSERT INTO blocks(path, block_id, content) VALUES (?, ?, ?)", (path, block_id, content))
        if commit:
            self.connection.commit()

    def search(self, query: str) -> list[tuple[str, str, str]]:
        rows = self.connection.execute(
            "SELECT path, block_id, content FROM blocks WHERE blocks MATCH ? ORDER BY rank", (query,)
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
