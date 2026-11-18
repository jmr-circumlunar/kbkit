import tempfile
import unittest
import os
import shutil
from unittest.mock import patch
from pathlib import Path

from kbkit.core import build_index, init_vault, maintain, read, search
from kbkit.state import StateStore
from kbkit.application import ApplicationService
from kbkit.registry import VaultRegistry
from kbkit.writer import apply_proposal
import hashlib
from kbkit.backup import create_backup, restore_backup, verify_backup
from kbkit.git_adapter import commit, status


class CoreTests(unittest.TestCase):
    def test_copied_vaults_never_share_index_and_explicit_copy_gets_own_id(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.dict(os.environ, {"KBKIT_INDEX_DIR": str(base / "index"), "KBKIT_REGISTRY_DIR": str(base / "registry")}):
                original, duplicate = base / "original", base / "duplicate"
                app = ApplicationService(original)
                original_id = app.initialize()["vault_uuid"]
                (original / "note.md").write_text("# Note\nseedalpha", encoding="utf-8")
                app.index()
                shutil.copytree(original, duplicate)
                moved_note = duplicate / "note.md"
                timestamp = moved_note.stat()
                moved_note.write_text("# Note\nseedbravo", encoding="utf-8")
                os.utime(moved_note, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
                duplicate_app = ApplicationService(duplicate)
                self.assertEqual(duplicate_app.search("seedalpha")["hits"], [])
                self.assertEqual(len(duplicate_app.search("seedbravo")["hits"]), 1)
                self.assertEqual(len(app.search("seedalpha")["hits"]), 1)
                registry = VaultRegistry()
                try:
                    with self.assertRaisesRegex(ValueError, "choose --identity"):
                        registry.add(duplicate)
                    with self.assertRaisesRegex(ValueError, "identity must"):
                        registry.add(duplicate, identity="invalid")
                    with self.assertRaisesRegex(ValueError, "original vault still exists"):
                        registry.add(duplicate, identity="moved")
                    copied_id = registry.add(duplicate, identity="copy")
                    self.assertNotEqual(copied_id, original_id)
                    self.assertEqual(registry.use(original_id), original)
                    self.assertEqual(registry.use(copied_id), duplicate)
                finally:
                    registry.close()

    def test_moved_vault_rebuilds_index_and_retains_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.dict(os.environ, {"KBKIT_INDEX_DIR": str(base / "index"), "KBKIT_REGISTRY_DIR": str(base / "registry")}):
                original, destination = base / "original", base / "destination"
                app = ApplicationService(original)
                original_id = app.initialize()["vault_uuid"]
                note = original / "note.md"
                note.write_text("# Note\nportabilitytoken", encoding="utf-8")
                original_hits = app.search("portabilitytoken")["hits"]
                original.rename(destination)
                registry = VaultRegistry()
                try:
                    with self.assertRaisesRegex(ValueError, "choose --identity"):
                        registry.add(destination)
                    self.assertEqual(registry.add(destination, identity="moved"), original_id)
                    self.assertEqual(registry.current(), destination)
                finally:
                    registry.close()
                self.assertEqual(ApplicationService(destination).search("portabilitytoken")["hits"], original_hits)

    def test_init_index_search_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            (root / "note.md").write_text("# Agent\n\nLocal knowledge", encoding="utf-8")
            self.assertEqual(build_index(root), 1)
            self.assertEqual(search(root, "knowledge")[0][0], "note.md")
            self.assertIn("Local knowledge", read(root, "note.md"))

    def test_read_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            with self.assertRaises(ValueError):
                read(root, "../outside.md")

    def test_state_store_records_task_and_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root)
            event_id = store.record_event("session", "today", None, "hash", "1")
            run_id = store.start_task("daily-maintain", "1")
            store.finish_task(run_id, "succeeded", "report.json")
            proposal_id = store.create_proposal("low", "missing provenance", {"path": "note.md"})
            store.set_proposal_status(proposal_id, "approved")
            artifact_id = store.record_session_artifact("session-1", "approved decision", "30d", True)
            self.assertTrue(event_id and run_id and proposal_id)
            self.assertTrue((root / ".kbkit" / "artifacts" / f"{artifact_id}.txt").exists())
            store.close()

    def test_session_artifact_requires_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            with self.assertRaises(ValueError):
                store.record_session_artifact("session-1", "private", "30d", False)
            store.close()

    def test_application_service_initializes_and_reports_status(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ApplicationService(Path(directory))
            result = service.initialize()
            self.assertTrue(result["vault_uuid"])
            self.assertTrue(service.status()["initialized"])

    def test_registry_can_switch_vaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = VaultRegistry(root / "registry")
            first = root / "one"
            second = root / "two"
            init_vault(first)
            init_vault(second)
            first_id = registry.add(first)
            second_id = registry.add(second)
            self.assertEqual(registry.current(), second)
            self.assertEqual(registry.use(first_id), first)
            self.assertNotEqual(first_id, second_id)
            registry.close()

    def test_approved_proposal_applies_with_hash_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            note = root / "note.md"
            note.write_text("# Note\n", encoding="utf-8")
            expected = hashlib.sha256(note.read_bytes()).hexdigest()
            store = StateStore(root)
            proposal_id = store.create_proposal("low", "append note", {"operation": "append", "path": "note.md", "content": "\nnew\n", "expected_hash": expected})
            store.set_proposal_status(proposal_id, "approved")
            store.close()
            result = apply_proposal(root, proposal_id)
            self.assertEqual(result["status"], "applied")
            self.assertIn("new", note.read_text(encoding="utf-8"))

    def test_proposal_conflict_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            note = root / "note.md"
            note.write_text("# Note\n", encoding="utf-8")
            expected = hashlib.sha256(note.read_bytes()).hexdigest()
            store = StateStore(root)
            proposal_id = store.create_proposal("low", "append note", {"operation": "append", "path": "note.md", "content": "\nnew\n", "expected_hash": expected})
            store.set_proposal_status(proposal_id, "approved")
            store.close()
            note.write_text("# Changed\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_proposal(root, proposal_id)
            self.assertEqual(note.read_text(encoding="utf-8"), "# Changed\n")

    def test_backup_verifies_markdown_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            (root / "note.md").write_text("backup", encoding="utf-8")
            archive = root / "backup.zip"
            create_backup(root, archive)
            result = verify_backup(archive)
            self.assertTrue(result["ok"])
            self.assertIn("note.md", result["files"])
            restored = root / "restored"
            restore_backup(archive, restored)
            self.assertEqual((restored / "note.md").read_text(encoding="utf-8"), "backup")

    def test_git_status_is_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            result = status(Path(directory))
            self.assertIn("available", result)

    def test_git_status_and_commit_in_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import subprocess

            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            (root / "note.md").write_text("versioned", encoding="utf-8")
            self.assertTrue(status(root)["available"])
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
            self.assertTrue(commit(root, "test snapshot")["committed"])

    def test_application_service_writes_and_reindexes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = ApplicationService(root)
            service.initialize()
            (root / "note.md").write_text("# Note\n", encoding="utf-8")
            service.index()
            result = service.apply_operations([{"operation": "append", "path": "note.md", "content": "\nindexed"}])
            self.assertEqual(result["state"], "applied")
            self.assertTrue(service.search("indexed")["hits"])
            self.assertTrue(result["consistency"]["ok"])

    def test_index_tracks_content_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            old = root / "old.md"
            new = root / "new.md"
            old.write_text("# Stable\n\nmove me", encoding="utf-8")
            build_index(root)
            old.rename(new)
            build_index(root)
            self.assertEqual(search(root, "move me")[0][0], "new.md")

    def test_search_syncs_external_edits_copies_and_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            note = root / "original.md"
            note.write_text("# Note\n\noldtoken", encoding="utf-8")
            self.assertEqual(len(search(root, "oldtoken")), 1)
            note.write_text("# Note\n\nnewtoken added", encoding="utf-8")
            self.assertEqual(search(root, "oldtoken"), [])
            copy = root / "copy.md"
            copy.write_bytes(note.read_bytes())
            self.assertEqual({hit[0] for hit in search(root, "newtoken")}, {"original.md", "copy.md"})
            note.unlink()
            self.assertEqual([hit[0] for hit in search(root, "newtoken")], ["copy.md"])
            store = StateStore(root)
            try:
                events = store.connection.execute(
                    "SELECT before_hash, after_hash FROM change_events WHERE source_ref = ?", ("original.md",)
                ).fetchall()
            finally:
                store.close()
            self.assertEqual(len(events), 3)
            self.assertIsNone(events[-1][1])
            self.assertEqual(events[-1][0], events[1][1])

    def test_maintenance_detects_edits_with_unchanged_mtime_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = root / "note.md"
            note.write_text("# Note\n\noldtoken", encoding="utf-8")
            build_index(root)
            stat = note.stat()
            note.write_text("# Note\n\nnewtoken", encoding="utf-8")
            os.utime(note, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.assertEqual(maintain(root)["changed_blocks"], 1)
            self.assertEqual(search(root, "oldtoken"), [])
            self.assertEqual(len(search(root, "newtoken")), 1)
