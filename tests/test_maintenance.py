import tempfile
import unittest
from pathlib import Path

from kbkit.core import maintain
from kbkit.state import StateStore


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
