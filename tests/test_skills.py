import tempfile
import unittest
from pathlib import Path

from kbkit.skills import list_skills


class SkillTests(unittest.TestCase):
    def test_skill_resources_are_discoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kb-query").mkdir()
            (root / "kb-query" / "SKILL.md").write_text("---\nname: kb-query\n---\n", encoding="utf-8")
            skills = list_skills(root)
            self.assertEqual(skills[0]["name"], "kb-query")
            self.assertIn("name: kb-query", skills[0]["content"])

    def test_builtin_skills_include_file_ingestion(self):
        names = {item["name"] for item in list_skills(Path(__file__).parents[1] / "skills")}
        self.assertIn("kb-ingest", names)
