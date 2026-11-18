import tempfile
import unittest
from pathlib import Path

from kbkit.scheduler import configure, load


class SchedulerTests(unittest.TestCase):
    def test_agent_host_schedule_is_persisted_and_editable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = configure(root, "codex", "daily")
            self.assertEqual(load(root)["task_id"], first["task_id"])
            second = configure(root, "claude-code", "weekly")
            self.assertNotEqual(second["task_id"], first["task_id"])
            self.assertEqual(load(root)["host"], "claude-code")

    def test_safe_auto_apply_and_generated_content_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = configure(root, "codex", "daily", generated_content="enabled", generated_root="_generated/code")
            self.assertEqual(record["auto_apply"], "safe")
            self.assertEqual(record["generated_content"], "enabled")
            self.assertEqual(record["generated_root"], "_generated/code")
            with self.assertRaises(ValueError):
                configure(root, "codex", "daily", generated_root="../outside")
