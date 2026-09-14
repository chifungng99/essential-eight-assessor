"""Tests for report rendering.

Run with:  python3 -m unittest discover -s tests -v

Two layers, because they catch different things.

**Golden files.** The committed reports in `examples/` must match what the
renderers produce, byte for byte. This catches unintended rendering changes as
a reviewable diff rather than as a surprise in someone's report, and it keeps
the examples in the repository honest: they cannot drift from what the tool
actually outputs.

**Invariants across formats.** Golden files prove the output has not changed.
They do not prove it is right, and they say nothing about a format someone adds
later. So the guarantees that matter (every format carries the disclaimer, names
the criteria behind the rating, and agrees with the others about the levels) are
asserted against all three formats at once, by iterating the renderer registry
rather than naming formats one at a time.
"""

import json
import os
import re
import sys
import unittest
from datetime import date
from html.parser import HTMLParser


def flat(text):
    """Whitespace-normalised, so an assertion is not defeated by line wrapping."""
    return re.sub(r"\s+", " ", text)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from e8 import answers, model, report, scoring  # noqa: E402
from update_examples import EXTENSIONS, FIXTURES, build_example  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROLS = os.path.join(ROOT, "controls", "e8-2023-11.json")
FIXTURE = os.path.join(ROOT, "examples", "harbourline-freight.json")
REDGUM = os.path.join(ROOT, "examples", "redgum-plumbing.json")


def load_control_set():
    with open(CONTROLS, encoding="utf-8") as fh:
        raw = json.load(fh)
    return model.load(CONTROLS, today=date.fromisoformat(raw["sourced_on"]))


def build_data(document=None, today=None):
    control_set = load_control_set()
    if document is None:
        document = answers.load(FIXTURE, control_set)
    results = scoring.score(control_set, document["answers"])
    unanswered = answers.unanswered(document, control_set)
    return report.build(
        control_set, document, results, unanswered,
        today=today or date.fromisoformat(document["answered_on"]),
    )


class TestGoldenFiles(unittest.TestCase):
    """The committed examples are what the renderers produce."""

    def test_every_format_matches_its_committed_example(self):
        for fixture in FIXTURES:
            data = build_example(fixture)
            stem = os.path.splitext(os.path.basename(fixture))[0]
            for fmt, extension in EXTENSIONS.items():
                with self.subTest(fixture=stem, format=fmt):
                    path = os.path.join(ROOT, "examples", f"{stem}.{extension}")
                    with open(path, encoding="utf-8") as fh:
                        committed = fh.read()
                    self.assertEqual(
                        report.RENDERERS[fmt](data), committed,
                        f"examples/{stem}.{extension} is out of date. If the rendering "
                        f"change was deliberate, run tools/update_examples.py and read "
                        f"the diff before committing it.",
                    )

    def test_the_examples_are_reproducible_from_committed_data_alone(self):
        """No clock, no environment. Regenerating next year gives the same file."""
        for fixture in FIXTURES:
            self.assertEqual(report.render_markdown(build_example(fixture)),
                             report.render_markdown(build_example(fixture)))


