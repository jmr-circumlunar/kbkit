import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class McpProcessTests(unittest.TestCase):
    def test_stdio_process_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("# Note\n\nagent process", encoding="utf-8")
            environment = os.environ.copy()
            environment["KBKIT_VAULT"] = str(root)
            process = subprocess.Popen(
                [sys.executable, "-m", "kbkit", "mcp", "stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_status", "arguments": {}}},
            ]
            process_input = "\n".join(json.dumps(request) for request in requests) + "\n"
            output, error = process.communicate(process_input, timeout=10)
            self.assertEqual(process.returncode, 0, error)
            responses = [json.loads(line) for line in output.splitlines()]
            self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "kbkit")
            self.assertEqual(len(responses[1]["result"]["tools"]), 8)
            self.assertIn("initialized", responses[2]["result"]["content"][0]["text"])
