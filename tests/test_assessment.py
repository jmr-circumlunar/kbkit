"""Regression coverage for the real-vault assessment findings."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbkit.application import ApplicationService
from kbkit.core import init_vault
from kbkit.prototype_mcp import handle
from kbkit.state import StateStore
from kbkit.storage import metadata_dir
from kbkit.transaction import apply_plan, plan_operations, recover_transaction


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "vault"
        config = patch.dict(os.environ, {"KBKIT_INDEX_DIR": str(self.base / "index"), "KBKIT_HOME": ""})
        config.start()
        self.addCleanup(config.stop)
        self.profile = init_vault(self.root)
        self.app = ApplicationService(self.root)

    def request(self, name, **arguments):
        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments}}, self.app, output="structured")
        self.assertLess(len(json.dumps(response, ensure_ascii=False).encode("utf-8")), 200_000)
        return response["result"]

    def ok(self, name, **arguments):
        result = self.request(name, **arguments)
        self.assertFalse(result["isError"], result["structuredContent"])
        return result["structuredContent"]

    def note(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
        return target

    def configure(self, content):
        with self.profile.open("a", encoding="utf-8") as stream:
            stream.write("\n" + content + "\n")


    def test_interrupted_write_blocks_overlap_and_request_retry_is_idempotent(self):
        from kbkit import transaction

        path = self.note("first.md", "first\n")
        self.note("second.md", "second\n")
        self.note("unrelated.md", "unrelated\n")
        operations = [{"operation": "append", "path": name, "content": " once"}
                      for name in ("first.md", "second.md")]
        preview = self.ok("kb_write_plan", operations=operations)
        options = {"operations": operations, "plan_hash": preview["plan_hash"], "request_id": preview["transaction_id"]}
        recover = transaction._recover
        with patch.object(transaction, "_recover", side_effect=lambda root, journal, record, _: recover(root, journal, record, 1)):
            with self.assertRaisesRegex(RuntimeError, "fault injection"):
                self.app.apply_operations(**options)
        self.assertEqual(self.ok("kb_write_status", transaction_id=options["request_id"])["state"], "pending")
        other = [{"operation": "append", "path": "second.md", "content": " blocked"}]
        pending = self.request("kb_write_apply", operations=other)["structuredContent"]
        self.assertEqual(pending["code"], "KB_WRITE_PENDING")
        self.assertEqual(pending["details"]["transaction_id"], options["request_id"])
        self.ok("kb_write_apply", operations=[{"operation": "append", "path": "unrelated.md", "content": " allowed"}])
        first = self.ok("kb_write_apply", **options)
        second = self.ok("kb_write_apply", **options)
        self.assertEqual(first, second)
        self.assertEqual(path.read_text().count("once"), 1)
        self.assertEqual((self.root / "second.md").read_text().count("once"), 1)
        self.assertFalse((metadata_dir(self.root) / "transactions" / options["request_id"]).exists())
        reused = self.request("kb_write_apply", **{**options, "operations": other})["structuredContent"]
        self.assertEqual(reused["code"], "KB_WRITE_CONFLICT")

    def test_legacy_terminal_receipt_is_archived_without_replaying_write(self):
        from kbkit import transaction

        path = self.note("archived.md", "note\n")
        operations = [{"operation": "append", "path": path.name, "content": " once"}]
        preview = self.ok("kb_write_plan", operations=operations)
        identity = preview["transaction_id"]
        options = {"operations": operations, "plan_hash": preview["plan_hash"], "request_id": identity}
        first = self.ok("kb_write_apply", **options)
        archive = transaction.find_journal(self.root, identity)
        self.assertEqual(archive.parent.name, "receipts")
        active = archive.parent.parent / archive.name
        archive.replace(active)
        self.ok("kb_write_apply", operations=[{"operation": "create", "path": "other.md", "content": "other"}])
        self.assertFalse(active.exists())
        self.assertTrue(archive.is_file())
        self.assertEqual(self.ok("kb_write_status", transaction_id=identity)["state"], "applied")
        self.assertEqual(self.ok("kb_write_apply", **options), first)
        self.assertEqual(path.read_text().count("once"), 1)

    def test_large_preview_pages_share_hash_and_mcp_frame_is_bounded(self):
        from kbkit.paging import json_size

        content = "# Scope\n\n" + ("some context " + "o" * 154 + "\n") * 13
        operations = []
        for i in range(50):
            name = f"many{i}.md"
            self.note(name, content)
            operations.append({"operation": "append", "path": name, "content": "\n" + "r" * 430})
        offset = 0
        fingerprints = set()
        paths = []
        while offset is not None:
            preview = self.ok("kb_write_plan", operations=operations, offset=offset, max_bytes=24_000)
            self.assertEqual(preview["total"], 50)
            fingerprints.add(preview["plan_hash"])
            paths.extend(preview["changes"])
            offset = preview["next_offset"]
        self.assertEqual(len(fingerprints), 1)
        self.assertEqual(paths, [op["path"] for op in operations])
        self.note("wide.md", "# Wide\n" + ("a" * 300 + "\n") * 250)
        response = handle({"jsonrpc": "2.0", "id": "\x01" * 256, "method": "tools/call",
                           "params": {"name": "kb_read", "arguments": {
                               "path": "wide.md", "lines": [1, 251], "max_bytes": 60_000
                           }}}, self.app, output="structured")
        self.assertLessEqual(json_size(response), 60_000)
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["truncated"])
        self.assertTrue(payload["next_lines"])
        self.assertEqual(response["result"]["content"], [])

    def test_scoped_index_refresh_and_config_diagnostics(self):
        unrelated = self.note("elsewhere.md", "distinct old token\n")
        self.note("drafts/keep/note.md", "# Project marker\n")
        self.note("drafts/hide.md", "# Project marker\n")
        self.configure('[unknown_section]\na = 1\n[search]\nallow = ["drafts/keep", "drafts/typo"]\n'
                       '[search.exclude]\nprefixes = ["drafts"]\n[lint]\ndisable = ["FM-STAT"]')
        self.app.index()
        path_read = Path.read_bytes

        def read_bytes(path):
            self.assertNotEqual(path, unrelated)
            return path_read(path)

        with patch.object(Path, "read_bytes", read_bytes):
            result = self.ok("kb_write_apply", operations=[{"operation": "rename", "path": "drafts/keep/note.md",
                                                           "destination": "drafts/keep/new.md"}])
            self.assertFalse(result["index_dirty"])
        status = self.ok("kb_status")
        self.assertEqual(status["excluded_documents"], 1)
        self.assertIn("Unknown profile key: unknown_section", status["config_warnings"])
        self.assertIn("Unknown lint rule: FM-STAT", status["config_warnings"])
        self.assertIn("Path prefix matched no indexed Markdown: drafts/typo", status["config_warnings"])
        self.assertEqual([hit["path"] for hit in self.ok("kb_search", query="Project marker")["hits"]],
                         ["drafts/keep/new.md"])

    def test_precise_selectors_and_preview_token(self):
        path = self.note("guide.md", "\ufeff# Parent\r\nfirst\r\n## Child\r\nsecond\r\n# Other\r\nthird\r\n")
        selectors = [
            {"path": path.name, "line_range": [1, 1]},
            {"block_id": "guide.md:0"},
            {"path": path.name, "heading_path": ["Parent"]},
        ]
        original = path.read_bytes()
        previews = [
            self.ok("kb_write_plan", operations=[{"operation": "append", "selector": selector, "content": "added"}])
            for selector in selectors
        ]
        self.assertEqual([p["previews"][0]["position"]["after_line"] for p in previews], [1, 2, 4])
        self.assertEqual(path.read_bytes(), original)
        for selector, preview in zip(selectors, previews, strict=True):
            path.write_bytes(original)
            operations = [{"operation": "append", "selector": selector, "content": "added"}]
            response = self.ok("kb_write_apply", operations=operations, plan_hash=preview["plan_hash"])
            self.assertEqual(response["positions"][0]["after_line"], preview["previews"][0]["position"]["after_line"])
            position = response["positions"][0]["byte_offset"]
            self.assertEqual(path.read_bytes(), original[:position] + b"added\r\n" + original[position:])
        operations = [{"operation": "append", "selector": selectors[0], "content": "added"}]
        result = self.request("kb_write_apply", operations=operations, plan_hash=previews[0]["plan_hash"])
        self.assertEqual(result["structuredContent"]["code"], "KB_WRITE_CONFLICT")

    def test_selector_errors_and_fenced_headings(self):
        self.note("guide.md", "# Parent\n\n\N{GRAVE ACCENT}\N{GRAVE ACCENT}\N{GRAVE ACCENT}\n# Fake\n"
                  "\N{GRAVE ACCENT}\N{GRAVE ACCENT}\N{GRAVE ACCENT}\n## Dup\n## Dup\n")
        outline = self.ok("kb_outline", path="guide.md")
        self.assertEqual([h["title"] for h in outline["outline"]], ["Parent", "Dup", "Dup"])
        for selector in ({"path": "guide.md", "heading_path": ["Parent", "Dup"]}, {"block_id": "guide.md:99"},
                         {"line_range": "guide.md:9-10"}, {"path": "guide.md", "heading_path": ["Fake"]}):
            result = self.request("kb_write_plan", operations=[{"operation": "append", "selector": selector, "content": "x"}])
            self.assertTrue(result["isError"])
            self.assertEqual(result["structuredContent"]["code"], "KB_SELECTOR_INVALID")

    def test_delete_move_and_restore_survive_interruption(self):
        for i in range(3):
            source = self.note(f"source-{i}.md", "payload")
            prior = self.note(f"remove-{i}.md", f"unique{i}")
            destination = self.root / f"elsewhere/target-{i}.md"
            operations = [{"operation": "move", "path": source.name, "destination": destination.relative_to(self.root).as_posix()},
                          {"operation": "delete", "path": prior.name}]
            plan = plan_operations(self.root, operations)
            with self.assertRaises(RuntimeError):
                apply_plan(self.root, plan, fail_after=1)
            journal = self.profile.parent / "transactions" / f"{plan['transaction_id']}.json"
            self.assertEqual(recover_transaction(self.root, journal), "applied")
            self.assertEqual(recover_transaction(self.root, journal), "applied")
            self.assertFalse(source.exists())
            self.assertFalse(prior.exists())
            self.assertEqual(destination.read_text(), "payload")
            status = self.ok("kb_write_status", transaction_id=plan["transaction_id"])
            entry = status["trash"][0]["entry_id"]
            self.assertEqual(self.ok("kb_restore", entry_id=entry)["status"], "restored")
            self.assertEqual(prior.read_text(), f"unique{i}")
        self.assertTrue(all(file.stat().st_size for file in self.root.glob("*.md")))
        self.ok("kb_sync")
        self.assertEqual(self.ok("kb_search", query="payload")["total_candidates"], 3)

    def test_profile_filters_states_and_same_metadata_edit(self):
        self.configure("""
