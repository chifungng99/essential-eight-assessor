"""Pure scoring functions: an answer set plus a loaded control set -> results.

This module implements ASD's evaluation rule and nothing about the Essential
Eight itself. A maturity level is awarded only when every APPLICABLE criterion
in its own complete requirement set is satisfied. Two words there carry the
whole design:

**Own.** The requirement set for a level is exactly the criteria tagged with
that level (`model.criteria_for_level`), never that level plus everything
below, which would resurrect requirements a higher level has deliberately
superseded.

**Applicable.** A criterion answered "not_applicable" is removed from the set
rather than failed. ASD's assessment process guide lists "Not applicable: the
control does not apply to the system or environment" as a standard assessment
outcome, and without it an organisation with no internet-facing servers is
scored as failing to patch servers it does not own. That produced Maturity
Level Zero for organisations whose real answer was Three.

The five outcomes fall into three groups:

    satisfied   met, alternate_control
    failed      not_met, unknown, and any criterion left unanswered
    excluded    not_applicable

`alternate_control` scores exactly as `met` does, because ASD treats meeting a
control's objective by other means as effective. It is NOT equivalent evidence,
and `e8/report.py` says so wherever it appears: it is a self-declaration that
no assessor has verified.

Nothing here ever infers, estimates, or fills a gap on the user's behalf. A
criterion that is not explicitly satisfied is failed, and the only value that
can remove a requirement is one the answers file had to justify in writing.
"""

from dataclasses import dataclass
from typing import Dict, List

from e8 import model

MET = "met"
ALTERNATE_CONTROL = "alternate_control"
NOT_MET = "not_met"
NOT_APPLICABLE = "not_applicable"
UNKNOWN = "unknown"

VALID_ANSWERS = (MET, ALTERNATE_CONTROL, NOT_MET, NOT_APPLICABLE, UNKNOWN)

#: Values that satisfy a requirement.
SATISFYING = (MET, ALTERNATE_CONTROL)
#: Values that remove a requirement from the set rather than failing it.
EXCLUDING = (NOT_APPLICABLE,)
#: Values whose use has to be justified in writing. See e8/answers.py.
REQUIRES_JUSTIFICATION = (NOT_APPLICABLE, ALTERNATE_CONTROL)


@dataclass(frozen=True)
class Criterion:
    """A criterion as it appears in a report: just enough to show a human what
    is missing or excluded, without dragging the control-set schema along."""

    id: str
    text: str


@dataclass(frozen=True)
class LevelAssessment:
    """One maturity level, assessed for one strategy.

    `required` is every criterion the published model tags with this level.
    `not_applicable` is the subset the organisation declared it does not have.
    `applicable_count` is what the rating was actually computed from, and it is
    reported everywhere precisely because a level awarded on a reduced base is
    weaker evidence than one awarded on the full set.
    """

    level: int
    required_count: int
    applicable_count: int
    not_applicable: List[Criterion]
    unmet: List[Criterion]

    @property
    def satisfied(self):
        """Whether this level's applicable requirement set was fully met.

        An empty applicable set is NOT satisfied. "All of nothing is met" is
        vacuously true and would hand out a maturity level to an organisation
        that declared the entire level inapplicable, which is the one way
        not_applicable could be turned into a free pass.
        """
        return self.applicable_count > 0 and not self.unmet

    @property
    def unawardable(self):
        """True when nothing at this level was applicable, so nothing was shown."""
        return self.applicable_count == 0


@dataclass(frozen=True)
class StrategyResult:
    """The outcome for one mitigation strategy against one answer set.

    `level` is 0-3: the highest maturity level whose applicable requirement set
    was fully satisfied, or 0 if none was.
    """

    strategy_id: str
    strategy_name: str
    level: int
    levels: Dict[int, LevelAssessment]

    def met(self, level):
        """Whether `level`'s applicable requirement set was fully satisfied."""
        return self.levels[level].satisfied

    @property
    def unmet_by_level(self):
        """Unmet criteria keyed by level. Kept as the report's existing accessor."""
        return {lv: assessment.unmet for lv, assessment in self.levels.items()}


def is_satisfied(answers, criterion_id):
    """True only if the criterion was answered "met" or "alternate_control".

    Everything else is not satisfied: "not_met", "unknown", an unrecognised
    value, or the id being absent because the question was never answered.
    There is deliberately no path here that reads a missing answer as a pass.
    """
    return answers.get(criterion_id) in SATISFYING


def is_not_applicable(answers, criterion_id):
    return answers.get(criterion_id) in EXCLUDING


def assess_level(strategy, level, answers):
    """Assess one maturity level of one strategy."""
    required = model.criteria_for_level(strategy, level)
    not_applicable, applicable = [], []
    for c in required:
        (not_applicable if is_not_applicable(answers, c["id"]) else applicable).append(c)

    return LevelAssessment(
        level=level,
        required_count=len(required),
        applicable_count=len(applicable),
        not_applicable=[Criterion(c["id"], c["text"]) for c in not_applicable],
        unmet=[Criterion(c["id"], c["text"]) for c in applicable
               if not is_satisfied(answers, c["id"])],
    )


def score_strategy(strategy, answers):
    """Score one strategy against one answer set.

    Each level is assessed independently against its own applicable set, and
    the awarded level is the highest one satisfied. This is deliberately not a
    running "and everything below" check. See the module docstring.
    """
    levels = {lv: assess_level(strategy, lv, answers) for lv in model.VALID_LEVELS}
    achieved = [lv for lv in model.VALID_LEVELS if levels[lv].satisfied]
    return StrategyResult(
        strategy_id=strategy["id"],
        strategy_name=strategy["name"],
        level=max(achieved) if achieved else 0,
        levels=levels,
    )


def score(control_set, answers):
    """Score every strategy in a validated control set.

    Returns one `StrategyResult` per strategy, in the control set's own order.
    `control_set` is expected to have passed `model.validate` already, and
    `answers` to have passed `answers.validate`. This function re-checks
    neither: it is the arithmetic, not the gate.
    """
    return [score_strategy(strategy, answers) for strategy in control_set["strategies"]]
