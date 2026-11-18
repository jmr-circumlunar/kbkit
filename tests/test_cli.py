import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from kbkit.cli import main


class CliTests(unittest.TestCase):
    def test_task_run_executes_full_maintenance_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("# Note\n\ncontent", encoding="utf-8")
            original = sys.argv
            output = io.StringIO()
            try:
                sys.argv = ["kbc", "task", "run", str(root)]
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(), 0)
            finally:
                sys.argv = original
            text = output.getvalue()
            self.assertIn("changed_blocks", text)
            self.assertIn("report_path", text)


if __name__ == "__main__":
    unittest.main()
