"""Tests for answers file loading and validation.

Run with:  python3 -m unittest discover -s tests -v

The answers file is the only untrusted input this tool takes. Everything here
is a way an assessment could end up scored against something other than what
the person filling it in believed they were answering.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import answers, model, scoring  # noqa: E402

CONTROLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "controls", "e8-2023-11.json",
)


def load_control_set():
    with open(CONTROLS, encoding="utf-8") as fh:
        raw = json.load(fh)
    return model.load(CONTROLS, today=date.fromisoformat(raw["sourced_on"]))


class TestFingerprint(unittest.TestCase):
    """The fingerprint exists to catch a control set that changed without its
    version string changing, which is exactly what will happen when Jackson's
    review of the extracted criteria produces a correction."""

    def setUp(self):
        self.control_set = load_control_set()

    def test_is_stable_for_the_same_control_set(self):
        self.assertEqual(
            answers.fingerprint(self.control_set),
            answers.fingerprint(copy.deepcopy(self.control_set)),
        )

    def test_changes_when_a_criterion_text_changes(self):
        before = answers.fingerprint(self.control_set)
        other = copy.deepcopy(self.control_set)
        other["strategies"][0]["criteria"][0]["sha256"] = "000000000000"
        self.assertNotEqual(before, answers.fingerprint(other))

    def test_changes_when_a_criterion_is_retagged_to_different_levels(self):
        """The case a file hash of the criteria texts would miss entirely.

        Re-tagging a requirement from [1, 2] to [1, 2, 3] changes what Level
        Three demands while leaving every text digest identical.
        """
        before = answers.fingerprint(self.control_set)
        other = copy.deepcopy(self.control_set)
        criterion = next(
            c for c in other["strategies"][0]["criteria"]
            if c["required_at_levels"] != [1, 2, 3]
        )
        criterion["required_at_levels"] = [1, 2, 3]
        self.assertNotEqual(before, answers.fingerprint(other))


class TestTemplate(unittest.TestCase):
    def setUp(self):
        self.control_set = load_control_set()

    def test_covers_every_criterion_and_validates(self):
        document = answers.template(self.control_set, organisation="Example Pty Ltd")
        answers.validate(document, self.control_set)
        expected = sum(len(s["criteria"]) for s in self.control_set["strategies"])
        self.assertEqual(len(document["answers"]), expected)

    def test_starts_unknown_rather_than_not_met(self):
        """A blank assessment has not been done. Starting it out asserting every
        control has failed is as dishonest as starting it out asserting they pass."""
        document = answers.template(self.control_set)
        self.assertEqual(set(document["answers"].values()), {scoring.UNKNOWN})

    def test_a_blank_template_scores_zero_everywhere(self):
        document = answers.template(self.control_set)
        for result in scoring.score(self.control_set, document["answers"]):
            self.assertEqual(result.level, 0, result.strategy_id)

    def test_carries_the_fingerprint_of_the_set_it_was_built_from(self):
        document = answers.template(self.control_set)
        self.assertEqual(
            document["control_set_fingerprint"], answers.fingerprint(self.control_set)
        )


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.control_set = load_control_set()
        self.document = answers.template(self.control_set, organisation="Example Pty Ltd")

    def test_accepts_a_good_document(self):
        answers.validate(self.document, self.control_set)

    def test_rejects_a_missing_required_field(self):
        del self.document["answered_on"]
        with self.assertRaisesRegex(answers.AnswersError, "missing required fields"):
            answers.validate(self.document, self.control_set)

    def test_rejects_a_control_set_version_mismatch(self):
        self.document["control_set_version"] = "November 2019"
        with self.assertRaisesRegex(answers.AnswersError, "November 2019"):
            answers.validate(self.document, self.control_set)

    def test_rejects_a_fingerprint_mismatch_even_when_the_version_matches(self):
        """The drift the version string cannot see."""
        self.document["control_set_fingerprint"] = "deadbeefcafe"
        with self.assertRaisesRegex(answers.AnswersError, "criteria themselves have changed"):
            answers.validate(self.document, self.control_set)

    def test_accepts_a_document_with_no_fingerprint(self):
        """The PRD's schema does not include one, so a hand-written file that
        omits it is valid. It just gets less protection."""
        del self.document["control_set_fingerprint"]
        answers.validate(self.document, self.control_set)

    def test_rejects_a_bad_answered_on(self):
        self.document["answered_on"] = "12 September 2026"
        with self.assertRaisesRegex(answers.AnswersError, "ISO date"):
            answers.validate(self.document, self.control_set)

    def test_rejects_an_unrecognised_criterion_id(self):
        self.document["answers"]["patch-apps-99"] = scoring.MET
        with self.assertRaisesRegex(answers.AnswersError, "not in this control set"):
            answers.validate(self.document, self.control_set)

    def test_rejects_an_invalid_answer_value(self):
        """Rejected rather than counted as not met. A user who typed "Met" and
        scored Zero could not otherwise tell a strict tool from a broken one."""
        self.document["answers"]["patch-apps-01"] = "Met"
        with self.assertRaisesRegex(answers.AnswersError, "must be one of"):
            answers.validate(self.document, self.control_set)

    def test_rejects_a_boolean_answer(self):
        self.document["answers"]["patch-apps-01"] = True
        with self.assertRaises(answers.AnswersError):
            answers.validate(self.document, self.control_set)

    def test_rejects_answers_that_are_not_an_object(self):
        self.document["answers"] = ["patch-apps-01"]
        with self.assertRaisesRegex(answers.AnswersError, "criterion id"):
            answers.validate(self.document, self.control_set)


class TestUnanswered(unittest.TestCase):
    """An unanswered criterion is not an error. It scores as not met and is
    reported, because forcing a user to type "unknown" 55 times to get a result
    they could have had anyway teaches them to fill the file in mechanically."""

    def setUp(self):
        self.control_set = load_control_set()
        self.document = answers.template(self.control_set)

    def test_a_complete_document_has_none(self):
        self.assertEqual(answers.unanswered(self.document, self.control_set), [])

    def test_names_the_missing_ids(self):
        del self.document["answers"]["patch-apps-01"]
        del self.document["answers"]["mfa-01"]
        self.assertEqual(
            answers.unanswered(self.document, self.control_set),
            ["patch-apps-01", "mfa-01"],
        )

    def test_a_document_missing_criteria_still_validates(self):
        del self.document["answers"]["patch-apps-01"]
        answers.validate(self.document, self.control_set)


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.control_set = load_control_set()

    def test_round_trips_a_template(self):
        document = answers.template(self.control_set, organisation="Example Pty Ltd")
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(document, fh)
        fh.close()
        try:
            self.assertEqual(answers.load(fh.name, self.control_set), document)
        finally:
            os.unlink(fh.name)

    def test_missing_file(self):
        with self.assertRaisesRegex(answers.AnswersError, "not found"):
            answers.load("/nonexistent/answers.json", self.control_set)

    def test_not_json(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        fh.write("{ not json")
        fh.close()
        try:
            with self.assertRaisesRegex(answers.AnswersError, "not valid JSON"):
                answers.load(fh.name, self.control_set)
        finally:
            os.unlink(fh.name)


class TestJustifications(unittest.TestCase):
    """not_applicable and alternate_control are the two answers that change a
    rating without anything being implemented, so each one has to say why."""

    def setUp(self):
        self.control_set = load_control_set()
        self.document = answers.template(self.control_set, organisation="Example Pty Ltd")

    def test_not_applicable_without_a_justification_is_refused(self):
        self.document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        with self.assertRaisesRegex(answers.AnswersError, "without a written justification"):
            answers.validate(self.document, self.control_set)

    def test_alternate_control_without_a_justification_is_refused(self):
        self.document["answers"]["patch-apps-02"] = scoring.ALTERNATE_CONTROL
        with self.assertRaisesRegex(answers.AnswersError, "without a written justification"):
            answers.validate(self.document, self.control_set)

    def test_a_non_string_justification_is_refused(self):
        """A justification has to be written text.

        `str(None).strip()` is "None", which is non-empty, so a null would
        otherwise satisfy a rule whose whole point is that an exclusion says why
        in words. Same for a number, a boolean or a list.
        """
        for value in (None, 123, 0, True, False, [], ["a reason"], {}, {"a": 1}, 1.5):
            with self.subTest(justification=repr(value)):
                document = answers.template(self.control_set, organisation="Example")
                document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
                document["justifications"]["patch-os-03"] = value
                with self.assertRaises(answers.AnswersError):
                    answers.validate(document, self.control_set)

    def test_a_non_string_justification_is_refused_for_alternate_control_too(self):
        for value in (None, 123, True, [], {}):
            with self.subTest(justification=repr(value)):
                document = answers.template(self.control_set, organisation="Example")
                document["answers"]["patch-apps-02"] = scoring.ALTERNATE_CONTROL
                document["justifications"]["patch-apps-02"] = value
                with self.assertRaises(answers.AnswersError):
                    answers.validate(document, self.control_set)

    def test_the_refusal_says_what_a_justification_has_to_be(self):
        self.document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        self.document["justifications"]["patch-os-03"] = None
        with self.assertRaisesRegex(answers.AnswersError, "null, a number, a boolean"):
            answers.validate(self.document, self.control_set)

    def test_a_short_justification_is_still_accepted(self):
        """There is deliberately no minimum length. The control is that every
        justification is printed verbatim where a reader can judge it."""
        self.document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        self.document["justifications"]["patch-os-03"] = "None here."
        answers.validate(self.document, self.control_set)

    def test_a_whitespace_only_justification_is_refused(self):
        self.document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        self.document["justifications"]["patch-os-03"] = "   "
        with self.assertRaisesRegex(answers.AnswersError, "without a written justification"):
            answers.validate(self.document, self.control_set)

    def test_a_justified_exclusion_is_accepted(self):
        self.document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        self.document["justifications"]["patch-os-03"] = "No internet-facing servers."
        answers.validate(self.document, self.control_set)

    def test_a_justification_on_an_answer_that_does_not_take_one_is_refused(self):
        """Either the answer was changed and the reason left behind, or the
        reason was written against the wrong criterion."""
        self.document["justifications"]["patch-apps-01"] = "Left over from an edit."
        with self.assertRaisesRegex(answers.AnswersError, "does not take one"):
            answers.validate(self.document, self.control_set)

    def test_unknown_needs_no_justification(self):
        """Making the honest answer expensive is how a tool fills up with guesses."""
        self.document["answers"]["patch-apps-01"] = scoring.UNKNOWN
        answers.validate(self.document, self.control_set)

    def test_justifications_must_be_an_object(self):
        self.document["justifications"] = ["nope"]
        with self.assertRaisesRegex(answers.AnswersError, "criterion id"):
            answers.validate(self.document, self.control_set)

    def test_the_helper_returns_the_stated_reason(self):
        self.document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        self.document["justifications"]["patch-os-03"] = "  No internet-facing servers. "
        self.assertEqual(answers.justification(self.document, "patch-os-03"),
                         "No internet-facing servers.")


class TestWholeStrategyExclusion(unittest.TestCase):
    """ASD is explicit that an entire mitigation strategy cannot be scoped out."""

    def setUp(self):
        self.control_set = load_control_set()
        self.document = answers.template(self.control_set, organisation="Example Pty Ltd")

    def test_refused_when_every_criterion_in_a_strategy_is_not_applicable(self):
        strategy = next(s for s in self.control_set["strategies"] if s["id"] == "mfa")
        for c in strategy["criteria"]:
            self.document["answers"][c["id"]] = scoring.NOT_APPLICABLE
            self.document["justifications"][c["id"]] = "We do not use authentication."
        with self.assertRaisesRegex(answers.AnswersError, "entire mitigation strategy"):
            answers.validate(self.document, self.control_set)

    def test_the_refusal_names_the_strategy(self):
        strategy = next(s for s in self.control_set["strategies"] if s["id"] == "mfa")
        for c in strategy["criteria"]:
            self.document["answers"][c["id"]] = scoring.NOT_APPLICABLE
            self.document["justifications"][c["id"]] = "We do not use authentication."
        with self.assertRaisesRegex(answers.AnswersError, "Multi-factor authentication"):
            answers.validate(self.document, self.control_set)

    def test_excluding_all_but_one_criterion_is_allowed(self):
        """The refusal is about scoping out a whole strategy, not about being
        strict on how much may be excluded. A thin base is disclosed, not refused."""
        strategy = next(s for s in self.control_set["strategies"] if s["id"] == "mfa")
        for c in strategy["criteria"][1:]:
            self.document["answers"][c["id"]] = scoring.NOT_APPLICABLE
            self.document["justifications"][c["id"]] = "Not present in this environment."
        answers.validate(self.document, self.control_set)


class TestBackwardsCompatibility(unittest.TestCase):
    """An answers file written before this change must still work, unchanged."""

    def setUp(self):
        self.control_set = load_control_set()

    def _legacy_document(self):
        """Exactly the old schema: three values, no justifications block."""
        return {
            "control_set_version": self.control_set["version"],
            "control_set_fingerprint": answers.fingerprint(self.control_set),
            "organisation": "Legacy Pty Ltd",
            "answered_on": "2026-09-12",
            "answers": {
                c["id"]: scoring.MET
                for s in self.control_set["strategies"] for c in s["criteria"]
            },
        }

    def test_a_legacy_document_still_validates(self):
        answers.validate(self._legacy_document(), self.control_set)

    def test_a_legacy_document_scores_identically(self):
        document = self._legacy_document()
        levels = {r.strategy_id: r.level
                  for r in scoring.score(self.control_set, document["answers"])}
        self.assertEqual(levels, {"patch-apps": 3, "patch-os": 3, "mfa": 3})

    def test_a_legacy_document_with_unknowns_scores_identically(self):
        document = self._legacy_document()
        document["answers"]["patch-apps-01"] = scoring.UNKNOWN
        document["answers"]["mfa-01"] = scoring.NOT_MET
        levels = {r.strategy_id: r.level
                  for r in scoring.score(self.control_set, document["answers"])}
        self.assertEqual(levels, {"patch-apps": 0, "patch-os": 3, "mfa": 0})

    def test_the_control_set_fingerprint_is_unchanged_by_this_stage(self):
        """Pinned. The control set was not touched, so answers collected before
        this change still match the set they were given against."""
        self.assertEqual(answers.fingerprint(self.control_set), "47b94cd63a01")


if __name__ == "__main__":
    unittest.main()
