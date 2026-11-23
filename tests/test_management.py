"""Exercise the supported vault management workflows through CLI and MCP."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from kbkit.application import ApplicationService
from kbkit.core import init_vault
from kbkit.prototype_mcp import handle
from kbkit.transaction import apply_plan, digest, plan_operations


class ManagementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.vault = base / "vault"
        settings = patch.dict(os.environ, {"KBKIT_HOME": str(base / "state"), "KBKIT_INDEX_DIR": str(base / "index")})
        settings.start()
        self.addCleanup(settings.stop)
        self.profile = init_vault(self.vault)
        self.app = ApplicationService(self.vault)

    def configure(self, settings):
        with self.profile.open("a", encoding="utf-8") as stream:
            stream.write("\n" + settings)

    def note(self, path, data):
        note = self.vault / path
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_bytes(data)
        return note

    def request(self, name, **arguments):
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        return handle(message, self.app, output="structured")["result"]

    def mcp(self, name, **arguments):
        result = self.request(name, **arguments)
        self.assertFalse(result["isError"], result)
        return result["structuredContent"]

    def cli(self, *args, data=None, code=0):
        result = subprocess.run([sys.executable, "-m", "kbkit", *map(str, args)],
                                input=data, capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(result.stdout)

    def test_replace_preserves_frontmatter_subsections_and_document_version(self):
        header = b"\xef\xbb\xbf---\r\nstate: active\r\n---\r\n# Parent\r\n"
        tail = b"## Child\r\npreserve child\r\n# Another\r\npreserve sibling\r\n"
        note = self.note("decision.md", header + b"Old decision\r\n" + tail)
        old_id = self.mcp("kb_search", query="decision")["hits"][0]["block_id"]
        operations = [{"operation": "replace", "selector": {"path": "decision.md", "heading_path": ["Parent"]},
                       "content": "New decision\r\n"}]
        draft = self.mcp("kb_write_plan", operations=operations)
        self.assertIn("-Old decision", draft["previews"][0]["preview"]["diff"])
        self.assertTrue(self.request("kb_write_apply", operations=operations)["isError"])
        result = self.mcp("kb_write_apply", operations=operations, plan_hash=draft["plan_hash"],
                          request_id=draft["transaction_id"])
        self.assertEqual(result["state"], "applied")
        self.assertEqual(note.read_bytes(), header + b"New decision\r\n" + tail)
        stale = self.request("kb_write_apply", operations=[{"operation": "replace", "selector": {"block_id": old_id},
                                                            "content": "Stale"}])
        self.assertTrue(stale["isError"])
        self.assertEqual(stale["structuredContent"]["code"], "KB_SELECTOR_INVALID")
        self.assertEqual(note.read_bytes(), header + b"New decision\r\n" + tail)
        self.assertEqual(self.mcp("kb_search", query="New decision")["hits"][0]["path"], note.name)

    def test_block_start_insertion_preserves_heading_and_rejects_frontmatter_edits(self):
        original = b"---\nkind: note\n---\nWorkday\n=======\n## Work\nOriginal\n"
        note = self.note("daily.md", original)
        forbidden = [{"operation": "insert", "selector": {"path": note.name, "line_range": [2, 2]}, "content": "test"}]
        self.assertTrue(self.request("kb_write_plan", operations=forbidden)["isError"])
        ops = [{"operation": "insert", "selector": {"path": note.name, "heading_path": ["Workday"]},
                "position": "start", "content": "Needs confirmation"}]
        preview = self.cli("write", "plan", self.vault, "-", data=json.dumps(ops))
        self.assertEqual(preview["previews"][0]["position"]["after_line"], 5)
        self.cli("write", "apply", self.vault, "-", "--plan-hash", preview["plan_hash"], data=json.dumps(ops))
        self.assertEqual(note.read_bytes(), original.replace(b"## Work", b"Needs confirmation\n## Work"))

    def test_template_create_validates_fields_and_plan_fingerprint(self):
        self.configure('[templates]\ndaily = "templates/daily.md"\n[gates]\nrequired_fields = ["date", "state"]\n')
        template = self.note("templates/daily.md", b"---\ndate: ${date}\nstate: active\n---\n# ${date}\n\n## Work\n${body}\n")
        operations = [{"operation": "create", "path": "daily.md", "template": "daily",
                       "variables": {"date": "2026-11-23", "body": "Meeting notes"}}]
        first = self.mcp("kb_write_plan", operations=operations)
        template.write_bytes(template.read_bytes().replace(b"## Work", b"## Work details"))
        stale = self.request("kb_write_apply", operations=operations, plan_hash=first["plan_hash"])
        self.assertTrue(stale["isError"])
        self.assertFalse((self.vault / "daily.md").exists())
        self.mcp("kb_write_apply", operations=operations)
        self.assertEqual((self.vault / "daily.md").read_bytes(),
                         b'---\ndate: "2026-11-23"\nstate: active\n---\n# 2026-11-23\n\n## Work details\nMeeting notes\n')
        operations[0]["variables"] = {"body": "Incomplete"}
        self.assertTrue(self.request("kb_write_plan", operations=operations)["isError"])

    def test_gate_and_safe_link_repair_distinguish_active_and_historical(self):
        self.configure("""[gates]
