import tempfile
import unittest
from pathlib import Path

from kbkit.storage import metadata_dir
from kbkit.transaction import TransactionError, apply_plan, plan_operations, recover_transaction


class TransactionMatrixTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "a.md").write_bytes(b"a")
        (self.root / "b.md").write_bytes(b"b")

    def tearDown(self):
        self.directory.cleanup()

    def test_txn_01_staging_and_pending_journal(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}])
        with self.assertRaises(RuntimeError):
            apply_plan(self.root, plan, fail_after=0)
        journal = metadata_dir(self.root) / "transactions" / f"{plan['transaction_id']}.json"
        self.assertEqual(recover_transaction(self.root, journal), "applied")

    def test_txn_02_pending_before_apply(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}])
        result = apply_plan(self.root, plan)
        self.assertEqual(result["state"], "applied")

    def test_txn_03_partial_multi_file_apply(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}, {"operation": "append", "path": "b.md", "content": "2"}])
        with self.assertRaises(RuntimeError):
            apply_plan(self.root, plan, fail_after=1)
        journal = metadata_dir(self.root) / "transactions" / f"{plan['transaction_id']}.json"
        self.assertEqual(recover_transaction(self.root, journal), "applied")

    def test_txn_04_index_failure_boundary_is_recoverable(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}])
        self.assertEqual(apply_plan(self.root, plan)["state"], "applied")

    def test_txn_05_external_commit_boundary_keeps_content(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}])
        result = apply_plan(self.root, plan)
        self.assertEqual(result["state"], "applied")
        self.assertEqual((self.root / "a.md").read_bytes(), b"a1")

    def test_txn_06_concurrent_write_is_rejected(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}])
        (self.root / "a.md").write_bytes(b"external")
        with self.assertRaises(TransactionError):
            apply_plan(self.root, plan)

    def test_txn_07_external_edit_after_plan_is_divergent(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}])
        (self.root / "a.md").write_bytes(b"external")
        with self.assertRaises(TransactionError):
            apply_plan(self.root, plan)
        self.assertEqual((self.root / "a.md").read_bytes(), b"external")

    def test_recovery_is_idempotent_after_second_restart(self):
        plan = plan_operations(self.root, [{"operation": "append", "path": "a.md", "content": "1"}, {"operation": "append", "path": "b.md", "content": "2"}])
        with self.assertRaises(RuntimeError):
            apply_plan(self.root, plan, fail_after=1)
        journal = metadata_dir(self.root) / "transactions" / f"{plan['transaction_id']}.json"
        self.assertEqual(recover_transaction(self.root, journal), "applied")
        self.assertEqual(recover_transaction(self.root, journal), "applied")
        self.assertEqual((self.root / "a.md").read_bytes(), b"a1")
        self.assertEqual((self.root / "b.md").read_bytes(), b"b2")
