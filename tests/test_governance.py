import tempfile
import unittest
from pathlib import Path

from kbkit.application import ApplicationService
from kbkit.graph import build_graph, outline
from kbkit.lint import lint


class GovernanceTests(unittest.TestCase):
    def test_graph_resolves_and_reports_broken_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.md").write_text("[[b]] [[missing]]", encoding="utf-8")
            (root / "b.md").write_text("target", encoding="utf-8")
            graph = build_graph(root)
            self.assertEqual(len(graph["edges"]), 2)
            self.assertEqual(len(graph["broken"]), 1)
            self.assertIn("a.md", graph["orphaned"])

    def test_outline_reports_heading_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("# One\n## Two\n", encoding="utf-8")
            self.assertEqual(outline(root, "note.md")[1]["level"], 2)

    def test_lint_reports_empty_and_missing_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty.md").write_text("", encoding="utf-8")
            findings = lint(root)
            self.assertTrue(any(item["rule"] == "LINT-L11" for item in findings))
            self.assertTrue(any(item["rule"] == "LINT-L04" for item in findings))

    def test_application_service_exposes_governance(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ApplicationService(Path(directory))
            service.initialize()
            self.assertIn("findings", service.lint())
            self.assertIn("edges", service.graph())
