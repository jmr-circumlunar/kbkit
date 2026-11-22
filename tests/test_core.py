import tempfile
import unittest
import os
import shutil
import sqlite3
from contextlib import closing
from unittest.mock import patch
from pathlib import Path

from kbkit.core import build_index, init_vault, maintain
from kbkit.state import StateStore
from kbkit.storage import metadata_dir
from kbkit.application import ApplicationService
from kbkit.registry import VaultRegistry
from kbkit.writer import apply_proposal
import hashlib
from kbkit.backup import create_backup, restore_backup, verify_backup


class CoreTests(unittest.TestCase):
    def test_applied_write_reports_index_failure_without_losing_transaction_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            app = ApplicationService(root)
            with patch("kbkit.application._build_index", side_effect=sqlite3.OperationalError("index unavailable")):
                result = app.apply_operations([{"operation": "create", "path": "report.md", "content": "savedcontent"}])
            self.assertEqual(result["state"], "applied")
            self.assertEqual((root / "report.md").read_text(encoding="utf-8"), "savedcontent")
            self.assertTrue(result["index_dirty"])
            self.assertEqual(result["consistency"], {"ok": False, "errors": ["index unavailable"]})
            self.assertEqual(app.index()["blocks"], 1)
            self.assertEqual([hit["path"] for hit in app.search("savedcontent")["hits"]], ["report.md"])

    def test_sqlite_index_leaves_space_for_journal_in_deep_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            vault = base / "vault"
            init_vault(vault)
            legacy_suffix_length = len("/00000000-0000-0000-0000-000000000000/" + "0" * 64 + ".sqlite")
            child_length = 257 - len(str(base)) - 1 - legacy_suffix_length
            self.assertGreater(child_length, 0)
            with patch.dict(os.environ, {"KBKIT_INDEX_DIR": str(base / ("d" * child_length))}):
                app = ApplicationService(vault)
                result = app.apply_operations([{"operation": "create", "path": "deep.md", "content": "deeppath"}])
                self.assertEqual(result["state"], "applied")
                self.assertFalse(result["index_dirty"])
                self.assertEqual([hit["path"] for hit in app.search("deeppath")["hits"]], ["deep.md"])

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
                if metadata_dir(original) != original / ".kbkit":
                    with closing(VaultRegistry()) as registry:
                        copied_id = registry.add(duplicate, identity="copy")
                        self.assertEqual(registry.use(copied_id), duplicate.resolve())
                        self.assertEqual(registry.use(original_id), original.resolve())
                    self.assertNotEqual(copied_id, original_id)
                    self.assertEqual(duplicate_app.search("seedalpha")["hits"], [])
                    self.assertEqual(len(duplicate_app.search("seedbravo")["hits"]), 1)
                    self.assertEqual(len(app.search("seedalpha")["hits"]), 1)
                    return
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
                    self.assertEqual(registry.use(original_id), original.resolve())
                    self.assertEqual(registry.use(copied_id), duplicate.resolve())
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
                    with self.assertRaisesRegex(ValueError, "choose --identity|specify a moved"):
                        registry.add(destination)
                    self.assertEqual(registry.add(destination, identity="moved", moved_from=original), original_id)
                    self.assertEqual(registry.current(), destination.resolve())
                finally:
                    registry.close()
                self.assertEqual(ApplicationService(destination).search("portabilitytoken")["hits"], original_hits)

    def test_init_index_search_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            (root / "note.md").write_text("# Agent\n\nLocal knowledge", encoding="utf-8")
            self.assertEqual(build_index(root), 1)
            self.assertEqual(ApplicationService(root).search("knowledge")["hits"][0]["path"], "note.md")
            self.assertIn("Local knowledge", ApplicationService(root).read("note.md")["content"])

    def test_read_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            with self.assertRaises(ValueError):
                ApplicationService(root).read("../outside.md")

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
            self.assertTrue((metadata_dir(root) / "artifacts" / f"{artifact_id}.txt").exists())
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
            first = root / "one"
            second = root / "two"
            init_vault(first)
            init_vault(second)
            with closing(VaultRegistry(root / "registry")) as registry:
                first_id = registry.add(first)
                second_id = registry.add(second)
                self.assertEqual(registry.current(), second.resolve())
                self.assertEqual(registry.use(first_id), first.resolve())
                self.assertNotEqual(first_id, second_id)

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
            self.assertEqual(ApplicationService(root).search("move me")["hits"][0]["path"], "new.md")

    def test_search_syncs_external_edits_copies_and_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            note = root / "original.md"
            note.write_text("# Note\n\noldtoken", encoding="utf-8")
            self.assertEqual(len(ApplicationService(root).search("oldtoken")["hits"]), 1)
            note.write_text("# Note\n\nnewtoken added", encoding="utf-8")
            self.assertEqual(ApplicationService(root).search("oldtoken")["hits"], [])
            copy = root / "copy.md"
            copy.write_bytes(note.read_bytes())
            self.assertEqual({hit["path"] for hit in ApplicationService(root).search("newtoken")["hits"]}, {"original.md", "copy.md"})
            note.unlink()
            self.assertEqual([hit["path"] for hit in ApplicationService(root).search("newtoken")["hits"]], ["copy.md"])
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
            self.assertEqual(ApplicationService(root).search("oldtoken")["hits"], [])
            self.assertEqual(len(ApplicationService(root).search("newtoken")["hits"]), 1)
