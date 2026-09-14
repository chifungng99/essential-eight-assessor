"""Tests for the scoring engine.

Run with:  python3 -m unittest discover -s tests -v

The loader and validator tests in test_control_set.py prove the control set
is well-formed. They say nothing about whether the *scoring rule* is right,
and a wrong scoring rule is the tool's most dangerous failure mode: it
produces a maturity level that looks completely plausible while being wrong.
So this file leans on the actual shipped control set (not a toy fixture) for
every case, because the "own complete set, not cumulative" rule only bites on
real superseded requirements, and a synthetic fixture could accidentally be
too simple to exercise it.
"""

import os
import random
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import model, scoring  # noqa: E402

CONTROLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "controls", "e8-2023-11.json",
)


def load_control_set():
    """The shipped control set, loaded through the real staleness check.

    Scoring tests care about the criteria, not the calendar, so `today` is
    pinned to `sourced_on` (freshly sourced, never stale) rather than
    turning off the check this module exists to enforce.
    """
    raw = model.validate(_read_raw())
    sourced = date.fromisoformat(raw["sourced_on"])
    return model.load(CONTROLS, today=sourced)


def _read_raw():
    import json

    with open(CONTROLS, encoding="utf-8") as fh:
        return json.load(fh)


def strategy(control_set, strategy_id):
    for s in control_set["strategies"]:
        if s["id"] == strategy_id:
            return s
    raise KeyError(strategy_id)


def met_answers(strategy):
    """Every criterion in `strategy` answered "met". The all-good baseline
    that each worked-example test then knocks one criterion out of."""
    return {c["id"]: scoring.MET for c in strategy["criteria"]}


class TestWorkedExamples(unittest.TestCase):
    """Hand-computed answer sets with a known correct result.

    Each one knocks out a single, specifically-chosen criterion from an
    otherwise all-met answer set, chosen for which levels it is (and is not)
    required at, so the expected result follows directly from the PRD's
    scoring rule rather than from re-implementing the scorer to check it.
    """

    def setUp(self):
        self.control_set = load_control_set()
        self.patch_apps = strategy(self.control_set, "patch-apps")

    def test_everything_met_reaches_level_three(self):
        for s in self.control_set["strategies"]:
            result = scoring.score_strategy(s, met_answers(s))
            self.assertEqual(result.level, 3, s["id"])
            for level in model.VALID_LEVELS:
                self.assertTrue(result.met(level), f"{s['id']} level {level}")

    def test_a_criterion_required_at_every_level_failing_gives_zero(self):
        # patch-apps-01 is required at [1, 2, 3]: failing it fails every level.
        answers = met_answers(self.patch_apps)
        answers["patch-apps-01"] = scoring.NOT_MET
        result = scoring.score_strategy(self.patch_apps, answers)
        self.assertEqual(result.level, 0)
        for level in model.VALID_LEVELS:
            self.assertFalse(result.met(level))

    def test_level_one_complete_but_a_level_two_criterion_failed_gives_one(self):
        # patch-apps-10 is required at [2, 3] only, so Level One never asks
        # for it and is still fully met even though this answer is not.
        answers = met_answers(self.patch_apps)
        answers["patch-apps-10"] = scoring.NOT_MET
        result = scoring.score_strategy(self.patch_apps, answers)
        self.assertEqual(result.level, 1)
        self.assertTrue(result.met(1))
        self.assertFalse(result.met(2))
        self.assertFalse(result.met(3))

    def test_levels_one_and_two_complete_but_a_level_three_criterion_failed_gives_two(self):
        # patch-apps-12 is required at [3] only.
        answers = met_answers(self.patch_apps)
        answers["patch-apps-12"] = scoring.NOT_MET
        result = scoring.score_strategy(self.patch_apps, answers)
        self.assertEqual(result.level, 2)
        self.assertTrue(result.met(1))
        self.assertTrue(result.met(2))
        self.assertFalse(result.met(3))

    def test_an_unanswered_criterion_is_not_met(self):
        # Same as the all-met set, but one id is simply missing rather than
        # explicitly answered, the "unanswered" half of PRD success
        # criterion 4, as distinct from "unknown".
        answers = met_answers(self.patch_apps)
        del answers["patch-apps-01"]
        result = scoring.score_strategy(self.patch_apps, answers)
        self.assertEqual(result.level, 0)

    def test_all_unknown_gives_zero(self):
        for s in self.control_set["strategies"]:
            answers = {c["id"]: scoring.UNKNOWN for c in s["criteria"]}
            result = scoring.score_strategy(s, answers)
            self.assertEqual(result.level, 0, s["id"])

    def test_empty_answer_set_gives_zero_for_every_strategy(self):
        for s in self.control_set["strategies"]:
            result = scoring.score_strategy(s, {})
            self.assertEqual(result.level, 0, s["id"])

    def test_score_returns_one_result_per_strategy_in_order(self):
        answers = {}
        for s in self.control_set["strategies"]:
            answers.update(met_answers(s))
        results = scoring.score(self.control_set, answers)
        self.assertEqual(
            [r.strategy_id for r in results],
            [s["id"] for s in self.control_set["strategies"]],
        )


