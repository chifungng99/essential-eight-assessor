"""Command line entry point: an answers file in, a maturity rating out.

    python3 -m e8 init --organisation "Harbourline Freight Pty Ltd"
    python3 -m e8 assess my.assessment.json

Three things this deliberately does not offer, each because offering it would
undermine something the tool is for:

**No `--allow-stale` on either command.** `e8/model.py` refuses a control set
older than its own `max_age_days`, and a flag to wave that through is a flag
that will be used. `tools/review_controls.py` still reads a stale set, because
reading the criteria is exactly what you want to do when the model has moved
on. Producing a rating from them is not.

**No `--fail-under LEVEL` for use as a CI gate.** It would be four lines and it
is the single most requested feature a tool like this attracts. It is also the
affordance that turns an indicative self-assessment into something treated as
a compliance control, which the PRD names as a risk.

**No single overall maturity figure.** Version one covers three of the eight
mitigation strategies. A combined number would be read as an Essential Eight
rating, and no amount of surrounding text survives a screenshot.

Rendering lives in `e8/report.py`, which is what `--format` selects between.
"""

import argparse
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import answers as answers_module  # noqa: E402
from e8 import model, report, scoring  # noqa: E402

DEFAULT_CONTROLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "controls", "e8-2023-11.json",
)
DEFAULT_OUT = "my.assessment.json"

def _wrap(text, indent="", width=88):
    return textwrap.fill(text, width, initial_indent=indent, subsequent_indent=indent)


def _gitignore_covers(path):
    """Whether this repository's .gitignore already protects `path`.

    A completed assessment and a rendered report are the same sensitive
    document in two formats: a list of where an organisation is weakest. The
    shipped .gitignore covers assessments/, *.assessment.json and reports/.
    Anything else gets a warning rather than a refusal, because it is the
    user's filesystem and they may have their own arrangements.
    """
    basename = os.path.basename(path)
    parts = os.path.normpath(path).split(os.sep)
    return (
        basename.endswith(".assessment.json")
        or "assessments" in parts
        or "reports" in parts
    )


def cmd_init(args):
    control_set = model.load(args.controls)

    if os.path.exists(args.out) and not args.force:
        print(
            f"error: {args.out} already exists. Refusing to overwrite what may be a "
            f"completed assessment. Pass --force to replace it.",
            file=sys.stderr,
        )
        return 1

    document = answers_module.template(control_set, organisation=args.organisation)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"Wrote {len(document['answers'])} unanswered criteria to {args.out}")
    print()
    print(_wrap(
        "Read the criteria as you fill it in: python3 tools/review_controls.py --level 1 "
        "prints Maturity Level One the way Appendix A of the published model groups it. "
        "Answer each criterion met, alternate_control, not_met, not_applicable or "
        "unknown. unknown is a real answer and scores as not met; guessing met is the "
        "one thing that makes the result worthless. not_applicable and "
        "alternate_control each need a written reason in the justifications block, "
        "because they are the two answers that change a rating without anything being "
        "implemented, and both are printed in full in the report."
    ))

    if not _gitignore_covers(args.out):
        print()
        print(_wrap(
            f"Note: {args.out} will hold a map of where this organisation is weakest. "
            f"This repository's .gitignore covers assessments/ and *.assessment.json, "
            f"and this filename matches neither, so check it is not about to be committed."
        ))
    return 0


def cmd_assess(args):
    control_set = model.load(args.controls)
    document = answers_module.load(args.answers, control_set)
    results = scoring.score(control_set, document["answers"])
    unanswered_ids = answers_module.unanswered(document, control_set)

    data = report.build(control_set, document, results, unanswered_ids)
    rendered = report.RENDERERS[args.format](data)

    if not args.out:
        print(rendered)
        return 0

    # A report is regenerable from the answers file, so unlike `init` this
    # overwrites without asking. Refusing here would only teach people to pass
    # --force reflexively, which is how a real refusal stops being read.
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    print(f"Wrote {args.format} report to {args.out}")

    if not _gitignore_covers(args.out):
        print()
        print(_wrap(
            f"Note: {args.out} lists where this organisation is weakest, the same "
            f"sensitive content as the answers file it came from. This repository's "
            f".gitignore covers reports/, and this path is not under it, so check it "
            f"is not about to be committed."
        ))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="e8",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="write a blank answers file")
    p_init.add_argument("--controls", default=DEFAULT_CONTROLS)
    p_init.add_argument("--out", default=DEFAULT_OUT)
    p_init.add_argument("--organisation", default="")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite an existing answers file")
    p_init.set_defaults(handler=cmd_init)

    p_assess = sub.add_parser("assess", help="score a completed answers file")
    p_assess.add_argument("answers", help="path to a completed answers file")
    p_assess.add_argument("--controls", default=DEFAULT_CONTROLS)
    p_assess.add_argument("--format", choices=sorted(report.RENDERERS), default="text",
                          help="output format (default: text)")
    p_assess.add_argument("--out", help="write to a file instead of stdout")
    p_assess.set_defaults(handler=cmd_assess)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (model.ControlSetError, answers_module.AnswersError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
