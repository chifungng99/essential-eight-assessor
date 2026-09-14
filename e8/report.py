"""Render a scored assessment as plain text, Markdown or HTML.

All three formats are built from one intermediate structure rather than three
independent renderers walking the results. Three renderers drift: someone adds
the coverage figure to the HTML, forgets the Markdown, and the two reports of
the same assessment quietly disagree about how much of it was answered. Here
the only thing a format decides is presentation.

Two things every format carries, without an option to turn either off:

**The disclaimer.** A report gets forwarded, screenshotted and pasted into
slide decks, and it has to still say what it is when it arrives somewhere
without the conversation that produced it.

**The criteria behind the rating.** A maturity level with no list of what was
missing is the spreadsheet summary cell this project exists to replace.

**The declarations the rating rests on.** Every not_applicable and every
alternate_control is listed with its justification printed verbatim, and each
level shows the applicable base it was computed from. A level awarded on three
of eight requirements is not the same claim as one awarded on eight of eight,
and the reader has to be able to see which they are holding. Alternate controls
are labelled self-declared and unverified wherever they appear: they satisfy
ASD's rule, but no assessor has looked at them, and a reader must not mistake
one for the same evidence as an implemented control.

The date is injected rather than read from the clock inside the renderer, the
same way `e8/model.py` takes `today`. It keeps the committed example reports
reproducible, which is what makes them usable as golden files.
"""

import html
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from e8 import model, scoring

LEVEL_NAMES = {
    0: "Maturity Level Zero",
    1: "Maturity Level One",
    2: "Maturity Level Two",
    3: "Maturity Level Three",
}

DISCLAIMER = (
    "INDICATIVE SELF-ASSESSMENT, NOT A CERTIFIED ASD ASSESSMENT. This reports what "
    "the organisation says about itself. It has no affiliation with, and no "
    "endorsement from, the Australian Signals Directorate. It is a starting point "
    "for a conversation, not evidence of compliance."
)

NO_OVERALL = (
    "No overall rating is given. Three of the eight mitigation strategies are in "
    "scope here, so a single combined figure would be read as an Essential Eight "
    "maturity rating that this assessment cannot support."
)

ALTERNATE_CONTROL_WARNING = (
    "One or more requirements below were satisfied by a self-declared alternate "
    "control rather than by the control the model describes. ASD treats meeting a "
    "control's objective by other means as effective, so these count towards the "
    "rating. They have NOT been independently verified, and they are not equivalent "
    "evidence to an implemented control. An assessor would test each one before "
    "accepting the rating that rests on it."
)

NOT_APPLICABLE_NOTE = (
    "Requirements marked not applicable were removed from the requirement set rather "
    "than failed, so each maturity level below shows the applicable base it was "
    "computed from. A rating drawn from a reduced base is a narrower claim than the "
    "same rating drawn from the full set. Each exclusion is self-declared and is "
    "listed with its stated reason."
)

SUPERSEDED_NOTE = (
    "A requirement above is unmet at a level below the one awarded. That is not a "
    "contradiction. Each maturity level is assessed against its own complete "
    "requirement set, and a higher level sometimes replaces a requirement with a "
    "stricter one rather than adding to it. The stricter replacement was met."
)


@dataclass(frozen=True)
class LevelGap:
    """What one maturity level is still missing for one strategy.

    `applicable_count` and `required_count` differ whenever something was
    declared not applicable, and both are printed so the reader can see the
    base the rating came from.
    """

    level: int
    required_count: int
    applicable_count: int
    not_applicable_count: int
    unmet: List[Tuple[str, str, str]]  # (criterion id, text, how it was answered)
    below_awarded: bool
    unawardable: bool

    @property
    def level_name(self):
        return LEVEL_NAMES[self.level]


@dataclass(frozen=True)
class Declaration:
    """A not_applicable or alternate_control answer, with its written reason."""

    criterion_id: str
    text: str
    answer: str
    justification: str


@dataclass(frozen=True)
class StrategySection:
    strategy_id: str
    name: str
    level: int
    gaps: List[LevelGap]
    bases: List[Tuple[int, int, int]]  # (level, applicable, required) for all 3 levels

    @property
    def level_name(self):
        return LEVEL_NAMES[self.level]

    @property
    def has_superseded_gap(self):
        return any(gap.below_awarded for gap in self.gaps)