class TestSupersededRequirementsAreNotCumulative(unittest.TestCase):
    """The concrete case the whole design turns on.

    patch-apps-07 is required at Levels One and Two, and NOT at Level Three,
    because Level Three replaced it with a stricter requirement. A strategy must be
    able to reach Level Three while that specific answer stays "not met",
    because Level Three's own complete set never asks for it. If a future
    change made scoring cumulative ("this level and everything below"), this
    is the test that would catch it.
    """

    def test_level_three_is_reachable_without_a_superseded_lower_level_requirement(self):
        control_set = load_control_set()
        patch_apps = strategy(control_set, "patch-apps")
        self.assertNotIn(3, next(
            c for c in patch_apps["criteria"] if c["id"] == "patch-apps-07"
        )["required_at_levels"], "test fixture assumption: patch-apps-07 is not required at Level 3")

        answers = met_answers(patch_apps)
        answers["patch-apps-07"] = scoring.NOT_MET

        result = scoring.score_strategy(patch_apps, answers)

        self.assertEqual(result.level, 3)
        self.assertTrue(result.met(3))
        # And the gap is still visible at the levels that do require it:
        # scoring hides nothing just because a higher level was awarded.
        self.assertFalse(result.met(1))
        self.assertFalse(result.met(2))
        unmet_ids_at_1 = {c.id for c in result.unmet_by_level[1]}
        self.assertIn("patch-apps-07", unmet_ids_at_1)


