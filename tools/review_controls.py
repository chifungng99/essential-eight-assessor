#!/usr/bin/env python3
"""Print the control set for human review against the published model.

The test suite proves the loader and the validator work. It cannot prove the
criteria were extracted correctly, because it has no access to the source document
and no judgement. If a requirement were dropped or truncated, every test would still
pass and the tool would rate against a quietly incomplete framework.

So there is a human gate, and this script exists to make it practical: read the
output side by side with Appendices A, B and C of the published model and confirm
each level's set matches. Fifty-five JSON objects are not reviewable; a printed
list grouped the way the PDF groups it is.

Usage:
    python3 tools/review_controls.py                 # all levels
    python3 tools/review_controls.py --level 1       # one level, matching Appendix A
"""

import argparse
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import model  # noqa: E402

DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "controls", "e8-2023-11.json")
APPENDIX = {1: "A", 2: "B", 3: "C"}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--controls", default=DEFAULT)
    ap.add_argument("--level", type=int, choices=(1, 2, 3))
    args = ap.parse_args()

    # Reviewing a stale control set is exactly when you most want to see it.
    data = model.load(args.controls, allow_stale=True)

    print(f"{data['model']} — {data['version']}")
    print(f"Sourced {data['sourced_on']} from {data['source_url']}")
    print(f"Licence: {data['licence']['name']}")
    print()
    print(textwrap.fill(data["licence"]["attribution"], 88))
    print()

    levels = [args.level] if args.level else [1, 2, 3]
    for level in levels:
        print("=" * 88)
        print(f"MATURITY LEVEL {level}   (compare against Appendix {APPENDIX[level]})")
        print("=" * 88)
        for strategy in data["strategies"]:
            criteria = model.criteria_for_level(strategy, level)
            print(f"\n{strategy['name']}  ({len(criteria)} requirements)\n")
            for i, c in enumerate(criteria, 1):
                body = textwrap.fill(c["text"], 84, initial_indent="     ",
                                     subsequent_indent="     ")
                print(f"  {i:2}. [{c['id']}]")
                print(body)
                print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
