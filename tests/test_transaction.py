import json
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path

from kbkit.transaction import TransactionError, apply_plan, delete_to_trash, digest, plan_operations, recover_transaction, restore_from_trash
from kbkit.selector import SelectorError, resolve_source
from kbkit.storage import metadata_dir


class CreateTransactionTests(unittest.TestCase):
    def test_new_note_is_created_and_existing_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "first.md"
            request = [{"operation": "create", "path": "first.md", "content": "# First\n"}]
            with chdir(root.parent):
                plan = plan_operations(Path(root.name), request)
            self.assertFalse(path.exists())
            path.touch()
            with self.assertRaises(TransactionError):
                apply_plan(root, plan)
            self.assertEqual(path.read_bytes(), b"")
            path.unlink()
            self.assertEqual(apply_plan(root, plan)["state"], "applied")
            self.assertEqual(path.read_bytes(), b"# First\n")
            with self.assertRaises(TransactionError):
                plan_operations(root, request)


class TransactionTests(unittest.TestCase):
    def test_dry_run_then_apply_multiple_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.md").write_bytes(b"a")
            (root / "b.md").write_bytes(b"b")
            with chdir(root.parent):
                plan = plan_operations(Path(root.name), [{"operation": "append", "path": "a.md", "content": "1", "expected_hash": digest(b"a")}, {"operation": "append", "path": "b.md", "content": "2", "expected_hash": digest(b"b")}])
            self.assertTrue(plan["dry_run"])
            self.assertEqual((root / "a.md").read_bytes(), b"a")
            result = apply_plan(root, plan)
            self.assertEqual(result["state"], "applied")
            self.assertEqual((root / "b.md").read_bytes(), b"b2")

    def test_concurrent_change_stops_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.md"
            path.write_bytes(b"a")
            plan = plan_operations(root, [{"operation": "append", "path": "a.md", "content": "1"}])
            path.write_bytes(b"external")
            with self.assertRaises(TransactionError):
                apply_plan(root, plan)

    def test_recovery_applies_pending_after_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.md"
            path.write_bytes(b"a")
            plan = plan_operations(root, [{"operation": "append", "path": "a.md", "content": "1"}])
            transaction_dir = metadata_dir(root) / "transactions" / plan["transaction_id"]
            transaction_dir.mkdir(parents=True)
            staging = transaction_dir / "0.after"
            staging.write_bytes(b"a1")
            journal = transaction_dir.parent / f"{plan['transaction_id']}.json"
            journal.write_text(json.dumps({"state": "pending", "transaction_id": plan["transaction_id"], "changes": [{"path": "a.md", "before_hash": digest(b"a"), "after_hash": digest(b"a1"), "staging": str(staging)}]}), encoding="utf-8")
            self.assertEqual(recover_transaction(root, journal), "applied")
            self.assertEqual(path.read_bytes(), b"a1")

    def test_move_and_delete_operations_are_planned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_bytes(b"content")
            plan = plan_operations(root, [{"operation": "move", "path": "source.md", "destination": "target.md"}])
            self.assertEqual(len(plan["changes"]), 2)
            applied = apply_plan(root, plan)
            self.assertEqual(applied["state"], "applied")
            self.assertFalse((root / "source.md").exists())
            self.assertEqual((root / "target.md").read_bytes(), b"content")
            delete_plan = plan_operations(root, [{"operation": "delete", "path": "target.md"}])
            result = apply_plan(root, delete_plan)
            self.assertFalse((root / "target.md").exists())
            restored = restore_from_trash(root, result["trash"][0]["entry_id"])
            self.assertEqual(restored["status"], "restored")
            self.assertEqual((root / "target.md").read_bytes(), b"content")

    def test_selector_rejects_ambiguous_locator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "note.md"
            path.write_text("note", encoding="utf-8")
            with self.assertRaises(SelectorError):
                resolve_source(root, {"path": "note.md", "block_id": "note.md:0"})
            self.assertEqual(resolve_source(root, {"block_id": "note.md:0"})[0], path.resolve())

    def test_delete_uses_trash_and_can_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "note.md"
            target.write_bytes(b"keep")
            deleted = delete_to_trash(root, "note.md")
            self.assertFalse(target.exists())
            restored = restore_from_trash(root, deleted["entry_id"])
            self.assertEqual(restored["status"], "restored")
            self.assertEqual(target.read_bytes(), b"keep")

    def test_operation_accepts_structured_block_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "note.md"
            target.write_bytes(b"note")
            plan = plan_operations(root, [{"operation": "append", "selector": {"block_id": "note.md:0"}, "content": "!"}])
            apply_plan(root, plan)
            self.assertEqual(target.read_bytes(), b"note\n!")

    def test_fault_injection_leaves_pending_journal_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.md").write_bytes(b"a")
            (root / "b.md").write_bytes(b"b")
            plan = plan_operations(root, [{"operation": "append", "path": "a.md", "content": "1"}, {"operation": "append", "path": "b.md", "content": "2"}])
            with self.assertRaises(RuntimeError):
                apply_plan(root, plan, fail_after=1)
            journal = metadata_dir(root) / "transactions" / f"{plan['transaction_id']}.json"
            self.assertEqual(recover_transaction(root, journal), "applied")
            self.assertEqual((root / "b.md").read_bytes(), b"b2")
