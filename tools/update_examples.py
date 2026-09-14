#!/usr/bin/env python3
"""Regenerate the committed example reports from the example answers file.

The rendered examples in `examples/` serve two purposes at once. They show a
reader what the tool actually produces without making them run it, and they are
the golden files `tests/test_report.py` compares against, so a rendering change
that nobody intended shows up as a failing test and a reviewable diff rather
than as a surprise in someone's report.

Run this after deliberately changing a renderer, then read the diff before
committing it. If the diff is not what you meant to change, that is the test
doing its job early.

    python3 tools/update_examples.py
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import answers, model, report, scoring  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROLS = os.path.join(ROOT, "controls", "e8-2023-11.json")
FIXTURES = [
    os.path.join(ROOT, "examples", "harbourline-freight.json"),
    os.path.join(ROOT, "examples", "redgum-plumbing.json"),
]
EXTENSIONS = {"text": "txt", "md": "md", "html": "html"}


def build_example(fixture):
    """The example report data, with every date pinned to committed values.

    `today` comes from the fixture's own `answered_on` rather than the clock,
    so regenerating this next year produces an identical file. A golden file
    that changes daily is a golden file people learn to ignore.
    """
    with open(CONTROLS, encoding="utf-8") as fh:
        sourced = date.fromisoformat(json.load(fh)["sourced_on"])

    control_set = model.load(CONTROLS, today=sourced)
    document = answers.load(fixture, control_set)
    results = scoring.score(control_set, document["answers"])
    unanswered = answers.unanswered(document, control_set)

    return report.build(
        control_set, document, results, unanswered,
        today=date.fromisoformat(document["answered_on"]),
    )


def main():
    for fixture in FIXTURES:
        data = build_example(fixture)
        base = os.path.splitext(fixture)[0]
        for fmt, extension in EXTENSIONS.items():
            path = f"{base}.{extension}"
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report.RENDERERS[fmt](data))
            print(f"wrote {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
