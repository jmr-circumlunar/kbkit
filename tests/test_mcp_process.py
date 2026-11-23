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
            environment.pop("KBKIT_MCP_OUTPUT", None)
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
            self.assertTrue({"kb_graph", "kb_lint", "kb_outline"} <= {tool["name"] for tool in responses[1]["result"]["tools"]})
            result = responses[2]["result"]
            self.assertNotIn("structuredContent", result)
            self.assertFalse(json.loads(result["content"][0]["text"])["initialized"])

    def test_stdio_handles_notifications_ping_and_utf8_in_one_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "设计.md").write_text("# 设计\n\n测试内容", encoding="utf-8")
            env = dict(os.environ, KBKIT_VAULT=str(root), PYTHONIOENCODING="ascii", KBKIT_MCP_OUTPUT="text")
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
            self.assertIn("测试内容", json.loads(responses[3]["result"]["content"][0]["text"])["content"])
            self.assertEqual(result.stderr, b"")

    def test_both_output_modes_send_one_payload_and_bound_escaped_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notes = ('中文"' + "\\" * 48 + "\t example ") * 4 + "\n"
            (root / "large.md").write_bytes((notes * 240).encode("utf-8"))
            for mode in ("text", "structured"):
                with self.subTest(mode=mode):
                    environment = dict(os.environ, KBKIT_VAULT=str(root), KBKIT_MCP_OUTPUT=mode)
                    protocol = {"jsonrpc": "2.0"}
                    messages = [
                        {**protocol, "id": 1, "method": "initialize"},
                        {**protocol, "method": "notifications/initialized"},
                        {**protocol, "id": "\x01" * 256, "method": "tools/call",
                         "params": {"name": "kb_read", "arguments": {"path": "large.md", "lines": [1, 240], "max_bytes": 60_000}}},
                        {**protocol, "id": 3, "method": "tools/call",
                         "params": {"name": "kb_read", "arguments": {"path": "missing.md"}}},
                    ]
                    process = subprocess.run(
                        [sys.executable, "-m", "kbkit", "mcp", "stdio"],
                        input=("\n".join(map(json.dumps, messages)) + "\n").encode("utf-8"),
                        capture_output=True, check=True, env=environment, timeout=10,
                    )
                    lines = process.stdout.splitlines()
                    self.assertEqual(len(lines), 3)
                    self.assertTrue(all(len(line) <= 60_000 for line in lines))
                    response, error = (json.loads(line)["result"] for line in lines[1:])
                    for result in (response, error):
                        if mode == "structured":
                            self.assertEqual(result["content"], [])
                            self.assertIn("structuredContent", result)
                        else:
                            self.assertNotIn("structuredContent", result)
                            self.assertEqual(len(result["content"]), 1)
                    data = (response["structuredContent"] if mode == "structured"
                            else json.loads(response["content"][0]["text"]))
                    self.assertFalse(response["isError"])
                    self.assertTrue(error["isError"])
                    self.assertTrue(data["truncated"])
                    self.assertGreater(data["next_lines"][0], 1)
                    self.assertTrue(data["content"].startswith(notes))
