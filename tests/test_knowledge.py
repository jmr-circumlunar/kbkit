import subprocess
import tempfile
import unittest
from pathlib import Path

from kbkit.application import ApplicationService
from kbkit.backup import create_backup, restore_backup
from kbkit.code_sync import bind_code
from kbkit.core import init_vault, maintain
from kbkit.knowledge import KnowledgeVault


class KnowledgeTests(unittest.TestCase):
    def test_design_revision_invalidates_dependents_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vault"
            init_vault(root)
            design = root / "design.md"
            design.write_text("# Design\nfirstdesign", encoding="utf-8")
            (root / "guide.md").write_text("# Guide\noldguide", encoding="utf-8")
            (root / "runbook.md").write_text("# Runbook\noldrunbook", encoding="utf-8")
            (root / "archive.md").write_text("---\nstate: archived\n---\n# Archive\noldarchive", encoding="utf-8")
            knowledge = KnowledgeVault(root)
            knowledge.review("design.md", [])
            knowledge.review("guide.md", ["design.md"])
            knowledge.review("runbook.md", ["guide.md"])
            with self.assertRaisesRegex(ValueError, "cycle"):
                knowledge.review("design.md", ["runbook.md"])
            service = ApplicationService(root)
            self.assertEqual(len(service.search("oldrunbook")["hits"]), 1)
            self.assertEqual(service.search("oldarchive")["hits"], [])
            design.write_text("# Design\nseconddesign", encoding="utf-8")
            self.assertEqual(service.search("oldrunbook")["hits"], [])
            self.assertEqual(service.search("oldrunbook", True)["hits"][0]["reason"], "dependency_inactive")
            self.assertEqual(service.search("seconddesign", True)["hits"][0]["state"], "unreviewed")
            knowledge.review("design.md", None)
            with self.assertRaisesRegex(ValueError, "current dependency"):
                knowledge.review("runbook.md", None)
            (root / "guide.md").write_text("# Guide\nnewguide", encoding="utf-8")
            knowledge.review("guide.md", None)
            self.assertEqual(service.search("oldrunbook")["hits"], [])
            knowledge.review("runbook.md", None)
            self.assertEqual(len(service.search("oldrunbook")["hits"]), 1)
            self.assertEqual(service.search("firstdesign")["hits"], [])
            archive = root.parent / "backup.zip"
            create_backup(root, archive)
            restored = root.parent / "restored"
            restore_backup(archive, restored)
            self.assertIn("firstdesign", KnowledgeVault(restored).history("design.md", 1)["content"])
            self.assertEqual(KnowledgeVault(restored).statuses()["runbook.md"]["state"], "active")

    def test_daily_maintenance_refreshes_committed_code_and_flags_related_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            repo = workspace / "repo"
            repo.mkdir()

            def git(*args):
                subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

            def commit():
                git("add", ".")
                git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture revision")

            git("init", "-b", "main")
            (repo / "src").mkdir()
            source = repo / "src" / "example.py"
            source.write_text("def oldentry():\n    return 'privatebody'\n", encoding="utf-8")
            commit()
            root = workspace / "vault"
            init_vault(root)
            page = bind_code(KnowledgeVault(root), "example", repo, "refs/heads/main", ["src"])["page"]
            first = maintain(root)["code_sync"][0]
            self.assertEqual(first["status"], "updated")
            old_page = (root / page).read_bytes()
            self.assertIn(b"oldentry (line 1)", old_page)
            self.assertNotIn(b"privatebody", old_page)
            (root / "guide.md").write_text("# Guide\nreferenceguide", encoding="utf-8")
            KnowledgeVault(root).review("guide.md", [page])
            source.write_text("def newentry():\n    pass\n", encoding="utf-8")
            self.assertEqual(maintain(root)["code_sync"][0]["status"], "unchanged")
            commit()
            report = maintain(root)
            self.assertEqual(report["code_sync"][0]["previous_commit"], first["commit"])
            self.assertEqual(report["knowledge"]["guide.md"]["state"], "stale")
            service = ApplicationService(root)
            self.assertEqual(service.search("referenceguide")["hits"], [])
            self.assertEqual(service.search("oldentry")["hits"], [])
            self.assertEqual(service.search("newentry")["hits"][0]["path"], page)
            (repo / "unrelated.md").write_text("# Unrelated", encoding="utf-8")
            commit()
            self.assertEqual(maintain(root)["code_sync"][0]["status"], "unchanged")
            self.assertEqual(len(list((root / "_generated" / "code").glob("*.md"))), 1)
            (root / page).write_text("# Human-edited\nmanualedit", encoding="utf-8")
            conflicted = maintain(root)
            self.assertEqual(conflicted["status"], "partial")
            self.assertEqual(conflicted["code_sync"][0]["status"], "conflicted")
            self.assertIn("manualedit", (root / page).read_text(encoding="utf-8"))
            self.assertEqual(service.search("manualedit")["hits"], [])
            git("branch", "-m", "renamed")
            self.assertEqual(maintain(root)["code_sync"][0]["status"], "unverified")