class TestMonotonicity(unittest.TestCase):
    """The strongest properties this engine has to hold.

    The original invariant was "changing an answer from met to not_met can never
    raise the level". That is no longer the whole story, because not_applicable
    removes a requirement rather than failing it, and so CAN raise a level
    without anything being implemented. That is its purpose, and it is exactly
    why e8/answers.py makes it the one answer that must be justified in writing
    and e8/report.py prints every one of them.

    So the property is restated as three, over the categories in e8/scoring.py:
    satisfying (met, alternate_control), failing (not_met, unknown) and
    excluding (not_applicable).

    A fixed seed keeps these deterministic. Property-based testing normally
    wants a fresh seed per run, but a hand-rolled version of that without a
    library (per the project's zero-dependency rule) would trade a reproducible
    CI failure for a flaky one, which is the wrong trade for a compliance tool.
    """

    def setUp(self):
        self.control_set = load_control_set()
        self.all_pairs = [
            (s, c) for s in self.control_set["strategies"] for c in s["criteria"]
        ]

    def _trials(self, seed, pick_from, new_value, assertion):
        rng = random.Random(seed)
        trials = 0
        for _ in range(300):
            answers = {c["id"]: rng.choice(scoring.VALID_ANSWERS) for _, c in self.all_pairs}
            candidates = [(s, c) for s, c in self.all_pairs
                          if answers[c["id"]] in pick_from]
            if not candidates:
                continue
            strategy, criterion = rng.choice(candidates)
            before = scoring.score_strategy(strategy, answers)
            answers[criterion["id"]] = new_value
            after = scoring.score_strategy(strategy, answers)
            trials += 1
            assertion(before, after, strategy, criterion)
        self.assertGreater(trials, 0, "no trial produced a candidate answer to flip")

    def test_satisfying_to_failing_never_raises_the_level(self):
        """Invariant 1. A scorer that could be pushed up by doing less would be
        worse than useless."""
        def check(before, after, strategy, criterion):
            self.assertLessEqual(
                after.level, before.level,
                f"flipping {criterion['id']!r} to not_met raised {strategy['id']!r} "
                f"from {before.level} to {after.level}",
            )
        self._trials(20260914, scoring.SATISFYING, scoring.NOT_MET, check)

    def test_satisfying_to_unknown_never_raises_the_level(self):
        """unknown is not a softer failure than not_met."""
        def check(before, after, strategy, criterion):
            self.assertLessEqual(after.level, before.level)
        self._trials(20260914, scoring.SATISFYING, scoring.UNKNOWN, check)

    def test_failing_to_not_applicable_never_lowers_the_level(self):
        """Invariant 2. Excluding a requirement removes it from the set, so it
        can only help or do nothing. This is the formal statement of why
        not_applicable has to be justified and disclosed."""
        def check(before, after, strategy, criterion):
            self.assertGreaterEqual(
                after.level, before.level,
                f"marking {criterion['id']!r} not applicable lowered "
                f"{strategy['id']!r} from {before.level} to {after.level}",
            )
        self._trials(20260914, (scoring.NOT_MET, scoring.UNKNOWN),
                     scoring.NOT_APPLICABLE, check)

    def test_met_and_alternate_control_are_scoring_equivalent(self):
        """Invariant 3. They differ in evidence, not in arithmetic. The
        difference is carried by the report, not the scorer."""
        def check(before, after, strategy, criterion):
            self.assertEqual(after.level, before.level)
        self._trials(20260914, (scoring.MET,), scoring.ALTERNATE_CONTROL, check)
        self._trials(20260914, (scoring.ALTERNATE_CONTROL,), scoring.MET, check)


class TestNotApplicable(unittest.TestCase):
    """not_applicable removes a requirement from the set rather than failing it."""

    def setUp(self):
        self.control_set = load_control_set()
        self.patch_os = strategy(self.control_set, "patch-os")

    def test_excluding_a_failing_requirement_can_award_the_level(self):
        answers = met_answers(self.patch_os)
        answers["patch-os-03"] = scoring.NOT_MET
        self.assertEqual(scoring.score_strategy(self.patch_os, answers).level, 0)

        answers["patch-os-03"] = scoring.NOT_APPLICABLE
        self.assertEqual(scoring.score_strategy(self.patch_os, answers).level, 3)

    def test_the_applicable_base_is_recorded(self):
        answers = met_answers(self.patch_os)
        answers["patch-os-03"] = scoring.NOT_APPLICABLE
        level_one = scoring.score_strategy(self.patch_os, answers).levels[1]
        self.assertEqual(level_one.required_count, 8)
        self.assertEqual(level_one.applicable_count, 7)
        self.assertEqual([c.id for c in level_one.not_applicable], ["patch-os-03"])

    def test_a_level_with_no_applicable_requirements_is_never_awarded(self):
        """"All of nothing is met" is vacuously true and would hand out a
        maturity level to an organisation that excluded the entire level."""
        answers = met_answers(self.patch_os)
        for c in model.criteria_for_level(self.patch_os, 1):
            answers[c["id"]] = scoring.NOT_APPLICABLE
        result = scoring.score_strategy(self.patch_os, answers)
        self.assertFalse(result.met(1))
        self.assertTrue(result.levels[1].unawardable)
        self.assertEqual(result.levels[1].applicable_count, 0)

    def test_three_applicable_requirements_still_award_the_level(self):
        """The reduced-base case: an organisation running entirely on managed
        mobile devices, with no workstations, servers or network devices of its
        own. Level One rests on 3 of its 8 requirements, which is a narrower
        claim than 8 of 8 and is why the base is reported everywhere."""
        answers = met_answers(self.patch_os)
        excluded = ["patch-os-03", "patch-os-04", "patch-os-05",
                    "patch-os-06", "patch-os-07"]
        for cid in excluded:
            answers[cid] = scoring.NOT_APPLICABLE

        result = scoring.score_strategy(self.patch_os, answers)
        level_one = result.levels[1]
        self.assertEqual(level_one.applicable_count, 3)
        self.assertEqual(level_one.required_count, 8)
        self.assertTrue(result.met(1))
        self.assertEqual(sorted(c.id for c in level_one.not_applicable), sorted(excluded))


