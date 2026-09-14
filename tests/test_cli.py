"""Tests for the command line interface.

Run with:  python3 -m unittest discover -s tests -v

Includes the stage 3 gate from docs/PRD.md: the tool runs end to end on the
committed example fixture and produces the maturity levels that fixture was
built to produce.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from e8 import answers, cli, model, report, scoring  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROLS = os.path.join(ROOT, "controls", "e8-2023-11.json")
FIXTURE = os.path.join(ROOT, "examples", "harbourline-freight.json")


def run(argv):
    """Run the CLI in-process. Returns (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def load_control_set():
    with open(CONTROLS, encoding="utf-8") as fh:
        raw = json.load(fh)
    return model.load(CONTROLS, today=date.fromisoformat(raw["sourced_on"]))


class TestEndToEndOnTheFixture(unittest.TestCase):
    """The stage 3 gate."""

    def setUp(self):
        self.code, self.out, self.err = run(["assess", FIXTURE])

    def test_succeeds(self):
        self.assertEqual(self.code, 0, self.err)

    def test_reports_the_levels_the_fixture_was_built_to_produce(self):
        self.assertIn("Patch applications             Maturity Level One", self.out)
        self.assertIn("Patch operating systems        Maturity Level Zero", self.out)
        self.assertIn("Multi-factor authentication    Maturity Level Two", self.out)

    def test_the_fixture_still_scores_as_documented(self):
        """Guards the fixture itself. If a criterion is re-extracted or
        re-tagged, the fixture may no longer exercise the levels it was built
        for, and a passing CLI test would hide that."""
        control_set = load_control_set()
        document = answers.load(FIXTURE, control_set)
        levels = {r.strategy_id: r.level for r in scoring.score(control_set, document["answers"])}
        self.assertEqual(levels, {"patch-apps": 1, "patch-os": 0, "mfa": 2})

    def test_names_the_criteria_behind_the_rating(self):
        """PRD success criterion 3: no summary number without the criteria."""
        self.assertIn("[patch-os-01]", self.out)
        self.assertIn("answered: unknown", self.out)

    def test_carries_the_disclaimer(self):
        self.assertIn("NOT A CERTIFIED ASD ASSESSMENT", self.out)

    def test_gives_no_single_overall_figure(self):
        self.assertIn("No overall rating is given", self.out)

    def test_states_the_control_set_it_rated_against(self):
        self.assertIn("November 2023", self.out)
        self.assertIn(answers.fingerprint(load_control_set()), self.out)


class TestSupersededExplanation(unittest.TestCase):
    """When a level below the awarded one has a gap, the output has to say why,
    or it reads as a bug in the tool."""

    def test_explains_a_gap_below_the_awarded_level(self):
        control_set = load_control_set()
        document = answers.template(control_set, organisation="Example Pty Ltd")
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        document["answers"]["patch-apps-07"] = scoring.NOT_MET  # not required at Level 3

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.assessment.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(document, fh)
            code, out, err = run(["assess", path])

        self.assertEqual(code, 0, err)
        self.assertIn("Patch applications             Maturity Level Three", out)
        self.assertIn("superseded at the level awarded", out)
        self.assertIn("The stricter replacement was met.", out)


class TestInit(unittest.TestCase):
    def test_writes_a_valid_blank_assessment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "my.assessment.json")
            code, out, err = run(["init", "--out", path, "--organisation", "Example Pty Ltd"])
            self.assertEqual(code, 0, err)

            control_set = load_control_set()
            document = answers.load(path, control_set)
            self.assertEqual(document["organisation"], "Example Pty Ltd")
            self.assertEqual(set(document["answers"].values()), {scoring.UNKNOWN})

    def test_refuses_to_overwrite_an_existing_assessment(self):
        """Overwriting 55 answered questions with a blank file is the most
        destructive thing this tool could do to someone."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "my.assessment.json")
            run(["init", "--out", path])
            code, out, err = run(["init", "--out", path])
            self.assertEqual(code, 1)
            self.assertIn("Refusing to overwrite", err)

    def test_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "my.assessment.json")
            run(["init", "--out", path])
            code, out, err = run(["init", "--out", path, "--force"])
            self.assertEqual(code, 0, err)

    def test_warns_when_the_filename_is_not_covered_by_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "answers.json")
            code, out, err = run(["init", "--out", path])
            self.assertEqual(code, 0, err)
            self.assertIn("not about to be committed", out)

    def test_does_not_warn_for_a_covered_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "my.assessment.json")
            code, out, err = run(["init", "--out", path])
            self.assertNotIn("not about to be committed", out)


class TestRefusals(unittest.TestCase):
    """Each of these must fail with a message, not a traceback."""

    def test_refuses_an_answers_file_for_a_different_control_set_version(self):
        control_set = load_control_set()
        document = answers.template(control_set)
        document["control_set_version"] = "November 2019"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.assessment.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(document, fh)
            code, out, err = run(["assess", path])
        self.assertEqual(code, 1)
        self.assertIn("November 2019", err)

    def test_refuses_a_stale_control_set_rather_than_rating_against_it(self):
        """PRD success criterion 5. The refusal is the feature, so there is
        deliberately no --allow-stale to wave it through."""
        with open(CONTROLS, encoding="utf-8") as fh:
            stale = json.load(fh)
        stale["sourced_on"] = "2020-01-01"

        with tempfile.TemporaryDirectory() as tmp:
            controls_path = os.path.join(tmp, "stale.json")
            with open(controls_path, "w", encoding="utf-8") as fh:
                json.dump(stale, fh)
            code, out, err = run(["assess", FIXTURE, "--controls", controls_path])

        self.assertEqual(code, 1)
        self.assertIn("Refusing to produce a maturity rating", err)

    def test_assess_has_no_allow_stale_flag(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.build_parser().parse_args(["assess", FIXTURE, "--allow-stale"])

    def test_assess_has_no_fail_under_flag(self):
        """Named in the PRD risks: a CI gate is what turns an indicative
        self-assessment into something treated as a compliance control."""
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.build_parser().parse_args(["assess", FIXTURE, "--fail-under", "2"])

    def test_refuses_a_missing_answers_file(self):
        code, out, err = run(["assess", "/nonexistent/x.assessment.json"])
        self.assertEqual(code, 1)
        self.assertIn("not found", err)


class TestCoverageReporting(unittest.TestCase):
    def test_reports_unanswered_criteria_as_counted_not_met(self):
        control_set = load_control_set()
        document = answers.template(control_set)
        document["answers"] = {cid: scoring.MET for cid in document["answers"]}
        del document["answers"]["mfa-01"]

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.assessment.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(document, fh)
            code, out, err = run(["assess", path])

        self.assertEqual(code, 0, err)
        self.assertIn("54 of 55 criteria answered", out)
        self.assertIn("1 unanswered, each counted as not met", out)
        self.assertIn("answered: unanswered", out)


class TestFormats(unittest.TestCase):
    """`--format` selects between the renderers in e8/report.py."""

    def test_defaults_to_text_on_stdout(self):
        code, out, err = run(["assess", FIXTURE])
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("ASD Essential Eight Maturity Model"))

    def test_every_registered_format_runs_from_the_cli(self):
        """Iterates the registry rather than naming formats, so a format added
        to e8/report.py without a CLI path fails here."""
        for fmt in report.RENDERERS:
            with self.subTest(format=fmt):
                code, out, err = run(["assess", FIXTURE, "--format", fmt])
                self.assertEqual(code, 0, err)
                self.assertIn("NOT A CERTIFIED ASD ASSESSMENT", out)

    def test_rejects_an_unknown_format(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.build_parser().parse_args(["assess", FIXTURE, "--format", "pdf"])

    def test_out_writes_the_file_and_says_where(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reports", "assessment.html")
            os.makedirs(os.path.dirname(path))
            code, out, err = run(["assess", FIXTURE, "--format", "html", "--out", path])
            self.assertEqual(code, 0, err)
            self.assertIn(path, out)
            with open(path, encoding="utf-8") as fh:
                written = fh.read()
            self.assertTrue(written.startswith("<!doctype html>"))
            self.assertIn("NOT A CERTIFIED ASD ASSESSMENT", written)

    def test_out_overwrites_without_asking(self):
        """Unlike an answers file, a report is regenerable. Refusing here would
        only teach people to pass --force reflexively."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reports", "assessment.md")
            os.makedirs(os.path.dirname(path))
            run(["assess", FIXTURE, "--format", "md", "--out", path])
            code, out, err = run(["assess", FIXTURE, "--format", "md", "--out", path])
            self.assertEqual(code, 0, err)

    def test_warns_when_the_report_path_is_not_covered_by_gitignore(self):
        """A rendered report is the same sensitive content as the answers file."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "assessment.md")
            code, out, err = run(["assess", FIXTURE, "--format", "md", "--out", path])
            self.assertEqual(code, 0, err)
            self.assertIn("not about to be committed", out)

    def test_does_not_warn_for_a_path_under_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reports", "assessment.md")
            os.makedirs(os.path.dirname(path))
            code, out, err = run(["assess", FIXTURE, "--format", "md", "--out", path])
            self.assertNotIn("not about to be committed", out)


class TestNotApplicableEndToEnd(unittest.TestCase):
    """The second committed fixture, end to end through the CLI."""

    REDGUM = os.path.join(ROOT, "examples", "redgum-plumbing.json")

    def test_runs_and_reports_the_expected_levels(self):
        code, out, err = run(["assess", self.REDGUM])
        self.assertEqual(code, 0, err)
        self.assertIn("Patch applications             Maturity Level Three", out)
        self.assertIn("Patch operating systems        Maturity Level Three", out)
        self.assertIn("Multi-factor authentication    Maturity Level Two", out)

    def test_declares_its_exclusions_and_alternate_control(self):
        code, out, err = run(["assess", self.REDGUM])
        self.assertIn("9 declared not applicable", out)
        self.assertIn("1 met by an alternate control", out)
        self.assertIn("DECLARATIONS", out)

    def test_refuses_the_same_file_with_a_justification_removed(self):
        control_set = load_control_set()
        document = answers.load(self.REDGUM, control_set)
        del document["justifications"]["patch-os-03"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.assessment.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(document, fh)
            code, out, err = run(["assess", path])
        self.assertEqual(code, 1)
        self.assertIn("without a written justification", err)

    def test_refuses_a_whole_strategy_exclusion(self):
        control_set = load_control_set()
        document = answers.template(control_set, organisation="Example Pty Ltd")
        strategy = next(s for s in control_set["strategies"] if s["id"] == "mfa")
        for c in strategy["criteria"]:
            document["answers"][c["id"]] = scoring.NOT_APPLICABLE
            document["justifications"][c["id"]] = "Out of scope for us."
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.assessment.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(document, fh)
            code, out, err = run(["assess", path])
        self.assertEqual(code, 1)
        self.assertIn("entire mitigation strategy", err)


if __name__ == "__main__":
    unittest.main()
