import json
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from kbkit import writer
from kbkit.core import maintain
from kbkit.knowledge import KnowledgeVault
from kbkit.state import StateStore
from kbkit.storage import metadata_dir


class MaintenanceTests(unittest.TestCase):
    def test_maintain_records_run_and_reports_pending_proposals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("# Note\n\ncontent", encoding="utf-8")
            state = StateStore(root)
            state.create_proposal("low", "review", {"path": "note.md"})
            state.close()
            report = maintain(root)
            self.assertEqual(report["blocks"], 1)
            self.assertEqual(report["changed_blocks"], 1)
            self.assertGreaterEqual(report["proposals"], 1)
            self.assertIn("findings", report)
            self.assertIn("graph", report)
            self.assertTrue(Path(report["report_path"]).exists())
            second = maintain(root)
            self.assertEqual(second["proposals"], report["proposals"])
            self.assertEqual(second["blocks"], 1)
            self.assertEqual(second["changed_blocks"], 0)

    def test_safe_run_resumes_applied_transaction_after_status_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = root / "note.md"
            note.write_bytes(b"# Note\n\ncontent")
            with patch.object(StateStore, "set_proposal_status", side_effect=OSError("interrupted")):
                first = maintain(root, auto_apply="safe")
            self.assertEqual(first["status"], "partial")
            self.assertEqual(first["automatic_fixes"][0]["status"], "failed")
            self.assertEqual(note.read_bytes(), b"# Note\n\ncontent\n")
            second = maintain(root, auto_apply="safe")
            self.assertEqual(second["status"], "succeeded")
            fix = second["automatic_fixes"][0]
            self.assertEqual(fix["proposal_id"], first["automatic_fixes"][0]["proposal_id"])
            self.assertEqual(fix["status"], "applied")
            self.assertEqual(note.read_bytes(), b"# Note\n\ncontent\n")

    def test_safe_run_respects_hash_conflicts_rejections_and_tracked_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b"# Note\n\ncontent"
            for name in ("external.md", "rejected.md", "tracked.md"):
                (root / name).write_bytes(original)
            maintain(root)
            with closing(StateStore(root)) as state:
                rows = state.proposal_page("pending", 10, 0)[1]
                rejected = next(row for row in rows if row["payload"]["path"] == "rejected.md")
                state.set_proposal_status(rejected["proposal_id"], "rejected")
            KnowledgeVault(root).review("tracked.md", [])
            plan = writer.plan_operations

            def external_edit(vault, operations, **options):
                self.assertEqual([op["path"] for op in operations], ["external.md"])
                (root / "external.md").write_bytes(b"Unrelated editor change")
                return plan(vault, operations, **options)

            with patch.object(writer, "plan_operations", side_effect=external_edit):
                report = maintain(root, auto_apply="safe")
            self.assertEqual(report["status"], "partial")
            self.assertEqual([item["path"] for item in report["automatic_fixes"]], ["external.md"])
            self.assertIn("hash conflict", report["automatic_fixes"][0]["error"])
            self.assertEqual((root / "external.md").read_bytes(), b"Unrelated editor change")
            self.assertEqual((root / "rejected.md").read_bytes(), original)
            self.assertEqual((root / "tracked.md").read_bytes(), original)

    def test_failed_index_keeps_already_applied_fixes_in_the_run_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = root / "note.md"
            note.write_bytes(b"# Note\n\nNo final newline")
            with patch("kbkit.core._build_index", side_effect=OSError("cache is unavailable")):
                with self.assertRaisesRegex(OSError, "cache is unavailable"):
                    maintain(root, auto_apply="safe")
            (report_path,) = (metadata_dir(root) / "reports").glob("*.json")
            report = json.loads(report_path.read_bytes())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["automatic_fixes"][0]["status"], "applied")
            self.assertTrue(note.read_bytes().endswith(b"\n"))

    def test_resolved_finding_expires_pending_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = root / "note.md"
            note.write_text("# Note\n\ncontent", encoding="utf-8")
            first = maintain(root)
            self.assertEqual(first["proposals"], 1)
            note.write_text("---\nsource: user\nowner: me\n---\n# Note\n\ncontent\n", encoding="utf-8")
            second = maintain(root)
            self.assertGreaterEqual(second["expired_proposals"], 1)
