import json
import multiprocessing
import os
import sqlite3
import time
import tempfile
import unittest
from pathlib import Path

from kbkit.prototype_index import FtsIndex, fts5_available
from kbkit.prototype_markdown import parse_document, set_frontmatter_field
from kbkit.prototype_mcp import handle
from kbkit.prototype_lock import file_lock
from kbkit.prototype_transaction import apply_with_journal, recover


def _hold_lock(path: str, ready, release):
    from kbkit.prototype_lock import file_lock

    with file_lock(Path(path)):
        ready.set()
        release.wait(5)


def _acquire_lock(path: str, acquired):
    from kbkit.prototype_lock import file_lock

    with file_lock(Path(path)):
        acquired.set()
from kbkit.application import ApplicationService


class E2PrototypeTests(unittest.TestCase):
    def test_fts5_probe_and_search(self):
        self.assertTrue(fts5_available())
        connection = sqlite3.connect(":memory:")
        try:
            index = FtsIndex(connection)
            index.replace_block("a.md", "b1", "agent knowledge")
            self.assertEqual(index.search("knowledge")[0][:2], ("a.md", "b1"))
        finally:
            connection.close()

    def test_markdown_roundtrip_preserves_body(self):
        raw = b"\xef\xbb\xbf---\r\nstate: draft\r\ntags: old\r\n---\r\n# Title\r\n\r\nbody\r\n"
        updated = set_frontmatter_field(raw, "state", "active")
        self.assertEqual(parse_document(updated).body, parse_document(raw).body)
        self.assertIn(b"tags: old\r\n", updated)
        self.assertTrue(updated.startswith(b"\xef\xbb\xbf---\r\n"))

    def test_transaction_recovery_detects_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "note.md"
            journal = root / "txn.json"
            target.write_bytes(b"before")
            apply_with_journal(target, b"after", journal)
            self.assertEqual(recover(journal), "applied")
            target.write_bytes(b"external")
            journal.write_text(json.dumps({"target": str(target), "before_hash": "x", "after_hash": "y", "state": "pending"}), encoding="utf-8")
            self.assertEqual(recover(journal), "divergent")

    def test_mcp_contract_has_jsonrpc_error(self):
        self.assertEqual(handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["serverInfo"]["name"], "kbkit")
        self.assertTrue({"kb_graph", "kb_lint", "kb_outline"} <= {tool["name"] for tool in handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]})
        self.assertIn("inputSchema", handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"][0])
        self.assertEqual(handle({"jsonrpc": "2.0", "id": 2, "method": "unknown"})["error"]["code"], -32601)
        self.assertEqual(handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_search", "arguments": {"query": ""}}}, None)["result"]["structuredContent"]["code"], "KB_VAULT_NOT_CONFIGURED")

    def test_mcp_tools_call_uses_application_service(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ApplicationService(Path(directory))
            service.initialize()
            (Path(directory) / "note.md").write_text("# note\n", encoding="utf-8")
            response = handle(
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_status", "arguments": {}}},
                service,
            )
            self.assertIn("initialized", response["result"]["content"][0]["text"])
            maintain = handle(
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "kb_maintain", "arguments": {}}},
                service,
            )
            self.assertIn("run_id", maintain["result"]["content"][0]["text"])
            plan = handle(
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "kb_write_plan", "arguments": {"operations": [{"operation": "append", "path": "note.md", "content": "x"}]}}},
                service,
            )
            self.assertIn("dry_run", plan["result"]["content"][0]["text"])

    def test_file_lock_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "lock"
            with file_lock(lock_path):
                self.assertTrue(lock_path.exists())

    @unittest.skipUnless(os.name == "nt", "Windows process lock semantics")
    def test_file_lock_blocks_between_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "lock"
            ready = multiprocessing.Event()
            release = multiprocessing.Event()
            acquired = multiprocessing.Event()
            holder = multiprocessing.Process(target=_hold_lock, args=(str(lock_path), ready, release))
            waiter = multiprocessing.Process(target=_acquire_lock, args=(str(lock_path), acquired))
            holder.start()
            self.assertTrue(ready.wait(5))
            waiter.start()
            time.sleep(0.2)
            self.assertFalse(acquired.is_set())
            release.set()
            self.assertTrue(acquired.wait(5))
            holder.join(5)
            waiter.join(5)
            with file_lock(lock_path):
                self.assertTrue(lock_path.exists())