@dataclass(frozen=True)
class ReportData:
    """Everything any format needs, computed once."""

    model_name: str
    version: str
    sourced_on: str
    control_set_age_days: int
    fingerprint: str
    organisation: str
    answered_on: str
    generated_on: str
    total_criteria: int
    unanswered_count: int
    sections: List[StrategySection]
    declarations: List[Declaration]

    @property
    def not_applicable_count(self):
        return sum(1 for d in self.declarations if d.answer == scoring.NOT_APPLICABLE)

    @property
    def alternate_control_count(self):
        return sum(1 for d in self.declarations if d.answer == scoring.ALTERNATE_CONTROL)

    @property
    def has_alternate_controls(self):
        return self.alternate_control_count > 0

    @property
    def has_exclusions(self):
        return self.not_applicable_count > 0

    @property
    def answered_count(self):
        return self.total_criteria - self.unanswered_count

    @property
    def age_phrase(self):
        days = self.control_set_age_days
        return f"{days} day{'' if days == 1 else 's'} ago"

    @property
    def coverage(self):
        """Answered, excluded and unanswered are three different things and are
        never collapsed into one figure."""
        text = f"{self.answered_count} of {self.total_criteria} criteria answered"
        extra = []
        if self.not_applicable_count:
            extra.append(f"{self.not_applicable_count} declared not applicable")
        if self.alternate_control_count:
            extra.append(f"{self.alternate_control_count} met by an alternate control")
        if self.unanswered_count:
            extra.append(f"{self.unanswered_count} unanswered, each counted as not met")
        return text + (f" ({'; '.join(extra)})" if extra else "")


def build(control_set, document, results, unanswered_ids, today=None):
    """Assemble the render-ready structure from a scored assessment."""
    from e8 import answers as answers_module

    today = today or date.today()
    sections, declarations = [], []

    for result in results:
        strategy = next(
            s for s in control_set["strategies"] if s["id"] == result.strategy_id
        )
        gaps = []
        for level in model.VALID_LEVELS:
            assessment = result.levels[level]
            if assessment.satisfied:
                continue
            gaps.append(LevelGap(
                level=level,
                required_count=assessment.required_count,
                applicable_count=assessment.applicable_count,
                not_applicable_count=len(assessment.not_applicable),
                unmet=[
                    (c.id, c.text, document["answers"].get(c.id, "unanswered"))
                    for c in assessment.unmet
                ],
                below_awarded=level < result.level,
                unawardable=assessment.unawardable,
            ))
        sections.append(StrategySection(
            strategy_id=result.strategy_id,
            name=result.strategy_name,
            level=result.level,
            gaps=gaps,
            bases=[(lv, result.levels[lv].applicable_count,
                    result.levels[lv].required_count) for lv in model.VALID_LEVELS],
        ))

    # Declarations in control-set order, so the audit trail reads like the model.
    for strategy in control_set["strategies"]:
        for criterion in strategy["criteria"]:
            answer = document["answers"].get(criterion["id"])
            if answer in scoring.REQUIRES_JUSTIFICATION:
                declarations.append(Declaration(
                    criterion_id=criterion["id"],
                    text=criterion["text"],
                    answer=answer,
                    justification=answers_module.justification(document, criterion["id"]),
                ))

    return ReportData(
        model_name=control_set["model"],
        version=control_set["version"],
        sourced_on=control_set["sourced_on"],
        control_set_age_days=model.age_days(control_set, today),
        fingerprint=answers_module.fingerprint(control_set),
        organisation=document.get("organisation") or "(not stated)",
        answered_on=document["answered_on"],
        generated_on=today.isoformat(),
        total_criteria=sum(len(s["criteria"]) for s in control_set["strategies"]),
        unanswered_count=len(unanswered_ids),
        sections=sections,
        declarations=declarations,
    )


ANSWER_LABELS = {
    scoring.NOT_APPLICABLE: "not applicable",
    scoring.ALTERNATE_CONTROL: "alternate control (self-declared, unverified)",
}


