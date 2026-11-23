import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from kbkit.application import ApplicationService
from kbkit.core import init_vault
from kbkit.vault_profile import index_path


class SearchQualityTests(unittest.TestCase):
    def test_compact_index_replaces_and_deletes_chinese_postings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            original = root / "guide.md"
            original.write_text("# 实施流程\n\n" + "使用旧版连接池复核方案。\n" * 40, encoding="utf-8")
            other = root / "other.md"
            other.write_text("# 备用流程\n\n使用连接池复核方案。", encoding="utf-8")
            app = ApplicationService(root)
            hit = app.search("旧版")["hits"][0]
            self.assertIn("旧版连接池复核方案", hit["content"])
            original.write_text("# 实施流程\n\n" + "使用新版连接池复核方案。\n" * 40, encoding="utf-8")
            app.sync()
            self.assertEqual(app.search("旧版")["hits"], [])
            self.assertEqual([row["path"] for row in app.search("新版")["hits"]], [original.name])
            original.unlink()
            app.sync()
            self.assertEqual([row["path"] for row in app.search("连接池")["hits"]], [other.name])

    def test_chinese_and_identifier_golden_cases(self):
        documents = {
            "design.md": "# 数据库连接池设计",
            "ops.md": "# 生产部署回滚步骤\n\nAPI接入指南",
            "archived.md": "---\nstate: archived\n---\n# 生产部署回滚旧说明",
            "punctuation.md": "# 部署。回滚",
            "identifier.md": "# ERR_TIMEOUT field",
            "decoy.md": "# ERR TIMEOUT fields",
        }
        cases = {
            "连接": {"design.md"},
            "连接池": {"design.md"},
            "部署回滚": {"ops.md"},
            "API接入": {"ops.md"},
            "API": {"ops.md"},
            "ERR_TIMEOUT": {"identifier.md"},
            "回。": {"ops.md", "punctuation.md"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            for name, text in documents.items():
                (root / name).write_text(text, encoding="utf-8")
            app = ApplicationService(root)
            for query, expected in cases.items():
                with self.subTest(query=query):
                    self.assertEqual({item["path"] for item in app.search(query)["hits"]}, expected)
            results = {item["path"]: item["state"] for item in app.search("部署回滚", include_inactive=True)["hits"]}
            self.assertEqual(results, {"ops.md": "active", "archived.md": "archived"})

    def test_old_fts_index_upgrades_even_when_markdown_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_vault(root)
            (root / "note.md").write_text("# 设计复核规则", encoding="utf-8")
            app = ApplicationService(root)
            app.index()
            with closing(sqlite3.connect(index_path(root))) as connection, connection:
                connection.execute("DROP TABLE blocks")
                connection.execute("CREATE VIRTUAL TABLE blocks USING fts5(path, block_id, content)")
                connection.execute("INSERT INTO blocks VALUES (?, ?, ?)", ("note.md", "note.md:0", "设计复核规则"))
            self.assertEqual(app.search("复核")["hits"][0]["path"], "note.md")
            self.assertEqual(app.index()["blocks"], 0)
