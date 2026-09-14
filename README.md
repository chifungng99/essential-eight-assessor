# Essential Eight Assessor

A command line self-assessment tool for the Australian Signals Directorate's
**Essential Eight Maturity Model**. You answer a structured set of questions about
your environment, and it computes a maturity level per mitigation strategy and
writes a gap report naming every requirement that was not met, grouped by the
maturity level it belongs to. It reports gaps; it does not rank them or tell you
which to remediate first.

> **This is an indicative self-assessment, not a certified ASD assessment.**
> It has no affiliation with, and no endorsement from, the Australian Signals
> Directorate or the Australian Cyber Security Centre. Its output is a starting
> point for a conversation, not evidence of compliance.

**Status: v1 complete.** The control set, the scoring engine, the assessment outcomes including `not_applicable` and `alternate_control` with mandatory justifications, the CLI and report rendering are all built and tested, and the tool runs an assessment end to end in plain text, Markdown and HTML. The human review gate described below has been completed: the extracted criteria were checked against Appendices A to C of the published model, and the source edition was verified against ASD's published page.

---

## The decision this project is built around

In June 2026 ASD opened a consultation on evolving the Essential Eight into a new
**"Essentials"** series, organised by domain: enterprise IT first, then operational
technology and cloud. The ACSC's head of cyber security resilience has since been
reported as saying the Essential Eight will begin to be deprecated around mid-2027
and retired around mid-2028.

So this tool is being built against a framework with a publicly signalled end date.
That is a deliberate choice, and it shapes the architecture:

**The control set is versioned data, not code.** Criteria live in a JSON file that
carries the model's version and publication date. The scoring engine knows how to
evaluate criteria; it does not know anything about the Essential Eight specifically.
When an Essentials chapter is published, supporting it is a new data file and a new
set of fixtures, not a rewrite.

**The tool refuses to rate against a control set it cannot verify is current.** The
criteria file carries a `sourced_on` date. Past a configured age, loading it raises
rather than returning, so the tool stops instead of producing a maturity rating from
a stale model. There is no flag on `assess` to wave that through. A tool that returns
"Maturity Level Two" against superseded criteria is worse than one that stops,
because nobody checks a number that looks plausible.

## Running it

Python 3.9 or later. No dependencies, nothing to install.

```
python3 -m unittest discover -s tests -v     # 149 tests
python3 tools/review_controls.py --level 1   # print the control set for review
```

## Doing an assessment

```
python3 -m e8 init --organisation "Your Org Pty Ltd"   # writes my.assessment.json
python3 -m e8 assess my.assessment.json
python3 -m e8 assess my.assessment.json --format html --out reports/assessment.html
```

A completed assessment, and any report generated from it, is a map of where an
organisation is weakest. Treat both as sensitive. `.gitignore` already covers
`assessments/`, `*.assessment.json` and `reports/`, `init` warns when you write to a
filename none of those patterns cover, and nothing is ever transmitted anywhere: the
tool makes no network calls at runtime.

`--format` takes `text`, `md` or `html`. Two worked examples are committed, rendered in all three formats: read
[`examples/harbourline-freight.md`](examples/harbourline-freight.md) for a
straightforward assessment, and
[`examples/redgum-plumbing.md`](examples/redgum-plumbing.md) for a small business with
no internet-facing servers and no online customer services, which shows exclusions,
an alternate control and the declarations section. Those files are also the golden
files the tests compare against, so they cannot drift from the real output.

`init` writes one entry per criterion, every one set to `unknown`. Read the requirements
alongside with `review_controls.py` and answer each one:

| Answer | Means | Effect on the rating |
|---|---|---|
| `met` | Implemented as written | Satisfies the requirement |
| `alternate_control` | The objective is met by a different control | Satisfies the requirement |
| `not_met` | Not implemented, or not adequately | Fails the requirement |
| `not_applicable` | The asset or environment does not exist here | Removes the requirement from the set |
| `unknown` | Not assessed, or no visibility | Fails the requirement |

`unknown` is a real answer and scores as not met, which is the point: making the honest
answer available is what keeps the result honest. It needs no justification, because
making the honest answer expensive is how a tool fills up with confident guesses.

`not_applicable` and `alternate_control` do need one, in a `justifications` block keyed
by criterion id. They are the only two answers that change a rating without anything
being implemented, so each is printed verbatim in the report and labelled there as
self-declared. An alternate control counts towards the rating exactly as ASD's
assessment process guide says it should, and the report states plainly that it has not
been independently verified, because it is not equivalent evidence to an implemented
control.