[search.exclude]
prefixes = ["暂缓"]
allow = ["暂缓/保留"]
[search]
kinds = ["现状", "方案"]
[states]
inactive = ["paused"]
[states.aliases]
"暂停" = "paused"
""")
        self.note("暂缓/hidden.md", "# 架构升级\nWeeklyReportExcelExporter")
        self.note("暂缓一/nearby.md", "# 架构升级\n")
        self.note("暂缓/保留/allow.md", "# 架构升级\n")
        live = self.note("业务/current.md", "---\nstate: '生效'\nkind: 现状\ntags:\n  - 业务\n  - 已核验\n---\n# 架构升级\nWeeklyReportExcelExporter\n")
        self.note("业务/legacy.md", "---\nstate: 已终结\nkind: 现状\ntags: [业务, 已核验]\n---\n# 架构升级\n")
        self.note("业务/paused.md", "---\nstate: 暂停\n---\n# 架构升级\n")
        self.note("业务/unknown.md", "---\nstate: 未知值\n---\n# 架构升级\n")
        self.assertEqual({hit["path"] for hit in self.ok("kb_search", query="架构升级")["hits"]},
                         {"业务/current.md", "暂缓/保留/allow.md", "暂缓一/nearby.md"})
        hits = self.ok("kb_search", query="架构升级", path=["业务"], kind="现状", tags=["业务", "已核验"])["hits"]
        self.assertEqual([hit["path"] for hit in hits], ["业务/current.md"])
        selected = self.ok("kb_search", query="架构升级", state=["已终结", "暂停"])
        self.assertEqual({hit["state"] for hit in selected["hits"]}, {"archived", "paused"})
        symbol = self.ok("kb_search", symbols=["WeeklyReportExcelExporter"])["hits"][0]
        self.assertEqual(symbol["hit_line"], 9)
        source = self.ok("kb_read", block_id=symbol["block_id"])
        self.assertIn("WeeklyReportExcelExporter", source["content"])
        status = self.ok("kb_status")
        self.assertEqual(status["source_state_counts"]["生效"], 1)
        self.assertEqual(status["unknown_state_counts"], {"未知值": 1})
        self.assertEqual(status["excluded_paths"], ["暂缓"])
        stat = live.stat()
        live.write_bytes(live.read_bytes().replace(b"WeeklyReportExcelExporter", b"WeeklyReportExcelExported"))
        os.utime(live, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.ok("kb_sync")
        self.assertEqual(self.ok("kb_search", symbols="WeeklyReportExcelExporter")["total_candidates"], 0)
        self.assertEqual(self.ok("kb_search", symbols="WeeklyReportExcelExported")["total_candidates"], 1)

    def test_large_results_and_targeted_source_read(self):
        self.note("big.md", "# Tiny\nSelected content\n# Big\n" + "数据模型和证据 ⛔ xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n" * 15_000)
        for i in range(931):
            self.note(f"notes/{i:04}.md", "# 数据模型\n[[Missing]]\n" + ("## 数据模型\n" if i < 131 else ""))
        result = self.ok("kb_search", query="数据模型")
        self.assertEqual(result["total_candidates"], 1063)
        self.assertEqual(len(result["hits"]), 8)
        self.assertEqual(result["next_offset"], 8)
        self.assertTrue(result["truncated"])
        next_page = self.ok("kb_search", query="数据模型", offset=8, select="path")
        self.assertTrue({h["block_id"] for h in result["hits"]}.isdisjoint(h["block_id"] for h in next_page["hits"]))
        wide = self.ok("kb_read", path="big.md")
        self.assertNotIn("content", wide)
        self.assertTrue(wide["truncated"])
        outline = self.ok("kb_outline", path="big.md")
        target = self.ok("kb_read", path="big.md", heading=outline["outline"][0]["heading_path"])
        self.assertEqual(target["content"], "# Tiny\nSelected content\n")
        self.assertLess(len(json.dumps([outline, target]).encode()), 2000)
        report = self.ok("kb_maintain", limit=50, max_bytes=4000)
        self.assertTrue(report["truncated"])
        saved = self.ok("kb_maintenance_report", run_id=report["run_id"], offset=report["next_offset"], limit=10)
        self.assertGreater(saved["total"], 1800)
        self.assertTrue(Path(report["report_path"]).is_file())
        self.ok("kb_graph", limit=100, max_bytes=10_000)
        self.ok("kb_lint", limit=100, max_bytes=10_000)
        self.ok("kb_proposals")
        self.ok("kb_facet", dimension="path")

    def test_executable_proposals_and_external_state(self):
        with patch.dict(os.environ, {"KBKIT_HOME": str(self.base / "external")}):
            profile = init_vault(self.root)
            self.assertEqual(profile.parent, metadata_dir(self.root))
            for i in range(20):
                self.note(f"case-{i}.md", f"# Note\nsource {i}")
            state = StateStore(self.root)
            legacy = state.create_proposal("low", "legacy", {"rule": "LINT-L02", "path": "case-0.md"})
            state.close()
            report = self.ok("kb_maintain")
            self.assertEqual(report["proposals"], 20)
            proposals = self.ok("kb_proposals", status="pending")["proposals"]
            self.assertEqual(len(proposals), 20)
            state = StateStore(self.root)
            try:
                self.assertEqual(state.get_proposal(legacy)[3], "expired")
                for item in proposals:
                    state.set_proposal_status(item["proposal_id"], "approved")
                    result = self.ok("kb_proposal_apply", proposal_id=item["proposal_id"])
                    self.assertEqual(result["status"], "applied")
                    self.assertTrue((self.root / result["path"]).read_bytes().endswith(b"\n"))
                self.assertEqual(self.ok("kb_maintain")["proposals"], 0)
            finally:
                state.close()
            self.assertTrue((profile.parent / "reports").is_dir())
            self.assertEqual(list((self.root / ".kbkit").iterdir()), [self.profile])

    def test_mcp_errors_are_actionable_and_protocol_is_negotiated(self):
        self.note("known.md", "# Note ⛔\n")
        response = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
        for tool, args, code in [
            ("kb_search", {"query": "Note", "exclude_paths": ["tmp"]}, "KB_ARGUMENT_INVALID"),
            ("kb_search", {"query": "Note", "kind": "invented"}, "KB_QUERY_ENUM_INVALID"),
            ("kb_search", {"query": "("}, "KB_QUERY_INVALID"),
            ("kb_read", {"path": "missing.md"}, "KB_SELECTOR_INVALID"),
            ("kb_write_plan", {"operations": [{"operation": "append", "path": "known.md", "content": "x", "expected_hash": "bad"}]}, "KB_WRITE_CONFLICT"),
        ]:
            result = self.request(tool, **args)
            self.assertTrue(result["isError"])
            error = result["structuredContent"]
            self.assertEqual(error["code"], code)
            self.assertEqual(set(error), {"code", "message", "severity", "hint", "retryable", "details"})
            self.assertTrue(error["hint"])
        if os.name == "nt":
            args = [sys.executable, "-m", "kbkit", "search", str(self.root), "Note", "--json", "--include-inactive"]
            execution = subprocess.run(args, capture_output=True, env=dict(os.environ, PYTHONIOENCODING="cp936"), check=True)
            self.assertIn("⛔", json.loads(execution.stdout)["hits"][0]["content"])

    def test_concurrent_edit_during_trash_preserves_both_versions(self):
        from kbkit import transaction

        target = self.note("note.md", "original")
        plan = plan_operations(self.root, [{"operation": "delete", "path": "note.md"}])
        trash = transaction._trash

        def external_edit(root, original, record):
            trash(root, original, record)
            target.write_bytes(b"new editor content")

        with patch.object(transaction, "_trash", side_effect=external_edit):
            result = apply_plan(self.root, plan)
        self.assertEqual(result["state"], "divergent")
        self.assertEqual(target.read_bytes(), b"new editor content")
        journal = self.profile.parent / "transactions" / f"{plan['transaction_id']}.json"
        entry = json.loads(journal.read_bytes())["changes"][0]["trash_id"]
        self.assertEqual((self.profile.parent / "trash" / f"{entry}.md").read_bytes(), b"original")
        self.assertEqual(recover_transaction(self.root, journal), "divergent")
        self.assertEqual(target.read_bytes(), b"new editor content")

    def test_stale_block_ids_case_and_quoted_properties(self):
        target = self.note("note.md", "---\nstate: 'active' # retained\n---\nHeading\n=======\nClientFactory and clientfactory\n")
        self.note("case.md", "# lower-case\nclientfactory\n")
        hits = self.ok("kb_search", symbols=["ClientFactory"])["hits"]
        self.assertEqual([item["path"] for item in hits], ["note.md"])
        self.assertEqual(hits[0]["heading_path"], ["Heading"])
        self.assertEqual(self.ok("kb_read", block_id=hits[0]["block_id"])["state"], "active")
        operation = [{"operation": "set_prop", "path": "note.md", "property": "state", "value": "archived"}]
        preview = self.ok("kb_write_plan", operations=operation)
        self.assertIn("+state: \"archived\" # retained", preview["previews"][0]["preview"]["diff"])
        self.ok("kb_write_apply", operations=operation, plan_hash=preview["plan_hash"])
        self.assertIn(b' # retained\n', target.read_bytes())
        self.assertEqual(self.ok("kb_read", path="note.md")["state"], "archived")
        old_id = hits[0]["block_id"]
        self.assertEqual(self.request("kb_read", block_id=old_id)["structuredContent"]["code"], "KB_SELECTOR_INVALID")
        append = [{"operation": "append", "selector": {"block_id": old_id}, "content": "outdated"}]
        self.assertTrue(self.request("kb_write_apply", operations=append)["isError"])
        invalid = [{"operation": "create", "path": "first.md", "content": "x", "destination": "second.md"}]
        self.assertTrue(self.request("kb_write_apply", operations=invalid)["isError"])
        self.assertFalse((self.root / "first.md").exists())

    def test_tiny_payload_budget_and_invalid_stdio_request_id(self):
        self.configure('[search.exclude]\nprefixes = ["' + "长" * 115 + '"]\nallow = ["' + "短" * 115 + '"]')
        self.note("large.md", "# Heading\n" + "a" * 500_000)
        for result in (self.ok("kb_status", max_bytes=512), self.ok("kb_read", path="large.md", max_bytes=512)):
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")), 512)
        self.assertEqual(handle({"jsonrpc": "2.0", "method": "ping", "id": "\ud800"})["error"]["code"], -32600)
