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

    def test_stdio_handles_notifications_ping_and_utf8_in_one_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "设计.md").write_text("# 设计\n\n测试内容", encoding="utf-8")
            env = dict(os.environ, KBKIT_VAULT=str(root), PYTHONIOENCODING="ascii")
            requests = [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                "{malformed",
                json.dumps({"jsonrpc": "2.0", "id": "ping", "method": "ping"}),
                json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "kb_read", "arguments": {"path": "设计.md"}}}, ensure_ascii=False),
            ]
            result = subprocess.run(
                [sys.executable, "-m", "kbkit", "mcp", "stdio"], input=("\n".join(requests) + "\n").encode("utf-8"),
                capture_output=True, check=True, env=env, timeout=10,
            )
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(responses), 4)
            self.assertEqual(responses[1]["error"]["code"], -32700)
            self.assertEqual(responses[2], {"jsonrpc": "2.0", "id": "ping", "result": {}})
            self.assertIn("测试内容", responses[3]["result"]["structuredContent"]["content"])
            self.assertEqual(result.stderr, b"")