def _base_phrase(gap):
    """How a level's requirement base reads when something was excluded."""
    if gap.not_applicable_count:
        return (f"{len(gap.unmet)} of {gap.applicable_count} applicable requirements "
                f"not met ({gap.not_applicable_count} of {gap.required_count} declared "
                f"not applicable)")
    return f"{len(gap.unmet)} of {gap.required_count} requirements not met"


def _wrap(text, indent="", width=88):
    import textwrap
    return textwrap.fill(text, width, initial_indent=indent, subsequent_indent=indent)


def render_text(data):
    """Plain text, for a terminal. No markup, nothing to escape."""
    out = [
        f"{data.model_name}, {data.version}",
        f"Control set sourced {data.sourced_on} ({data.age_phrase}), "
        f"fingerprint {data.fingerprint}",
        f"Organisation: {data.organisation}",
        f"Answered: {data.answered_on}",
        f"Coverage: {data.coverage}",
        "",
        _wrap(DISCLAIMER),
        "",
        "RESULTS",
    ]

    width = max(len(s.name) for s in data.sections) + 4
    for section in data.sections:
        out.append(f"  {section.name.ljust(width)}{section.level_name}")
    out += ["", _wrap(NO_OVERALL, indent="  ")]

    if data.has_alternate_controls:
        out += ["", _wrap(ALTERNATE_CONTROL_WARNING, indent="  ")]
    if data.has_exclusions:
        out += ["", _wrap(NOT_APPLICABLE_NOTE, indent="  ")]
    out.append("")

    out.append("REQUIREMENT BASE")
    for section in data.sections:
        parts = ", ".join(
            f"ML{lv} {applicable}/{required}" for lv, applicable, required in section.bases
        )
        out.append(f"  {section.name.ljust(width)}{parts}")
    out += ["  (applicable requirements / requirements in the published model)", ""]

    if data.declarations:
        out.append("DECLARATIONS")
        out.append(_wrap(
            "Self-declared by the organisation. Each one changes the rating and none "
            "has been independently verified.", indent="  "))
        for d in data.declarations:
            out.append("")
            out.append(f"  [{d.criterion_id}] {ANSWER_LABELS[d.answer]}")
            out.append(_wrap(d.text, indent="      "))
            out.append(_wrap(f"Stated reason: {d.justification}", indent="      "))
        out.append("")

    out.append("GAPS")
    for section in data.sections:
        out += ["", f"{section.name}, awarded {section.level_name}"]
        if not section.gaps:
            out.append("  Every applicable requirement met at all three maturity levels.")
            continue

        for gap in section.gaps:
            if gap.unawardable:
                out.append(
                    f"  {gap.level_name}: not awarded, no applicable requirements "
                    f"(all {gap.required_count} declared not applicable). Nothing was "
                    f"demonstrated at this level, so it cannot be awarded."
                )
                continue
            header = f"  {gap.level_name}: {_base_phrase(gap)}"
            if gap.below_awarded:
                header += " (superseded at the level awarded, see note below)"
            out.append(header)
            for cid, text, answer in gap.unmet:
                out.append(f"    [{cid}] answered: {answer}")
                out.append(_wrap(text, indent="        "))

        if any(g.below_awarded for g in section.gaps):
            out += ["", _wrap("Note: " + SUPERSEDED_NOTE, indent="    ")]

    return "\n".join(out)