class TestAlternateControl(unittest.TestCase):
    def setUp(self):
        self.control_set = load_control_set()
        self.patch_apps = strategy(self.control_set, "patch-apps")

    def test_satisfies_a_requirement_exactly_as_met_does(self):
        answers = met_answers(self.patch_apps)
        answers["patch-apps-02"] = scoring.ALTERNATE_CONTROL
        self.assertEqual(scoring.score_strategy(self.patch_apps, answers).level, 3)

    def test_does_not_remove_the_requirement_from_the_set(self):
        """Unlike not_applicable, it satisfies the requirement rather than
        excluding it, so the applicable base is unchanged."""
        answers = met_answers(self.patch_apps)
        answers["patch-apps-02"] = scoring.ALTERNATE_CONTROL
        level_one = scoring.score_strategy(self.patch_apps, answers).levels[1]
        self.assertEqual(level_one.applicable_count, level_one.required_count)
        self.assertEqual(level_one.not_applicable, [])


class TestSmallBusinessRegression(unittest.TestCase):
    """The defect this stage exists to fix.

    A small business with no internet-facing servers and no online customer
    services, doing everything it possibly can, scored Three, Zero, Zero because
    it was failed on servers it does not own. With the nine inapplicable
    requirements excluded it scores Three, Three, Three.
    """

    NOT_APPLICABLE_IDS = ["patch-os-03", "patch-os-05", "patch-os-06",
                          "mfa-04", "mfa-05", "mfa-06", "mfa-11", "mfa-15", "mfa-21"]

    def setUp(self):
        self.control_set = load_control_set()
        self.answers = {}
        for s in self.control_set["strategies"]:
            self.answers.update(met_answers(s))

    def test_without_not_applicable_the_tool_under_rates(self):
        """Preserved deliberately. If this ever stops holding, the old defect
        has come back by another route."""
        answers = dict(self.answers)
        for cid in self.NOT_APPLICABLE_IDS:
            answers[cid] = scoring.NOT_MET
        levels = {r.strategy_id: r.level
                  for r in scoring.score(self.control_set, answers)}
        self.assertEqual(levels, {"patch-apps": 3, "patch-os": 0, "mfa": 0})

    def test_with_not_applicable_the_rating_is_correct(self):
        answers = dict(self.answers)
        for cid in self.NOT_APPLICABLE_IDS:
            answers[cid] = scoring.NOT_APPLICABLE
        levels = {r.strategy_id: r.level
                  for r in scoring.score(self.control_set, answers)}
        self.assertEqual(levels, {"patch-apps": 3, "patch-os": 3, "mfa": 3})


if __name__ == "__main__":
    unittest.main()
