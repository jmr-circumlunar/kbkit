import unittest

from kbkit.lifecycle import validate_state, validate_transition
from kbkit.frontmatter import validate_frontmatter


class LifecycleTests(unittest.TestCase):
    def test_allowed_and_rejected_transitions(self):
        self.assertTrue(validate_transition("draft", "active"))
        self.assertFalse(validate_transition("archived", "active"))
        self.assertTrue(validate_state("review_due"))
        self.assertFalse(validate_state("unknown"))

    def test_frontmatter_fields_and_values_are_validated(self):
        raw = b"---\nstate: strange\nvisibility: secret\nunknown: value\n---\nbody"
        rules = {finding["rule"] for finding in validate_frontmatter(raw)}
        self.assertEqual(rules, {"FM-STATE", "FM-VISIBILITY", "FM-UNKNOWN"})

    def test_confidence_and_review_date_rules(self):
        raw = b"---\nconfidence: 2\nreview_by: 2020-01-01\n---\nbody"
        rules = {finding["rule"] for finding in validate_frontmatter(raw)}
        self.assertEqual(rules, {"FM-CONFIDENCE", "LIFE-003"})

    def test_source_owner_and_tags_rules(self):
        raw = b"---\nsource:\nowner:\ntags: [unknown]\n---\nbody"
        rules = {finding["rule"] for finding in validate_frontmatter(raw)}
        self.assertIn("FM-SOURCE", rules)
        self.assertIn("FM-OWNER", rules)
        self.assertIn("FM-TAG", rules)