def render_markdown(data):
    """Markdown, for pasting into a ticket, a wiki or a pull request."""
    out = [
        f"# Essential Eight self-assessment: {data.organisation}",
        "",
        f"> **{DISCLAIMER}**",
        "",
        f"Assessed against {data.model_name}, {data.version}. Control set sourced "
        f"{data.sourced_on} ({data.age_phrase}), fingerprint `{data.fingerprint}`.",
        "",
        f"- Answered: {data.answered_on}",
        f"- Report generated: {data.generated_on}",
        f"- Coverage: {data.coverage}",
        "",
        "## Results",
        "",
        "| Mitigation strategy | Awarded | ML1 | ML2 | ML3 |",
        "|---|---|---|---|---|",
    ]
    for section in data.sections:
        bases = " | ".join(f"{a}/{r}" for _, a, r in section.bases)
        out.append(f"| {section.name} | {section.level_name} | {bases} |")
    out += ["", "Level columns show applicable requirements over requirements in the "
                "published model.", "", NO_OVERALL]

    if data.has_alternate_controls:
        out += ["", f"> **{ALTERNATE_CONTROL_WARNING}**"]
    if data.has_exclusions:
        out += ["", f"> {NOT_APPLICABLE_NOTE}"]

    if data.declarations:
        out += ["", "## Declarations", "",
                "Self-declared by the organisation. Each one changes the rating and "
                "none has been independently verified.", ""]
        for d in data.declarations:
            out.append(f"- **`{d.criterion_id}`, {ANSWER_LABELS[d.answer]}** {d.text}")
            out.append(f"  - Stated reason: {d.justification}")
        out.append("")

    out.append("## Gaps")

    for section in data.sections:
        out += ["", f"### {section.name}, awarded {section.level_name}", ""]
        if not section.gaps:
            out.append("Every applicable requirement met at all three maturity levels.")
            continue

        for gap in section.gaps:
            if gap.unawardable:
                out += [f"**{gap.level_name}: not awarded, no applicable requirements** "
                        f"(all {gap.required_count} declared not applicable). Nothing "
                        f"was demonstrated at this level, so it cannot be awarded.", ""]
                continue
            header = f"**{gap.level_name}: {_base_phrase(gap)}"
            header += " (superseded at the level awarded)**" if gap.below_awarded else "**"
            out += [header, ""]
            for cid, text, answer in gap.unmet:
                out.append(f"- `{cid}` (answered: {answer}) {text}")
            out.append("")

        if any(g.below_awarded for g in section.gaps):
            out += [f"> {SUPERSEDED_NOTE}", ""]

    return "\n".join(out).rstrip() + "\n"


CSS = """
:root { color-scheme: light; }
body {
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #1a1a1a; background: #fff; margin: 0; padding: 2.5rem 1.25rem;
}
main { max-width: 52rem; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 1rem; }
h2 { font-size: 1.2rem; margin: 2.5rem 0 0.75rem; padding-bottom: .35rem;
     border-bottom: 1px solid #d8d8d8; }
h3 { font-size: 1rem; margin: 1.75rem 0 .5rem; }
.disclaimer {
  border: 2px solid #8a1f11; background: #fdf3f2; color: #6d1a0e;
  padding: .85rem 1rem; border-radius: 4px; font-weight: 600; margin: 0 0 1.5rem;
}
.meta { color: #444; font-size: .92rem; margin: 0 0 1.5rem; }
.meta li { margin: .15rem 0; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #e2e2e2; }
th { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #555; }
.level { font-weight: 600; white-space: nowrap; }
.level-0 { color: #8a1f11; }
.level-1 { color: #8a5a11; }
.level-2 { color: #3d6b1f; }
.level-3 { color: #1f5c3d; }
.note { background: #f4f6f8; border-left: 3px solid #98a4b0; padding: .7rem .9rem;
        margin: 1rem 0; font-size: .92rem; color: #37414b; }
.gap-header { font-weight: 600; margin: 1rem 0 .5rem; }
.warn { background: #fdf6ec; border-left: 3px solid #b5761f; padding: .7rem .9rem;
        margin: 1rem 0; font-size: .92rem; color: #6b4611; }
.declaration { border-left: 3px solid #98a4b0; padding: .5rem .8rem; margin: .6rem 0;
               background: #f7f9fa; }
.declaration .tag { font-weight: 600; color: #37414b; }
.reason { color: #37414b; font-style: italic; margin-top: .3rem; }
.unawardable { color: #6d1a0e; }
ul.criteria { list-style: none; padding: 0; margin: 0; }
ul.criteria li { border-left: 3px solid #e0c4c0; padding: .5rem .8rem; margin: .5rem 0;
                 background: #fbfafa; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
.answer { color: #6d1a0e; font-weight: 600; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #d8d8d8;
         color: #555; font-size: .85rem; }
@media print {
  body { padding: 0; font-size: 11pt; }
  .disclaimer { border-color: #000; color: #000; background: #fff; }
  h2 { page-break-after: avoid; }
  ul.criteria li { page-break-inside: avoid; }
}
"""


def _esc(value):
    return html.escape(str(value), quote=True)


