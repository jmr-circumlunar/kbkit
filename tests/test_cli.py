import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from kbkit.cli import main
from kbkit.scheduler import configure


class CliTests(unittest.TestCase):
    def test_task_run_executes_full_maintenance_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = root / "note.md"
            original_text = b"# Note\r\n\r\ncontent"
            note.write_bytes(original_text)
            configure(root, "codex", "daily", auto_apply="safe")
            original_args = sys.argv

            def task(*options):
                output = io.StringIO()
                try:
                    sys.argv = ["kbc", "task", "run", str(root), "--collection", "automatic_fixes", *options]
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(main(), 0)
                finally:
                    sys.argv = original_args
                return json.loads(output.getvalue())

            preview = task("--auto-apply", "none")
            self.assertEqual(preview["proposals"], 1)
            self.assertEqual(note.read_bytes(), original_text)
            report = task()
            self.assertEqual(note.read_bytes(), original_text + b"\r\n")
            self.assertEqual(report["automatic_fix_counts"], {"applied": 1})
            self.assertEqual(report["proposals"], 0)
            self.assertIn("changed_blocks", report)
            fix = report["automatic_fixes"][0]
            saved = json.loads(Path(report["report_path"]).read_bytes())
            self.assertEqual(saved["automatic_fixes"], [fix])
            self.assertEqual(fix["rule"], "FM-FINAL-NEWLINE")
            self.assertNotEqual(fix["before_hash"], fix["after_hash"])
            self.assertEqual(task()["automatic_fixes"], [])


if __name__ == "__main__":
    unittest.main()
