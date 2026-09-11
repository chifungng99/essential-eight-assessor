"""Load and validate a control set.

A control set is the machine-readable form of a published maturity model. This
module knows how to read one and how to refuse a bad one. It knows nothing about
the Essential Eight specifically: the framework lives entirely in the data file, so
a future ASD "Essentials" chapter is a new file rather than a change here.

Two refusals are deliberate and are the reason this module exists at all:

1. A control set that fails validation is never partially loaded. A tool that
   limps along with half a framework produces a score that looks like every other
   score.
2. A control set older than its own `max_age_days` raises rather than returning.
   The Essential Eight is expected to begin deprecating from around mid-2027, so a
   rating produced against a superseded model is not a small error, it is a wrong
   answer wearing the costume of a right one.
"""

import hashlib
import json
from datetime import date, datetime

VALID_LEVELS = (1, 2, 3)

REQUIRED_TOP_LEVEL = (
    "model", "version", "source_url", "sourced_on", "max_age_days", "licence", "strategies",
)
REQUIRED_CRITERION = ("id", "text", "required_at_levels", "sha256")


class ControlSetError(Exception):
    """The control set is malformed and cannot be used."""


class StaleControlSetError(ControlSetError):
    """The control set is older than it declares itself good for."""

    def __init__(self, age_days, max_age_days, version, sourced_on):
        self.age_days = age_days
        self.max_age_days = max_age_days
        super().__init__(
            f"Control set '{version}' was sourced on {sourced_on}, {age_days} days ago, "
            f"which exceeds its max_age_days of {max_age_days}. Refusing to produce a "
            f"maturity rating against a control set that cannot be shown to be current. "
            f"Re-check the published model and re-run tools/extract_controls.py."
        )


def _parse_date(value, field):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ControlSetError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")


def validate(data):
    """Raise ControlSetError unless `data` is a usable control set.

    Checked rather than assumed, because every one of these has a failure mode that
    is silent at runtime: a duplicate id makes one criterion shadow another, an
    empty required_at_levels makes a criterion unreachable and therefore free, and
    a sha256 that no longer matches its text means the file has drifted from what
    was extracted from the source document.
    """
    if not isinstance(data, dict):
        raise ControlSetError("control set must be a JSON object")

    missing = [k for k in REQUIRED_TOP_LEVEL if k not in data]
    if missing:
        raise ControlSetError(f"missing required fields: {', '.join(missing)}")

    _parse_date(data["sourced_on"], "sourced_on")

    if not isinstance(data["max_age_days"], int) or data["max_age_days"] <= 0:
        raise ControlSetError("max_age_days must be a positive integer")

    strategies = data["strategies"]
    if not isinstance(strategies, list) or not strategies:
        raise ControlSetError("strategies must be a non-empty list")

    seen_strategy_ids = set()
    seen_criterion_ids = set()

    for strategy in strategies:
        for key in ("id", "name", "criteria"):
            if key not in strategy:
                raise ControlSetError(f"strategy missing '{key}': {strategy!r}")

        if strategy["id"] in seen_strategy_ids:
            raise ControlSetError(f"duplicate strategy id: {strategy['id']}")
        seen_strategy_ids.add(strategy["id"])

        criteria = strategy["criteria"]
        if not isinstance(criteria, list) or not criteria:
            raise ControlSetError(f"strategy '{strategy['id']}' has no criteria")

        for criterion in criteria:
            missing = [k for k in REQUIRED_CRITERION if k not in criterion]
            if missing:
                raise ControlSetError(
                    f"criterion in '{strategy['id']}' missing: {', '.join(missing)}"
                )

            cid = criterion["id"]
            if cid in seen_criterion_ids:
                raise ControlSetError(f"duplicate criterion id: {cid}")
            seen_criterion_ids.add(cid)

            if not str(criterion["text"]).strip():
                raise ControlSetError(f"criterion '{cid}' has empty text")

            levels = criterion["required_at_levels"]
            if not isinstance(levels, list) or not levels:
                raise ControlSetError(
                    f"criterion '{cid}' is required at no maturity level, so it can "
                    f"never affect a rating"
                )
            bad = [lv for lv in levels if lv not in VALID_LEVELS]
            if bad:
                raise ControlSetError(f"criterion '{cid}' has invalid levels: {bad}")
            if sorted(set(levels)) != list(levels):
                raise ControlSetError(
                    f"criterion '{cid}' levels must be sorted and unique, got {levels}"
                )

            digest = hashlib.sha256(criterion["text"].encode("utf-8")).hexdigest()[:12]
            if digest != criterion["sha256"]:
                raise ControlSetError(
                    f"criterion '{cid}' text does not match its recorded sha256. The "
                    f"file has been edited by hand, or has drifted from the source "
                    f"document. Re-run tools/extract_controls.py rather than patching."
                )

        # A strategy that has nothing to satisfy at some level would award that level
        # for free. Almost certainly an extraction bug rather than an intent.
        for level in VALID_LEVELS:
            if not any(level in c["required_at_levels"] for c in criteria):
                raise ControlSetError(
                    f"strategy '{strategy['id']}' has no criteria at Maturity Level {level}"
                )

    return data


def age_days(data, today=None):
    """Days between `sourced_on` and `today`. Injectable date, never date.today() inline."""
    today = today or date.today()
    return (today - _parse_date(data["sourced_on"], "sourced_on")).days


def is_stale(data, today=None):
    return age_days(data, today) > data["max_age_days"]


def load(path, today=None, allow_stale=False):
    """Read, validate and age-check a control set.

    `allow_stale` exists for the explicit case where a user knows the model is old
    and wants to look at it anyway. It is opt-in and never the default, because the
    whole point is that staleness should be loud.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ControlSetError(f"control set not found: {path}")
    except json.JSONDecodeError as exc:
        raise ControlSetError(f"control set is not valid JSON: {exc}")

    validate(data)

    if is_stale(data, today) and not allow_stale:
        raise StaleControlSetError(
            age_days(data, today), data["max_age_days"], data["version"], data["sourced_on"]
        )
    return data


def criteria_for_level(strategy, level):
    """The complete requirement set for one strategy at one maturity level.

    Each appendix of the published model restates the full set for its level rather
    than listing additions, and a higher level sometimes REPLACES a requirement with
    a stricter one rather than adding to it. At Maturity Level Three, for example,
    the blanket "within two weeks" patching requirement is gone, replaced by 48 hours
    for critical vulnerabilities and two weeks for non-critical ones.

    So a level's requirement set is exactly the criteria tagged with that level. It
    is NOT that level's criteria plus everything below, which would resurrect
    requirements the model has deliberately superseded.
    """
    if level not in VALID_LEVELS:
        raise ValueError(f"maturity level must be one of {VALID_LEVELS}, got {level!r}")
    return [c for c in strategy["criteria"] if level in c["required_at_levels"]]