def render_html(data):
    """A single self-contained HTML file.

    Everything is inlined and there is no script: the PRD forbids network
    access at runtime, and a compliance report that pulls a font or a stylesheet
    from a CDN would both break that and leak the fact that it was opened.

    Every interpolated value is escaped. `organisation` and every justification
    come straight out of the answers file, which is untrusted input.
    """
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Essential Eight self-assessment: {_esc(data.organisation)}</title>",
        f"<style>{CSS}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>Essential Eight self-assessment: {_esc(data.organisation)}</h1>",
        f'<p class="disclaimer">{_esc(DISCLAIMER)}</p>',
        '<ul class="meta">',
        f"<li>Assessed against {_esc(data.model_name)}, {_esc(data.version)}</li>",
        f"<li>Control set sourced {_esc(data.sourced_on)} ({_esc(data.age_phrase)}), "
        f"fingerprint <code>{_esc(data.fingerprint)}</code></li>",
        f"<li>Answered: {_esc(data.answered_on)}</li>",
        f"<li>Report generated: {_esc(data.generated_on)}</li>",
        f"<li>Coverage: {_esc(data.coverage)}</li>",
        "</ul>",
        "<h2>Results</h2>",
        "<table>",
        "<thead><tr><th>Mitigation strategy</th><th>Awarded</th>"
        "<th>ML1</th><th>ML2</th><th>ML3</th></tr></thead>",
        "<tbody>",
    ]
    for section in data.sections:
        cells = "".join(f"<td>{a}/{r}</td>" for _, a, r in section.bases)
        parts.append(
            f"<tr><td>{_esc(section.name)}</td>"
            f'<td class="level level-{section.level}">{_esc(section.level_name)}</td>'
            f"{cells}</tr>"
        )
    parts += [
        "</tbody>",
        "</table>",
        '<p class="meta">Level columns show applicable requirements over requirements '
        "in the published model.</p>",
        f'<p class="note">{_esc(NO_OVERALL)}</p>',
    ]

    if data.has_alternate_controls:
        parts.append(f'<p class="warn">{_esc(ALTERNATE_CONTROL_WARNING)}</p>')
    if data.has_exclusions:
        parts.append(f'<p class="note">{_esc(NOT_APPLICABLE_NOTE)}</p>')

    if data.declarations:
        parts += [
            "<h2>Declarations</h2>",
            '<p class="meta">Self-declared by the organisation. Each one changes the '
            "rating and none has been independently verified.</p>",
        ]
        for d in data.declarations:
            parts.append(
                f'<div class="declaration"><span class="tag"><code>'
                f"{_esc(d.criterion_id)}</code>, {_esc(ANSWER_LABELS[d.answer])}</span>"
                f"<br>{_esc(d.text)}"
                f'<div class="reason">Stated reason: {_esc(d.justification)}</div></div>'
            )

    parts.append("<h2>Gaps</h2>")

    for section in data.sections:
        parts.append(
            f"<h3>{_esc(section.name)}, awarded {_esc(section.level_name)}</h3>"
        )
        if not section.gaps:
            parts.append(
                "<p>Every applicable requirement met at all three maturity levels.</p>")
            continue

        for gap in section.gaps:
            if gap.unawardable:
                parts.append(
                    f'<p class="gap-header unawardable">{_esc(gap.level_name)}: not '
                    f"awarded, no applicable requirements (all {gap.required_count} "
                    f"declared not applicable). Nothing was demonstrated at this level, "
                    f"so it cannot be awarded.</p>"
                )
                continue
            header = f"{_esc(gap.level_name)}: {_esc(_base_phrase(gap))}"
            if gap.below_awarded:
                header += " (superseded at the level awarded)"
            parts.append(f'<p class="gap-header">{header}</p>')
            parts.append('<ul class="criteria">')
            for cid, text, answer in gap.unmet:
                parts.append(
                    f"<li><code>{_esc(cid)}</code> "
                    f'<span class="answer">answered: {_esc(answer)}</span><br>'
                    f"{_esc(text)}</li>"
                )
            parts.append("</ul>")

        if any(g.below_awarded for g in section.gaps):
            parts.append(f'<p class="note">{_esc(SUPERSEDED_NOTE)}</p>')

    parts += [
        f"<footer>{_esc(DISCLAIMER)}</footer>",
        "</main>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


RENDERERS = {
    "text": render_text,
    "md": render_markdown,
    "html": render_html,
}
