"""Load and validate a completed assessment, and generate a blank one.

An answers file is untrusted input. It is hand-edited JSON, and every field in
it is a way for an assessment to end up scored against something other than
what the person filling it in believed they were answering. So this module is
strict in exactly the places `e8/scoring.py` is permissive, and the asymmetry
is deliberate:

`scoring.is_met` treats anything that is not exactly "met" as not met, so no
malformed answer can ever inflate a rating. This module refuses that same
malformed answer outright, so it cannot quietly deflate one either. Someone
who typed "Met" and scored Maturity Level Zero would otherwise have no way to
tell a strict tool from a broken one.

Two refusals here matter more than the rest:

1. **The answers must belong to this control set.** `control_set_version` is
   checked, and so is `control_set_fingerprint` when present. The version
   string alone is too coarse: the criteria are extracted from a PDF and the
   extraction is subject to human review, so the same "November 2023" control
   set can legitimately be regenerated with corrected criteria. Answers
   collected against the earlier file would then be scored against the
   corrected one, silently, and that is precisely the class of drift this
   project exists to refuse.

2. **An unrecognised criterion id is an error, not a shrug.** It means the
   answers were built against a different control set than the one loaded,
   whatever the version string claims.

An *unanswered* criterion is not an error. It scores as not met (see the PRD's
success criterion 4) and is reported as a coverage figure, because forcing a
user to write "unknown" 55 times to get a result they could have had anyway
teaches them to fill the file in mechanically, which is the opposite of what
an honest self-assessment needs.

Two of the five outcomes have to be justified in writing:

**not_applicable** is the only value in the system that can raise a maturity
level without anything being implemented, because it removes a requirement
from the set rather than failing it. ASD requires out-of-scope components to
be documented with a justification for their exclusion, and so does this.

**alternate_control** scores as met, so an unjustified one is simply a claim
that something counts. It is recorded, printed verbatim in every report, and
labelled there as self-declared and unverified.

**unknown deliberately needs no justification.** Making the honest answer
expensive is how a tool ends up full of confident guesses, which is the same
reasoning that put `unknown` in the schema to begin with.
"""

import hashlib
import json
from datetime import date, datetime

from e8 import scoring

REQUIRED_FIELDS = ("control_set_version", "answered_on", "answers")
JUSTIFIED = scoring.REQUIRES_JUSTIFICATION


class AnswersError(Exception):
    """The answers file is malformed, or does not belong to this control set."""


