"""Cross-check Markdown, the document inventory and the derived FTS index."""

import sqlite3
from contextlib import closing
from pathlib import Path

from .storage import markdown_files, metadata_dir
from .transaction import digest
from .vault_profile import index_path


def check_consistency(root: Path) -> dict:
    if not (metadata_dir(root) / "profile.toml").is_file():
        return {"ok": False, "errors": ["vault is not initialized"]}
    database = index_path(root)
    if not database.is_file():
        return {"ok": False, "errors": ["index is missing"]}
    errors = []
    try:
        with closing(sqlite3.connect(database)) as connection:
            indexed = dict(connection.execute("SELECT path, content_hash FROM documents"))
            cached = connection.execute("SELECT count(*) FROM block_text").fetchone()[0]
            searchable = connection.execute("SELECT count(*) FROM blocks").fetchone()[0]
            if cached != searchable:
                errors.append(f"FTS contains {searchable} rows for {cached} cached blocks")
            missing_block_documents = connection.execute(
                "SELECT t.path FROM block_text AS t LEFT JOIN documents AS d ON t.path = d.path "
                "WHERE d.path IS NULL GROUP BY t.path"
            )
            errors.extend(f"orphaned index blocks: {path}" for (path,) in missing_block_documents)
    except sqlite3.DatabaseError as error:
        return {"ok": False, "errors": [f"damaged or incomplete index: {error}"]}
    paths = markdown_files(root)
    errors.extend(f"missing document: {path}" for path in sorted(indexed.keys() - paths.keys()))
    errors.extend(f"unindexed document: {path}" for path in sorted(paths.keys() - indexed.keys()))
    for relative in sorted(indexed.keys() & paths.keys()):
        if digest(paths[relative][0].read_bytes()) != indexed[relative]:
            errors.append(f"hash mismatch: {relative}")
    return {"ok": not errors, "errors": errors}