active_prefixes = ["active"]
historical_prefixes = ["history"]
required_entries = ["active/entry.md"]
allowed_roots = ["active", "history"]
name_pattern = "[a-z]+"
required_fields = ["version"]
version_pattern = '[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+'
[gates.link_targets]
Old = "active/target.md"
""")
        self.note("active/target.md", b"---\nversion: 1.2.3.4\n---\n# Target\n")
        original = (b"---\r\nversion: 1.2.3.4\r\n---\r\n# Entry\r\n[[Old|Kept alias]]\r\n"
                    b"[[Old#Anchor]]\r\n" + bytes([96]) + b"[[Old]]" + bytes([96]) + b"\r\n")
        entry = self.note("active/entry.md", original)
        historical = self.note("history/old.md", b"# History\n[[Old]]")
        gate = self.cli("check", self.vault, code=1)
        self.assertFalse(gate["ok"])
        self.assertTrue(any(x["area"] == "historical" and not x["blocking"] for x in gate["findings"]))
        self.assertIn("active/target.md", [x.get("suggested_target") for x in gate["findings"]])
        self.cli("task", "run", self.vault, "--auto-apply", "none")
        self.assertEqual(entry.read_bytes(), original)
        report = self.cli("task", "run", self.vault, "--auto-apply", "safe", "--collection", "automatic_fixes")
        self.assertEqual(report["automatic_fixes"][0]["link_targets"], {"Old": "active/target.md"})
        self.assertEqual(entry.read_bytes(), original.replace(b"[[Old|", b"[[active/target.md|"))
        self.assertEqual(historical.read_bytes(), b"# History\n[[Old]]")
        entry.write_bytes(entry.read_bytes().replace(b"[[Old#Anchor]]", b"Unresolved anchor needs review"))
        self.assertTrue(self.mcp("kb_check")["ok"])
        self.cli("check", self.vault)

    def test_gate_blocks_unresolved_transactions_without_recovering_them(self):
        note = self.note("pending.md", b"# Pending\n")
        operations = [{"operation": "append", "path": note.name, "content": "New content\n"}]
        plan = plan_operations(self.vault, operations, dry_run=False)
        with self.assertRaises(RuntimeError):
            apply_plan(self.vault, plan, fail_after=0)
        result = self.cli("check", self.vault, code=1)
        self.assertEqual(result["findings"][0]["transaction_id"], plan["transaction_id"])
        self.assertEqual(self.app.write_status(plan["transaction_id"])["state"], "pending")
        self.assertEqual(note.read_bytes(), b"# Pending\n")

    def test_external_audit_receipt_is_idempotent_and_checks_applied_writes(self):
        note = self.note("decision.md", b"# Decision\nOld\n")
        self.note("missing-context.md", b"# Follow-up\n")
        transaction = self.mcp("kb_write_apply", operations=[{"operation": "replace",
                               "selector": {"path": note.name, "line_range": [2, 2]}, "content": "New",
                               "expected_hash": digest(note.read_bytes())}])["transaction_id"]
        run = str(uuid4())
        findings = [
            {"path": note.name, "category": "stale", "disposition": "applied", "message": "Reviewed against current evidence",
             "transaction_id": transaction},
            {"path": "missing-context.md", "category": "incomplete", "disposition": "pending", "message": "Ask source owner"},
        ]
        payload = {"run_id": run, "reviewer": "nightly-host", "scope": ["."], "findings": findings}
        first = self.cli("audit", "record", self.vault, "-", data=json.dumps(payload))
        self.assertEqual(self.mcp("kb_audit_record", **payload), first)
        self.assertEqual(first["finding_counts"]["applied"], 1)
        pending = self.cli("audit", "report", self.vault, run, "--disposition", "pending")
        self.assertEqual([x["path"] for x in pending["findings"]], ["missing-context.md"])
        self.assertTrue(self.request("kb_audit_record", **{**payload, "reviewer": "different"})["isError"])
        findings[0]["path"] = "missing-context.md"
        self.assertTrue(self.request("kb_audit_record", **{**payload, "run_id": str(uuid4())})["isError"])
