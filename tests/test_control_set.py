"""Tests for the loader, the validator and the shipped control set.

Run with:  python3 -m unittest discover -s tests -v

Standard library only. A reviewer should be able to clone this repository and run
the tests without installing anything, and a compliance tool whose own test suite
needs a package index is a tool people will not verify.
"""

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import model  # noqa: E402

CONTROLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "controls", "e8-2023-11.json",
)


def load_raw():
    with open(CONTROLS, encoding="utf-8") as fh:
        return json.load(fh)


def write_temp(data):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, fh)
    fh.close()
    return fh.name


def resha(criterion):
    """Recompute a criterion's digest, for tests that legitimately change its text."""
    criterion["sha256"] = hashlib.sha256(criterion["text"].encode("utf-8")).hexdigest()[:12]
    return criterion


class TestShippedControlSet(unittest.TestCase):
    """The control set that actually ships must be valid on its own terms."""

    def setUp(self):
        self.data = load_raw()

    def test_validates(self):
        model.validate(self.data)

    def test_loads_with_a_date_inside_its_own_window(self):
        sourced = date.fromisoformat(self.data["sourced_on"])
        model.load(CONTROLS, today=sourced)

    def test_declares_its_licence_and_attribution(self):
        licence = self.data["licence"]
        self.assertEqual(licence["name"], "CC BY 4.0")
        self.assertIn("Commonwealth of Australia", licence["attribution"])
        self.assertIn("Coat of Arms", licence["attribution"])

    def test_covers_the_three_in_scope_strategies(self):
        ids = {s["id"] for s in self.data["strategies"]}
        self.assertEqual(ids, {"patch-apps", "patch-os", "mfa"})

    def test_every_criterion_matches_its_recorded_digest(self):
        for strategy in self.data["strategies"]:
            for criterion in strategy["criteria"]:
                expected = hashlib.sha256(criterion["text"].encode("utf-8")).hexdigest()[:12]
                self.assertEqual(criterion["sha256"], expected, criterion["id"])

    def test_criterion_counts_match_the_published_model(self):
        """Corroborated by a second, independent parse of the source PDF.

        These numbers are NOT copied from the extractor's output. A test that
        asserts whatever the code produced would pass just as happily if the
        extractor were wrong. They come from a separate crude sentence-splitting
        pass over the same document, written before the extractor existed, which
        arrived at the same counts.

        Two independent methods agreeing is corroboration, not proof. Only a human
        reading Appendices A to C confirms these are right, which is the review gate
        in docs/PRD.md stage 1.
        """
        expected = {
            "patch-apps": {1: 9, 2: 11, 3: 13},
            "patch-os": {1: 8, 2: 8, 3: 16},
            "mfa": {1: 7, 2: 19, 3: 23},
        }
        for strategy in self.data["strategies"]:
            for level, count in expected[strategy["id"]].items():
                self.assertEqual(
                    len(model.criteria_for_level(strategy, level)), count,
                    f"{strategy['id']} at Maturity Level {level}",
                )

    def test_some_criteria_are_superseded_rather_than_carried_forward(self):
        """The structural fact the scoring rule depends on.

        If every criterion applied at every level at or above its first appearance,
        'this level and all below' would be a harmless way to score. It is not:
        three requirements in this control set are required at lower levels and NOT
        at Maturity Level Three, because Level Three replaces them with stricter
        ones. If this test ever fails, re-read the model before touching the scorer.
        """
        superseded = [
            c["id"]
            for s in self.data["strategies"]
            for c in s["criteria"]
            if 3 not in c["required_at_levels"]
        ]
        self.assertTrue(superseded, "expected at least one superseded requirement")


