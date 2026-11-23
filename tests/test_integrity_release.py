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
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from kbkit.application import ApplicationService
from kbkit.backup import create_backup, restore_backup, verify_backup
from kbkit.consistency import check_consistency
from kbkit.graph import build_graph
from kbkit.knowledge import KnowledgeVault
from kbkit.scheduler import configure, load
from kbkit.storage import metadata_dir
from kbkit.transaction import apply_plan, plan_operations
from kbkit.vault_profile import index_path, vault_id


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
        self.assertEqual(vault_id(destination), self.identity)
        self.vault.rename(self.base / "old-copy")
        moved = self.run_cli("add", destination, "--identity", "moved")
        self.assertEqual(moved.returncode, 0, moved.stderr)
        self.assertIn(self.identity, moved.stdout.decode("utf-8"))

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

    def test_invalid_deflate_is_reported_and_restore_remains_empty(self):
        damaged = self.base / "deflate.zip"
        with ZipFile(damaged, "w", compression=ZIP_DEFLATED) as bundle:
            bundle.writestr("note.md", b"portable text " * 200)
        data = bytearray(damaged.read_bytes())
        data[30 + len("note.md")] = 0x07  # Invalid deflate block type.
        damaged.write_bytes(data)
        verified = self.run_cli("backup", "verify", damaged)
        self.assertEqual(verified.returncode, 1)
        self.assertNotIn(b"Traceback", verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["first_bad"], "note.md")
        destination = self.base / "clean"
        destination.mkdir()
        restored = self.run_cli("backup", "restore", damaged, destination)
        self.assertEqual(restored.returncode, 1)
        self.assertNotIn(b"Traceback", restored.stderr)
        self.assertEqual(list(destination.iterdir()), [])

    def test_divergent_transaction_can_accept_reconciled_files(self):
        original = self.note("note.md", b"before\n")
        plan = plan_operations(self.vault, [{"operation": "append", "path": "note.md", "content": "proposed\n"}])
        with self.assertRaisesRegex(RuntimeError, "fault injection"):
            apply_plan(self.vault, plan, fail_after=0)
        original.write_bytes(b"reconciled by the user\n")
        options = (self.vault, "--transaction-id", plan["transaction_id"])
        first = self.run_cli("recover", *options)
        self.assertEqual(first.returncode, 1)
        self.assertIn("divergent", json.loads(first.stdout).values())
        archive = self.base / "reconciled.zip"
        with self.assertRaisesRegex(ValueError, "divergent"):
            create_backup(self.vault, archive)
        resolved = self.run_cli("recover", *options, "--accept-current")
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertIn("resolved", json.loads(resolved.stdout).values())
        self.assertEqual(original.read_bytes(), b"reconciled by the user\n")
        create_backup(self.vault, archive)
        self.assertTrue(verify_backup(archive)["ok"])

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
        self.note("note.md", b"# Source\n\n![[picture.png]] | [[note\\|Source]]\n\n\x60\x60\x60\n[[example-only]]\n\x60\x60\x60\n")
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
        self.assertTrue((project / ".agents" / "skills" / "kb-install" / "SKILL.md").is_file())
        config = tomllib.loads((project / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["mcp_servers"]["kbkit"]["env"]["KBKIT_VAULT"], str(root))
        hooks = json.loads((project / ".codex" / "hooks.json").read_bytes())["hooks"]["SessionStart"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["matcher"], "startup|resume|clear|compact|fork")
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

        hook_file = project / ".codex" / "hooks.json"
        hooks[0]["matcher"] = "startup|resume|compact"
        hook_file.write_text(json.dumps({"hooks": {"SessionStart": hooks}}), encoding="utf-8")
        self.assertEqual(self.run_cli("setup", root, "--project", project, "--host", "codex",
                                      "--context-note", "first.md").returncode, 0)
        updated = json.loads(hook_file.read_bytes())["hooks"]["SessionStart"]
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["matcher"], "startup|resume|clear|compact|fork")
        note_hook = self.run_cli("context", root, "--note", "first.md")
        self.assertIn("standalone-write", json.loads(note_hook.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_session_start_detects_external_edit_and_warm_search_never_scans(self):
        note = self.note("source.md", b"# Before markerabc\n")
        initial = self.service.search("markerabc")["hits"][0]
        original = note.stat()
        note.write_bytes(b"# Before markerxyz\n")
        os.utime(note, ns=(original.st_atime_ns, original.st_mtime_ns))
        project = self.base / "session project"
        installed = self.run_cli("setup", self.vault, "--project", project, "--host", "codex")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        note.write_bytes(b"# Before markertwo\n")
        with self.assertRaisesRegex(ValueError, "earlier document version"):
            self.service.read(block_id=initial["block_id"])
        hook = json.loads((project / ".codex" / "hooks.json").read_bytes())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        clean_environment = {key: value for key, value in os.environ.items()
                             if key not in {"KBKIT_HOME", "KBKIT_INDEX_DIR", "KBKIT_REGISTRY_DIR"}}

        def event(source):
            run = subprocess.run(hook, shell=os.name != "nt", input=json.dumps({"source": source}).encode(),
                                 capture_output=True, timeout=25, env=clean_environment)
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(run.stdout)
            self.assertNotIn("systemMessage", payload)
            self.assertIn("kb_search", payload["hookSpecificOutput"]["additionalContext"])

        with patch("kbkit.core.index_sources", side_effect=AssertionError("warm lookup scanned Markdown")):
            event("compact")
            self.assertTrue(self.service.search("markerxyz")["hits"])
            self.assertFalse(self.service.search("markertwo")["hits"])
            self.service.facet()
            self.service.status()
        event("startup")
        self.assertFalse(self.service.search("markerxyz")["hits"])
        self.assertTrue(self.service.search("markertwo")["hits"])
        self.assertEqual(self.service.apply_operations([{"operation": "append", "path": note.name,
                                                         "content": " immediatelyindexed"}])["state"], "applied")
        self.assertTrue(self.service.search("immediatelyindexed")["hits"])

    def test_broken_profile_status_returns_diagnostics_and_search_fails_closed(self):
        profile = metadata_dir(self.vault) / "profile.toml"
        with profile.open("a", encoding="utf-8") as stream:
            stream.write("\n[search]\nrequire_state = true\n[search]\n")
        status = self.run_cli("status", self.vault, "--max-bytes", "512")
        self.assertEqual(status.returncode, 0, status.stderr)
        result = json.loads(status.stdout)
        self.assertFalse(result["profile_valid"])
        self.assertIn("profile.toml", result["profile_error"])
        self.assertIn("line", result["profile_error"])
        search = self.run_cli("search", self.vault, "marker", "--json")
        self.assertEqual(search.returncode, 1)
        self.assertIn(b"invalid vault profile", search.stderr)

    def test_git_sync_fast_forwards_only_and_indexes_the_result(self):
        seed = self.base / "seed"
        seed.mkdir()
        bare = self.base / "remote.git"

        def git(cwd, *args):
            result = subprocess.run(["git", *map(str, args)], cwd=cwd, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.decode("utf-8").strip()

        def commit(cwd, marker):
            (cwd / "tracked.md").write_text(f"# Vault\n\n{marker}\n", encoding="utf-8")
            git(cwd, "add", "--", "tracked.md")
            git(cwd, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", marker)

        git(seed, "init", "--initial-branch=main")
        commit(seed, "oldmarker")
        git(self.base, "clone", "--bare", seed, bare)
        git(self.base, "clone", bare, self.vault)
        self.service.sync()
        self.assertTrue(self.service.search("oldmarker")["hits"])
        profile = metadata_dir(self.vault) / "profile.toml"
        with profile.open("a", encoding="utf-8") as stream:
            stream.write('\n[git]\nremote = "origin"\nbranch = "main"\n')
        commit(seed, "newmarker")
        git(seed, "push", bare, "main")
        self.service.sync()
        self.assertFalse(self.service.search("newmarker")["hits"])

        local = self.vault / "tracked.md"
        original = local.read_bytes()
        local.write_bytes(b"local edits")
        blocked = self.run_cli("sync", self.vault, "--git")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn(b"local changes", blocked.stderr)
        self.assertEqual(local.read_bytes(), b"local edits")
        local.write_bytes(original)
        synced = self.run_cli("sync", self.vault, "--git")
        self.assertEqual(synced.returncode, 0, synced.stderr)
        self.assertEqual(json.loads(synced.stdout)["git_status"], "updated")
        self.assertTrue(self.service.search("newmarker")["hits"])
        self.assertFalse(self.service.search("oldmarker")["hits"])
        commit(seed, "upstreamonly")
        git(seed, "push", bare, "main")
        commit(self.vault, "localonly")
        before = git(self.vault, "rev-parse", "HEAD")
        rejected = self.run_cli("sync", self.vault, "--git")
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(git(self.vault, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.vault, "for-each-ref", "refs/kbkit/sync"), "")
