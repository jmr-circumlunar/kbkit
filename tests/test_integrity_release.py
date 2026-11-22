"""Regressions from the release integrity exercise and clone onboarding."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from zipfile import BadZipFile, ZIP_STORED, ZipFile

from kbkit.application import ApplicationService
from kbkit.backup import create_backup, restore_backup, verify_backup
from kbkit.consistency import check_consistency
from kbkit.graph import build_graph
from kbkit.knowledge import KnowledgeVault
from kbkit.scheduler import configure, load
from kbkit.storage import metadata_dir
from kbkit.transaction import apply_plan, plan_operations
from kbkit.vault_profile import index_path


class IntegrityRegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        environment = patch.dict(os.environ, {
            "KBKIT_HOME": str(self.base / "meta"),
            "KBKIT_INDEX_DIR": str(self.base / "index"),
            "KBKIT_REGISTRY_DIR": str(self.base / "registry"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.vault = self.base / "vault"
        self.service = ApplicationService(self.vault)
        self.identity = self.service.initialize()["vault_uuid"]

    def run_cli(self, *arguments, stdin=None):
        return subprocess.run([sys.executable, "-m", "kbkit", *map(str, arguments)],
                              input=stdin, capture_output=True, timeout=25)

    def note(self, name, body):
        path = self.vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def test_archive_restores_assets_identity_automation_and_history(self):
        note = self.note("案内/État.md", b"# Source\r\n")
        asset = self.note("graphics/依据.png", b"fixture")
        self.note(".obsidian/app.json", b"{}")
        self.note(".git", b"gitdir: elsewhere")
        self.note(".obsidian/plugins/sample/data.json", b"private plugin state")
        KnowledgeVault(self.vault).review("案内/État.md", [])
        configure(self.vault, "fixture", "0 2 * * *", enabled=True)
        archive = self.base / "archive.zip"
        created = self.run_cli("backup", "create", self.vault, archive)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertTrue(verify_backup(archive)["ok"])
        destination = self.base / "restored"
        outcome = self.run_cli("backup", "restore", archive, destination)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual((destination / "案内/État.md").read_bytes(), note.read_bytes())
        self.assertEqual((destination / "graphics/依据.png").read_bytes(), asset.read_bytes())
        self.assertFalse((destination / ".obsidian/plugins").exists())
        self.assertFalse((destination / ".git").exists())
        self.assertIn("Source", KnowledgeVault(destination).history("案内/État.md", 1)["content"])
        self.assertTrue(load(destination)["enabled"])
        ApplicationService(destination).index()
        self.assertEqual(len(ApplicationService(destination).search("Source")["hits"]), 1)

    def test_bad_archives_and_existing_files_leave_destination_untouched(self):
        self.note("existing.md", b"source")
        archive = self.base / "valid.zip"
        create_backup(self.vault, archive)
        dest = self.base / "existing"
        dest.mkdir()
        original = dest / "existing.md"
        original.write_bytes(b"later edit")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            restore_backup(archive, dest)
        self.assertEqual(original.read_bytes(), b"later edit")

        damaged = self.base / "bad.zip"
        with ZipFile(damaged, "w", compression=ZIP_STORED) as bundle:
            bundle.writestr("first.md", b"would otherwise be written")
            bundle.writestr("last.md", b"last_record_125")
        damaged.write_bytes(damaged.read_bytes().replace(b"last_record_125", b"last_record_126"))
        self.assertFalse(verify_backup(damaged)["ok"])
        dest = self.base / "clean"
        dest.mkdir()
        with self.assertRaises(BadZipFile):
            restore_backup(damaged, dest)
        self.assertEqual(list(dest.iterdir()), [])

    def test_external_move_and_bad_journal_recovery(self):
        self.note("a.md", b"unchanged\n")
        plan = plan_operations(self.vault, [{"operation":"append", "path":"a.md", "content":"applied\n"}])
        with self.assertRaises(RuntimeError):
            apply_plan(self.vault, plan, fail_after=0)
        with self.assertRaisesRegex(ValueError, "pending"):
            create_backup(self.vault, self.base / "pending.zip")
        self.assertFalse((self.base / "pending.zip").exists())
        journals = metadata_dir(self.vault) / "transactions"
        (journals / "000-bad.json").write_bytes(b'{"incomplete"')
        moved = self.base / "moved"
        self.vault.rename(moved)
        added = self.run_cli("add", moved, "--identity", "moved", "--from", self.vault)
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn(self.identity, added.stdout.decode("utf-8"))
        repaired = self.run_cli("recover", moved)
        self.assertEqual(repaired.returncode, 1)
        outcomes = json.loads(repaired.stdout)
        self.assertEqual(outcomes["000-bad.json"]["state"], "error")
        self.assertIn("applied", outcomes.values())
        self.assertEqual((moved / "a.md").read_bytes(), b"unchanged\napplied\n")

    def test_corrupt_index_is_quarantined_and_graph_handles_attachments(self):
        self.note("note.md", b"# Source\n\n![[picture.png]]\n\n\x60\x60\x60\n[[example-only]]\n\x60\x60\x60\n")
        self.note("assets/picture.png", b"image")
        self.service.index()
        self.assertEqual(build_graph(self.vault)["broken"], [])
        db = index_path(self.vault)
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute("DROP TABLE blocks")
        self.assertFalse(check_consistency(self.vault)["ok"])
        self.assertTrue(self.service.search("Source")["hits"])
        db.write_bytes(b"not a sqlite database")
        self.assertTrue(self.service.search("Source")["hits"])
        self.assertTrue(check_consistency(self.vault)["ok"])
        self.assertEqual(len(list(db.parent.glob("*.damaged-*"))), 1)

    def test_strict_state_and_explicit_historical_scope(self):
        profile = metadata_dir(self.vault) / "profile.toml"
        with profile.open("a", encoding="utf-8") as stream:
            stream.write('\n[search]\nrequire_state = true\n[search.exclude]\nprefixes = ["diary"]\n')
        self.note("diary/old.md", b"---\nstate: archived\n---\n# historicmarker\n")
        self.note("missing-state.md", b"# historicmarker\n")
        self.assertEqual(self.service.search("historicmarker")["hits"], [])
        with self.assertRaisesRegex(ValueError, "explicit"):
            self.service.search("historicmarker", include_excluded=True)
        found = self.service.search("historicmarker", path="diary", include_excluded=True, include_inactive=True)
        self.assertEqual([hit["path"] for hit in found["hits"]], ["diary/old.md"])

    def test_cli_setup_generates_routing_and_starter_and_supports_writing(self):
        root = self.base / "Knowledge Base"
        project = self.base / "Agent Project"
        project.mkdir()
        guide = project / "AGENTS.md"
        guide.write_text("# Existing project rule\n", encoding="utf-8")
        for _ in range(2):
            result = self.run_cli("setup", root, "--project", project, "--host", "codex")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(guide.read_text(encoding="utf-8").count("<!-- kbkit: begin -->"), 1)
        self.assertIn("Existing project rule", guide.read_text(encoding="utf-8"))
        self.assertEqual(len(list((project / ".agents" / "skills").glob("*/SKILL.md"))), 5)
        config = tomllib.loads((project / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["mcp_servers"]["kbkit"]["env"]["KBKIT_VAULT"], str(root))
        hooks = json.loads((project / ".codex" / "hooks.json").read_bytes())["hooks"]["SessionStart"]
        self.assertEqual(len(hooks), 1)
        hook = self.run_cli("context", root, "--note", "00-索引/工作空间上下文.md")
        if os.name == "nt":
            native = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                                     str(project / ".codex" / "kbkit-context.ps1")],
                                    capture_output=True, timeout=25)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertEqual(json.loads(native.stdout), json.loads(hook.stdout))
        text = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("kb_search", text)
        self.assertIn("工作空间上下文", text)
        payload = json.dumps([{"operation":"create","path":"first.md","content":"# New\nstandalone-write"}]).encode()
        preview = self.run_cli("write", "plan", root, "-", stdin=payload)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        plan_hash = json.loads(preview.stdout)["plan_hash"]
        applied = self.run_cli("write", "apply", root, "-", "--plan-hash", plan_hash, stdin=payload)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual((root / "first.md").read_bytes(), b"# New\nstandalone-write")

    def test_quick_search_detects_edit_preserving_size_and_mtime(self):
        note = self.note("source.md", b"# Before markerabc\n")
        self.assertTrue(self.service.search("markerabc")["hits"])
        original = note.stat()
        note.write_bytes(b"# Before markerxyz\n")
        os.utime(note, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(self.service.search("markerabc")["hits"], [])
        self.assertTrue(self.service.search("markerxyz")["hits"])