def fingerprint(control_set):
    """A short digest of everything about a control set that changes scoring.

    Covers each criterion's id, its text digest and the levels it is required
    at. The last of those is the reason this is not simply a hash of the file:
    re-tagging a criterion from [1, 2] to [1, 2, 3] changes what every level
    requires while leaving every text digest untouched.
    """
    parts = []
    for strategy in control_set["strategies"]:
        parts.append(strategy["id"])
        for criterion in strategy["criteria"]:
            levels = ",".join(str(lv) for lv in criterion["required_at_levels"])
            parts.append(f"{criterion['id']}:{criterion['sha256']}:{levels}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def _criterion_ids(control_set):
    return [c["id"] for s in control_set["strategies"] for c in s["criteria"]]


def validate(document, control_set):
    """Raise AnswersError unless `document` is a usable answer set for `control_set`.

    Returns the document unchanged on success, so it reads the same way as
    `model.validate`.
    """
    if not isinstance(document, dict):
        raise AnswersError("answers file must be a JSON object")

    missing = [f for f in REQUIRED_FIELDS if f not in document]
    if missing:
        raise AnswersError(f"answers file is missing required fields: {', '.join(missing)}")

    declared = document["control_set_version"]
    if declared != control_set["version"]:
        raise AnswersError(
            f"answers were given against control set version {declared!r}, but the "
            f"loaded control set is {control_set['version']!r}. Re-answer against the "
            f"current control set rather than scoring one against the other."
        )

    expected = fingerprint(control_set)
    declared_fp = document.get("control_set_fingerprint")
    if declared_fp is not None and declared_fp != expected:
        raise AnswersError(
            f"answers carry control set fingerprint {declared_fp!r}, but the loaded "
            f"control set is {expected!r}. The version string matches, so the criteria "
            f"themselves have changed since these answers were given: a requirement was "
            f"re-extracted, re-worded, or re-tagged to different maturity levels. "
            f"Re-check the changed criteria and re-answer them."
        )

    try:
        datetime.strptime(document["answered_on"], "%Y-%m-%d")
    except (TypeError, ValueError):
        raise AnswersError(
            f"answered_on must be an ISO date (YYYY-MM-DD), got {document['answered_on']!r}"
        )

    answers = document["answers"]
    if not isinstance(answers, dict):
        raise AnswersError("answers must be a JSON object of criterion id -> answer")

    known = set(_criterion_ids(control_set))
    unrecognised = sorted(set(answers) - known)
    if unrecognised:
        raise AnswersError(
            f"answers refer to {len(unrecognised)} criterion id(s) that are not in this "
            f"control set: {', '.join(unrecognised[:5])}"
            f"{' ...' if len(unrecognised) > 5 else ''}. The answers were built against a "
            f"different control set than the one loaded."
        )

    bad = sorted(
        f"{cid}={value!r}" for cid, value in answers.items()
        if value not in scoring.VALID_ANSWERS
    )
    if bad:
        raise AnswersError(
            f"answers must be one of {', '.join(scoring.VALID_ANSWERS)}. Invalid: "
            f"{', '.join(bad[:5])}{' ...' if len(bad) > 5 else ''}. Rejected rather than "
            f"counted as not met, so a typo cannot quietly lower a rating."
        )

    _validate_justifications(document, answers)
    _validate_not_applicable_scope(document, control_set)

    return document


def _is_written(value):
    """Whether a justification is actually written text.

    Type is checked, not just emptiness. `str(None).strip()` is `"None"`, which
    is non-empty, so a null justification would otherwise satisfy a rule whose
    entire point is that an exclusion has to say why in words. The same goes for
    a number, a boolean or a list. There is deliberately no minimum length: the
    control is that every justification is printed verbatim in the report, where
    a reader can judge it, not that it clears some arbitrary character count.
    """
    return isinstance(value, str) and bool(value.strip())


def _is_blank(value):
    """An entry a user can reasonably have left empty rather than filled in.

    Distinguished from a non-string value, which nobody leaves behind by
    accident and which the stray check below should still flag.
    """
    return isinstance(value, str) and not value.strip()


def _validate_justifications(document, answers):
    """Every not_applicable and alternate_control needs a written reason.

    Also rejects a justification attached to an answer that does not take one.
    That combination means the file was edited into a state its author did not
    intend: either the answer was changed and the reason left behind, or a
    reason was written against the wrong criterion.
    """
    justifications = document.get("justifications", {})
    if not isinstance(justifications, dict):
        raise AnswersError("justifications must be a JSON object of criterion id -> text")

    needs = {cid for cid, value in answers.items() if value in JUSTIFIED}

    missing = sorted(
        cid for cid in needs
        if not _is_written(justifications.get(cid))
    )
    if missing:
        raise AnswersError(
            f"{len(missing)} criterion(s) answered "
            f"{' or '.join(JUSTIFIED)} without a written justification: "
            f"{', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}. "
            f"A justification must be text containing something other than "
            f"whitespace; null, a number, a boolean or a list is not a reason. "
            f"These are the two answers that change a rating without anything being "
            f"implemented, so each one has to say why in writing."
        )

    stray = sorted(
        cid for cid, text in justifications.items()
        if not _is_blank(text) and cid not in needs
    )
    if stray:
        raise AnswersError(
            f"justification given for {len(stray)} criterion(s) whose answer does not "
            f"take one: {', '.join(stray[:5])}{' ...' if len(stray) > 5 else ''}. "
            f"Either the answer was changed and the reason left behind, or the reason "
            f"was written against the wrong criterion. Both are worth a second look."
        )


def _validate_not_applicable_scope(document, control_set):
    """Refuse an answer set that scopes out an entire mitigation strategy.

    ASD's assessment process guide is explicit that risk acceptance is not a
    justification for not implementing an entire mitigation strategy. Declaring
    every criterion in one inapplicable is the same move in a different costume,
    and it is refused loudly here rather than quietly producing a rating.
    """
    answers = document["answers"]
    for strategy in control_set["strategies"]:
        criteria = strategy["criteria"]
        excluded = [c for c in criteria
                    if answers.get(c["id"]) == scoring.NOT_APPLICABLE]
        if len(excluded) == len(criteria):
            raise AnswersError(
                f"every criterion in '{strategy['name']}' is marked not applicable, "
                f"which scopes out an entire mitigation strategy. ASD's assessment "
                f"process guide does not permit that: an entire strategy cannot be "
                f"excluded, only specific controls that genuinely do not apply. If "
                f"this strategy truly has no relevance to the environment, say so in "
                f"the assessment's scope rather than in its answers."
            )


def load(path, control_set):
    """Read and validate an answers file against an already-loaded control set."""
    try:
        with open(path, encoding="utf-8") as fh:
            document = json.load(fh)
    except FileNotFoundError:
        raise AnswersError(f"answers file not found: {path}")
    except json.JSONDecodeError as exc:
        raise AnswersError(f"answers file is not valid JSON: {exc}")
    return validate(document, control_set)


def unanswered(document, control_set):
    """Criterion ids in the control set that the answers file does not mention.

    These score as not met. They are reported separately from an explicit
    "unknown" because the two mean different things to the person reading the
    gap report: one is a question that was considered, the other is a question
    that was never reached.
    """
    answers = document["answers"]
    return [cid for cid in _criterion_ids(control_set) if cid not in answers]


def justification(document, criterion_id):
    """The written reason for a not_applicable or alternate_control answer."""
    return str(document.get("justifications", {}).get(criterion_id, "")).strip()


def template(control_set, organisation="", answered_on=None):
    """A blank answer set for `control_set`, every criterion set to "unknown".

    "unknown" rather than "not_met" because a blank assessment has not been
    done, and a file that starts out asserting every control has failed is as
    dishonest as one that starts out asserting they all pass.
    """
    return {
        "control_set_version": control_set["version"],
        "control_set_fingerprint": fingerprint(control_set),
        "organisation": organisation,
        "answered_on": (answered_on or date.today()).isoformat(),
        "answers": {cid: scoring.UNKNOWN for cid in _criterion_ids(control_set)},
        "justifications": {},
    }