class TestValidation(unittest.TestCase):
    """Each of these is a way a control set can be quietly wrong."""

    def setUp(self):
        self.data = load_raw()

    def test_rejects_missing_top_level_field(self):
        del self.data["max_age_days"]
        with self.assertRaises(model.ControlSetError):
            model.validate(self.data)

    def test_rejects_duplicate_criterion_id(self):
        s = self.data["strategies"][0]
        clone = copy.deepcopy(s["criteria"][0])
        s["criteria"].append(clone)
        with self.assertRaisesRegex(model.ControlSetError, "duplicate criterion id"):
            model.validate(self.data)

    def test_rejects_criterion_required_at_no_level(self):
        self.data["strategies"][0]["criteria"][0]["required_at_levels"] = []
        with self.assertRaisesRegex(model.ControlSetError, "required at no maturity level"):
            model.validate(self.data)

    def test_rejects_invalid_level(self):
        self.data["strategies"][0]["criteria"][0]["required_at_levels"] = [1, 4]
        with self.assertRaisesRegex(model.ControlSetError, "invalid levels"):
            model.validate(self.data)

    def test_rejects_unsorted_levels(self):
        self.data["strategies"][0]["criteria"][0]["required_at_levels"] = [3, 1]
        with self.assertRaisesRegex(model.ControlSetError, "sorted and unique"):
            model.validate(self.data)

    def test_rejects_text_edited_without_updating_the_digest(self):
        """Hand-editing a requirement is the single most dangerous change possible."""
        self.data["strategies"][0]["criteria"][0]["text"] = "Patch things when convenient."
        with self.assertRaisesRegex(model.ControlSetError, "does not match its recorded sha256"):
            model.validate(self.data)

    def test_accepts_edited_text_when_the_digest_is_recomputed(self):
        """The digest detects drift; it is not a lock. Regeneration is the sanctioned path."""
        c = self.data["strategies"][0]["criteria"][0]
        c["text"] = "Patch things when convenient."
        resha(c)
        model.validate(self.data)

    def test_rejects_empty_text(self):
        c = self.data["strategies"][0]["criteria"][0]
        c["text"] = "   "
        resha(c)
        with self.assertRaisesRegex(model.ControlSetError, "empty text"):
            model.validate(self.data)

    def test_rejects_a_strategy_with_no_criteria_at_some_level(self):
        """An empty level would be awarded for free."""
        for c in self.data["strategies"][0]["criteria"]:
            c["required_at_levels"] = [lv for lv in c["required_at_levels"] if lv != 2] or [1]
        with self.assertRaisesRegex(model.ControlSetError, "no criteria at Maturity Level 2"):
            model.validate(self.data)

    def test_rejects_bad_sourced_on(self):
        self.data["sourced_on"] = "November 2023"
        with self.assertRaisesRegex(model.ControlSetError, "ISO date"):
            model.validate(self.data)


class TestStaleness(unittest.TestCase):
    """The refusal that gives the tool its integrity."""

    def setUp(self):
        self.data = load_raw()
        self.data["sourced_on"] = "2026-01-01"
        self.data["max_age_days"] = 180
        self.path = write_temp(self.data)

    def tearDown(self):
        os.unlink(self.path)

    def test_loads_inside_the_window(self):
        model.load(self.path, today=date(2026, 6, 1))

    def test_boundary_day_is_still_fresh(self):
        """Exactly max_age_days old is inside the window, not outside it."""
        self.assertEqual(model.age_days(self.data, date(2026, 6, 30)), 180)
        model.load(self.path, today=date(2026, 6, 30))

    def test_one_day_past_the_boundary_refuses(self):
        with self.assertRaises(model.StaleControlSetError):
            model.load(self.path, today=date(2026, 7, 1))

    def test_refusal_says_what_to_do_about_it(self):
        with self.assertRaises(model.StaleControlSetError) as ctx:
            model.load(self.path, today=date(2027, 1, 1))
        message = str(ctx.exception)
        self.assertIn("Refusing to produce a maturity rating", message)
        self.assertIn("extract_controls.py", message)

    def test_allow_stale_is_opt_in_and_works(self):
        data = model.load(self.path, today=date(2027, 1, 1), allow_stale=True)
        self.assertTrue(model.is_stale(data, date(2027, 1, 1)))

    def test_a_stale_set_is_still_validated(self):
        """Staleness must not become a way to smuggle in a malformed control set."""
        broken = copy.deepcopy(self.data)
        del broken["strategies"]
        path = write_temp(broken)
        try:
            with self.assertRaises(model.ControlSetError):
                model.load(path, today=date(2027, 1, 1), allow_stale=True)
        finally:
            os.unlink(path)


class TestCriteriaForLevel(unittest.TestCase):
    def setUp(self):
        self.strategy = load_raw()["strategies"][0]

    def test_rejects_a_level_outside_one_to_three(self):
        for bad in (0, 4, "1", None):
            with self.assertRaises(ValueError):
                model.criteria_for_level(self.strategy, bad)

    def test_returns_only_criteria_tagged_with_that_level(self):
        for level in (1, 2, 3):
            for c in model.criteria_for_level(self.strategy, level):
                self.assertIn(level, c["required_at_levels"])

    def test_does_not_include_superseded_lower_level_criteria(self):
        """The concrete case behind the scoring rule."""
        superseded = [c for c in self.strategy["criteria"] if 3 not in c["required_at_levels"]]
        if not superseded:
            self.skipTest("no superseded criteria in this strategy")
        at_three = {c["id"] for c in model.criteria_for_level(self.strategy, 3)}
        for c in superseded:
            self.assertNotIn(c["id"], at_three)


class TestLoadFailures(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaisesRegex(model.ControlSetError, "not found"):
            model.load("/nonexistent/controls.json")

    def test_not_json(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        fh.write("{ not json")
        fh.close()
        try:
            with self.assertRaisesRegex(model.ControlSetError, "not valid JSON"):
                model.load(fh.name)
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