Two guard rails follow from that. A maturity level whose requirements were all declared
not applicable is never awarded, since nothing was demonstrated. And an answers file
that marks an entire mitigation strategy not applicable is refused outright, because
ASD does not permit a whole strategy to be scoped out.

Every report shows the applicable base each level was computed from, for example
`ML1 5/8`. A rating drawn from five of eight requirements is a narrower claim than the
same rating drawn from eight of eight, and a reader has to be able to tell which one
they are holding.

Every format carries the disclaimer and names the criteria behind the rating, and the
HTML report is a single self-contained file with no scripts and no external references,
because a compliance report that pulls a font from a CDN both breaks the offline
constraint and leaks the fact that it was opened.

There are three things the CLI
deliberately will not do. It has no `--allow-stale`, because refusing to rate against a
superseded model is the guarantee the tool is built on. It has no `--fail-under` for use
as a CI gate, because that is the affordance that turns an indicative self-assessment
into something treated as a compliance control. And it gives no single overall figure,
because three of the eight mitigation strategies are in scope and a combined number
would be read as an Essential Eight rating.

## Rebuilding the control set

The control set is **generated from ASD's published PDF, never hand-typed**.
Transcribing 114 requirements by hand would introduce errors no test could detect:
the tool would score against subtly wrong criteria and return numbers that looked
entirely reasonable.

```
pdftotext -layout "Essential Eight maturity model (November 2023).pdf" e8.txt
python3 tools/extract_controls.py e8.txt controls/e8-2023-11.json
```

The PDF itself is deliberately **not** committed here. Its text is CC BY 4.0, but the
Commonwealth Coat of Arms and the ASD logo it contains are explicitly excluded from
that licence, so redistributing the file would redistribute those marks. Download it
from the [Essential Eight Maturity Model page](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight/essential-eight-maturity-model).

## How the control set is structured

Each maturity level in the published model restates its **complete** requirement set
rather than listing only what is new, and a higher level sometimes **replaces** a
requirement with a stricter one. At Maturity Level Three the blanket "within two
weeks" patching requirement is gone, replaced by 48 hours for critical
vulnerabilities and two weeks for non-critical ones.

Two consequences run through the whole design:

**A level's requirement set is exactly the criteria tagged with that level.** Not
that level plus everything below, which would resurrect requirements the model has
deliberately superseded. Three requirements in this control set apply at lower levels
and not at Level Three, and a test asserts they exist so the rule cannot be
quietly changed later.

**Each distinct requirement is stored once, tagged with the levels that require it.**
Per-level storage would mean 114 entries for three strategies, and would ask a user
the identical asset-discovery question three times. Deduplicated it is 55.

| | Unique | ML1 | ML2 | ML3 |
|---|---|---|---|---|
| Patch applications | 14 | 9 | 11 | 13 |
| Patch operating systems | 17 | 8 | 8 | 16 |
| Multi-factor authentication | 24 | 7 | 19 | 23 |

Every criterion carries a SHA-256 of its own text. Editing a requirement by hand
without regenerating fails validation, because hand-editing a control text is the
most dangerous change anyone can make to this repository.

## The limit of the tests

The suite covers the loader, the validator, the staleness refusal, the scoring
engine including not-applicable handling and alternate controls, answers file
validation, all three report formats and the CLI, across 149 tests. It **cannot**
prove the criteria were extracted correctly. It has no access to the source document
and no judgement. If a requirement were truncated, every one of those tests would
still pass.

That is what `tools/review_controls.py` is for, and why the project has a human
review gate: the output is read side by side with Appendices A to C before any
rating is trusted. Knowing which risks your tests do not cover is part of the design,
not an admission.

## Scope

Version one covers three mitigation strategies in full, across Maturity Levels One
to Three:

- Patch applications
- Patch operating systems
- Multi-factor authentication

Three strategies covered properly is more useful, and more honest, than eight
covered shallowly. The remaining five are additive once the engine is proven.

## Source material and attribution

Essential Eight Maturity Model (November 2023), © Commonwealth of Australia 2023,
Australian Signals Directorate, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The Commonwealth Coat of Arms and the ASD logo are excluded from that licence and are
not reproduced here.

Criteria are stored **verbatim**. An earlier draft of this project planned to
paraphrase them pending the licence position. Having confirmed CC BY 4.0, verbatim is
both permitted and correct: the wording is where a compliance requirement lives, and
"within 48 hours" rather than "promptly" is the entire substance of the control.

Always read the official model. This tool is not a substitute for it.

## Licence

MIT, see [LICENSE](LICENSE). The licence covers this tool's own code and data
structures. It does not and cannot extend to ASD's published material.