class TestEveryFormat(unittest.TestCase):
    """Guarantees that must hold whatever the format, including one added later."""

    def setUp(self):
        self.data = build_data()
        self.rendered = {fmt: fn(self.data) for fmt, fn in report.RENDERERS.items()}

    def test_carries_the_disclaimer(self):
        """A report gets forwarded and screenshotted. It has to still say what
        it is when it arrives without the conversation that produced it."""
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("NOT A CERTIFIED ASD ASSESSMENT", text)

    def test_names_the_criteria_behind_the_rating(self):
        """PRD success criterion 3. A level with no list of what was missing is
        the spreadsheet summary cell this project exists to replace."""
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("patch-os-01", text)
                self.assertIn("patch-apps-10", text)

    def test_says_how_each_unmet_criterion_was_answered(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("unknown", text)
                self.assertIn("not_met", text)

    def test_reports_the_same_levels_in_every_format(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("Maturity Level One", text)
                self.assertIn("Maturity Level Zero", text)
                self.assertIn("Maturity Level Two", text)

    def test_gives_no_single_overall_figure(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("No overall rating is given", text)

    def test_states_which_control_set_was_rated_against(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("November 2023", text)
                self.assertIn(self.data.fingerprint, text)

    def test_reports_coverage(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("55 of 55 criteria answered", text)


class TestSupersededNote(unittest.TestCase):
    """A gap below the awarded level needs explaining in every format, or it
    reads as a bug in the tool."""

    def setUp(self):
        control_set = load_control_set()
        document = answers.template(control_set, organisation="Example Pty Ltd")
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        document["answers"]["patch-apps-07"] = scoring.NOT_MET  # not required at Level 3
        document["answered_on"] = "2026-09-12"
        self.data = build_data(document)

    def test_the_strategy_still_reaches_level_three(self):
        section = next(s for s in self.data.sections if s.strategy_id == "patch-apps")
        self.assertEqual(section.level, 3)
        self.assertTrue(section.has_superseded_gap)

    def test_every_format_explains_it(self):
        for fmt, fn in report.RENDERERS.items():
            with self.subTest(format=fmt):
                text = fn(self.data)
                self.assertIn("superseded at the level awarded", text)
                self.assertIn("The stricter replacement was met.", text)


class TestHtmlSafety(unittest.TestCase):
    """The HTML report is the one that gets opened in a browser."""

    def _render(self, organisation):
        control_set = load_control_set()
        document = answers.template(control_set, organisation=organisation)
        document["answered_on"] = "2026-09-12"
        return report.render_html(build_data(document))

    def test_escapes_the_organisation_name(self):
        """`organisation` comes straight out of the answers file, which the PRD
        treats as untrusted input."""
        rendered = self._render('<script>alert("x")</script>')
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_escapes_quotes_and_ampersands(self):
        rendered = self._render('Smith & Sons "Pty" Ltd')
        self.assertIn("&amp;", rendered)
        self.assertIn("&quot;", rendered)
        self.assertNotIn('Sons "Pty"', rendered)

    def test_has_no_external_references(self):
        """The PRD forbids network access at runtime. A report that pulls a font
        from a CDN breaks that and leaks the fact that it was opened."""
        rendered = report.render_html(build_data())
        self.assertEqual(re.findall(r'(?:https?:)?//[^\s"\'<>]+', rendered), [])
        self.assertNotIn("<script", rendered.lower())

    def test_is_well_formed(self):
        class Checker(HTMLParser):
            void = {"meta", "br", "hr", "img", "input", "link"}

            def __init__(self):
                super().__init__()
                self.stack, self.errors = [], []

            def handle_starttag(self, tag, attrs):
                if tag not in self.void:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if not self.stack or self.stack[-1] != tag:
                    self.errors.append(f"mismatched </{tag}>")
                else:
                    self.stack.pop()

        checker = Checker()
        checker.feed(report.render_html(build_data()))
        self.assertEqual(checker.errors, [])
        self.assertEqual(checker.stack, [])


class TestAgePhrasing(unittest.TestCase):
    """The control set's age appears in every report, so its wording is part of
    the golden output."""

    def test_singular_at_one_day(self):
        data = build_data(today=date(2026, 9, 12))
        self.assertEqual(data.control_set_age_days, 1)
        self.assertEqual(data.age_phrase, "1 day ago")

    def test_plural_otherwise(self):
        self.assertEqual(build_data(today=date(2026, 9, 13)).age_phrase, "2 days ago")
        self.assertEqual(build_data(today=date(2026, 9, 11)).age_phrase, "0 days ago")


class TestAllMet(unittest.TestCase):
    def test_a_fully_met_assessment_says_so_rather_than_printing_an_empty_gap_list(self):
        control_set = load_control_set()
        document = answers.template(control_set)
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        document["answered_on"] = "2026-09-12"
        data = build_data(document)

        for section in data.sections:
            self.assertEqual(section.level, 3)
            self.assertEqual(section.gaps, [])

        for fmt, fn in report.RENDERERS.items():
            with self.subTest(format=fmt):
                self.assertIn("Every applicable requirement met at all three maturity levels",
                              fn(data))


class TestDeclarations(unittest.TestCase):
    """The audit trail. Every answer that changed the rating without anything
    being implemented is listed, in every format, with its stated reason."""

    def setUp(self):
        control_set = load_control_set()
        document = answers.load(REDGUM, control_set)
        self.data = build_data(document)
        self.rendered = {fmt: fn(self.data) for fmt, fn in report.RENDERERS.items()}

    def test_the_counts_are_separated(self):
        self.assertEqual(self.data.not_applicable_count, 9)
        self.assertEqual(self.data.alternate_control_count, 1)
        self.assertIn("9 declared not applicable", self.data.coverage)
        self.assertIn("1 met by an alternate control", self.data.coverage)

    def test_every_format_lists_each_declaration_with_its_reason(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                for d in self.data.declarations:
                    self.assertIn(d.criterion_id, text)
                    self.assertIn(flat(d.justification), flat(text))

    def test_every_format_labels_alternate_controls_as_self_declared(self):
        """A reader must not mistake an alternate control for the same evidence
        as an implemented one."""
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("self-declared", flat(text))
                self.assertIn("NOT been independently verified", flat(text))

    def test_every_format_explains_what_not_applicable_did(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("removed from the requirement set rather than",
                              flat(text))

    def test_every_format_shows_the_applicable_base(self):
        for fmt, text in self.rendered.items():
            with self.subTest(format=fmt):
                self.assertIn("applicable", text)

    def test_a_report_with_no_declarations_omits_the_section(self):
        data = build_data()  # the harbourline fixture excludes nothing
        self.assertEqual(data.declarations, [])
        for fmt, fn in report.RENDERERS.items():
            with self.subTest(format=fmt):
                self.assertNotIn("self-declared", flat(fn(data)))


class TestUnawardableLevel(unittest.TestCase):
    """A level with nothing applicable is reported as not awarded, with the
    reason, rather than appearing as an ordinary failure."""

    def setUp(self):
        control_set = load_control_set()
        document = answers.template(control_set, organisation="Example Pty Ltd")
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        document["answered_on"] = "2026-09-14"
        patch_os = next(s for s in control_set["strategies"] if s["id"] == "patch-os")
        for c in model.criteria_for_level(patch_os, 1):
            document["answers"][c["id"]] = scoring.NOT_APPLICABLE
            document["justifications"][c["id"]] = "Not present in this environment."
        answers.validate(document, control_set)
        self.data = build_data(document)

    def test_every_format_says_the_level_was_not_awarded_and_why(self):
        for fmt, fn in report.RENDERERS.items():
            with self.subTest(format=fmt):
                text = flat(fn(self.data))
                self.assertIn("no applicable requirements", text)
                self.assertIn("Nothing was demonstrated at this level", text)


class TestReducedBaseDisclosure(unittest.TestCase):
    """Level One on three of eight requirements is a narrower claim than eight
    of eight, and the report has to show which one the reader is holding."""

    def setUp(self):
        control_set = load_control_set()
        document = answers.template(control_set, organisation="Example Pty Ltd")
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        document["answered_on"] = "2026-09-14"
        for cid in ["patch-os-03", "patch-os-04", "patch-os-05",
                    "patch-os-06", "patch-os-07"]:
            document["answers"][cid] = scoring.NOT_APPLICABLE
            document["justifications"][cid] = (
                "No workstations, servers or network devices. The fleet is managed "
                "mobile devices only."
            )
        answers.validate(document, control_set)
        self.data = build_data(document)

    def test_the_level_is_still_awarded(self):
        section = next(s for s in self.data.sections if s.strategy_id == "patch-os")
        self.assertEqual(section.level, 3)

    def test_every_format_shows_three_of_eight_rather_than_a_clean_pass(self):
        section = next(s for s in self.data.sections if s.strategy_id == "patch-os")
        self.assertEqual(section.bases[0], (1, 3, 8))
        for fmt, fn in report.RENDERERS.items():
            with self.subTest(format=fmt):
                self.assertIn("3/8", fn(self.data))


class TestHtmlEscapesJustifications(unittest.TestCase):
    def test_a_justification_cannot_inject_markup(self):
        """Justifications are free text from an untrusted answers file."""
        control_set = load_control_set()
        document = answers.template(control_set, organisation="Example Pty Ltd")
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        document["answered_on"] = "2026-09-14"
        document["answers"]["patch-os-03"] = scoring.NOT_APPLICABLE
        document["justifications"]["patch-os-03"] = '<script>alert("x")</script>'
        answers.validate(document, control_set)
        rendered = report.render_html(build_data(document))
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
