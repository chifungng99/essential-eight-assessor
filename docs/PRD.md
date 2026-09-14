# PRD: Essential Eight Assessor

**Status:** stages 0 to 4.5 built and tested. Stage 5, publication, is gated on the
source verification in section 11 rather than on code.
**Written:** 11-09-2026
**Revised:** 11-09-2026 after reading the official ASD source documents
**Revised:** 14-09-2026 for the stage 4.5 outcome model and the release review
**Author:** Jackson Ng

---

## 1. Problem

An organisation that wants to know its Essential Eight maturity has three options
today: pay a consultancy, buy a compliance platform, or keep a spreadsheet.

The spreadsheet is what most small organisations actually do, and it has three
failure modes. It is unversioned, so nobody can tell which revision of the maturity
model it was built against. It is opaque, so the number in the summary cell cannot
be traced back to the specific criteria that produced it. And it is generous,
because a blank cell tends to get read as a pass.

The narrower problem this tool solves: **turn a structured set of honest answers
into a defensible maturity level, and show the working.**

Secondary purpose, stated plainly because it shapes decisions: this is a portfolio
project. It must demonstrate judgement, not just function.

## 2. Success criteria

Measurable, and each one is a test:

1. Given a complete answer set, returns a maturity level of 0 to 3 for each
   in-scope mitigation strategy.
2. Level assignment follows ASD's rule: the awarded level is the **highest level
   whose own applicable requirement set is fully satisfied.** Partial achievement of
   a level awards the level below. "Own" means the criteria tagged with that level,
   never that level plus everything below. "Applicable" means excluding anything
   answered `not_applicable`, which stage 4.5 added; a level with no applicable
   requirements left is never awarded, because nothing was demonstrated. Proven by tests, including the case where a single
   Maturity Level One criterion fails and the result is Zero.

   This is a correction to the first draft, which said "that level and all levels
   below it". Reading the published model shows each appendix restates the full
   requirement set for its level rather than listing only the additions, and higher
   levels sometimes tighten the wording of a requirement rather than adding a new
   one. Evaluating lower levels as well is therefore redundant, and would be wrong
   wherever a stricter requirement supersedes a weaker one.
3. Every rating is traceable. The report names the specific criteria that were not
   met and which level each belongs to. No summary number appears without the
   criteria behind it.
4. An unanswered or unknown criterion is treated as **not met**. Never as met. A
   criterion answered `not_applicable` is removed from the requirement set rather
   than failed, and must carry a written justification.
5. The tool refuses to produce a rating when the control set is older than its
   configured maximum age, rather than rating against superseded criteria.
6. Every branch of the scoring logic is covered by a test, including Maturity Level
   Zero and every partial-level combination.
7. Runs offline, with no network access at runtime.
8. Contains no verbatim ASD text unless and until the licence position is confirmed.

## 3. Scope

Version one:

- Three mitigation strategies, complete across Maturity Levels One to Three:
  Patch applications, Patch operating systems, Multi-factor authentication
- A versioned control set as a JSON data file
- A CLI: answers file in, maturity results and a gap report out
- Report output in plain text, Markdown and HTML
- Example fixtures for two fictional organisations
- A test suite

## 4. Out of scope

Deliberately, and each for a reason:

- **The other five strategies.** Additive once the engine is proven. Three done
  properly beats eight done shallowly, and eight shallow strategies is the most
  likely way this project ends up abandoned.
- **The Essentials series.** No chapter has been published. There is nothing to
  encode. The architecture makes it a new data file when there is.
- **Scanning the actual environment.** This is a questionnaire, not a scanner. It
  does not connect to Intune, Active Directory or anything else. It reports what
  the organisation says about itself, and the report says so.
- **Evidence storage.** The tool records answers, not the evidence behind them.
- **Any claim of certification or compliance.** The output is indicative.
- **Multi-user, multi-org, a database, a web UI, authentication.**

## 5. Constraints

- **ASD text is reproduced verbatim, under CC BY 4.0, with attribution.** Resolved:
  the maturity model states it is (c) Commonwealth of Australia 2023 and licensed
  Creative Commons Attribution 4.0 International, excluding the Coat of Arms and the
  ASD logo. Verbatim criteria are therefore permitted and preferable to paraphrase,
  because a compliance tool that quietly reworded the requirements would be worse
  than useless. Neither the Coat of Arms nor the ASD logo goes anywhere near this
  repository.
- **Python 3.9+, standard library only** for the core. A reviewer should be able to
  read the whole thing without installing anything. Test tooling may be an exception.
- **The tool never writes to the control set.** Criteria are read-only input.
- **No network calls at runtime.** A compliance tool that phones home is a bad look
  and an unnecessary attack surface.
- **Completed assessments never enter version control.** Already enforced in
  `.gitignore`, because a finished self-assessment is a map of where an organisation
  is weakest.

## 6. Architecture

```
controls/e8-2023-11.json     versioned control set (data, not code)
e8/model.py                  load and validate a control set, staleness check
e8/answers.py                load and validate an answers file, blank templates
e8/scoring.py                pure functions: answers + control set -> results
e8/report.py                 results -> plain text / Markdown / HTML
e8/cli.py                    argparse entry point
tests/                       unit tests
examples/                    fictional organisation fixtures
```

The organising principle: **rules in tested code, judgement in the human's answers.** `scoring.py` knows how to evaluate criteria. It
knows nothing about the Essential Eight. It never infers, never estimates, and never
fills a gap on the user's behalf.

## 7. Data

**Control set** (`controls/e8-2023-11.json`):

```
version        "November 2023"
sourced_on     ISO date the criteria were transcribed from the official model
source_url     link to the published model
licence        "CC BY 4.0", attribution string
max_age_days   how stale the set may be before the tool refuses to rate
strategies[]   id, name
  criteria[]   id, text (verbatim), required_at_levels [1,2,3]
```

**Criteria are canonical, not per-level.** The published model restates shared
requirements in every appendix that needs them: the same asset discovery requirement
appears identically at Maturity Levels One, Two and Three. Storing them per level
would mean roughly 114 entries across the three in-scope strategies, and would make
a user answer the identical question three times. Instead each distinct requirement
is stored once and tagged with the levels that require it. The user answers once,
and the engine evaluates each level's set by selecting on that tag.

**Answers** (user-supplied, gitignored):

```
control_set_version       must match the control set, or the tool refuses
control_set_fingerprint   optional; must match the loaded control set when present
organisation              a label only, no identifying detail required
answered_on               ISO date
answers{}                 criterion_id -> one of the five outcomes below
justifications{}          criterion_id -> written reason, required for
                          not_applicable and alternate_control
```

The five outcomes, and what each does to a level's requirement set:

| Outcome | Effect |
|---|---|
| `met` | Satisfies the requirement |
| `alternate_control` | Satisfies the requirement, by other means |
| `not_met` | Fails the requirement |
| `not_applicable` | Removes the requirement from the set |
| `unknown` | Fails the requirement |

An unanswered criterion fails, exactly as `unknown` does.

`unknown` is a first-class value and scores as not met. Making the honest answer
available is what keeps the result honest, which is also why it needs no
justification: making the honest answer expensive is how a tool fills with guesses.

`not_applicable` and `alternate_control` do need one. A justification must be text
containing something other than whitespace; null, a number, a boolean or a list is
rejected. There is no minimum length, because the control is that every justification
is printed verbatim in the report where a reader can judge it.

## 8. Security

- Assessment answers are sensitive. Gitignored, never logged, never transmitted.
- The answers file is untrusted input. Schema validated before use.
- No secrets of any kind. Nothing to store.
- No network at runtime.
- Every generated report carries the indicative-not-certified disclaimer, so a
  report that escapes its context still says what it is.

## 9. Testing

Standard unit tests cover loading, validation, staleness refusal and report
rendering. The scoring engine needs more than that, because **its failure mode is
a plausible wrong answer.** A tool that returns Maturity Level Two when the truth is
One looks completely normal.

Three layers:

1. **Worked examples.** Hand-computed answer sets with a known correct result,
   including all-met, one-ML1-criterion-failed (expect Zero), ML1 complete but one
   ML2 criterion failed (expect One), and an all-unknown set (expect Zero).
2. **Invariants.** Properties that must hold for every possible input. Generate
   random answer sets, flip one answer, assert the property. This catches whole
   classes of logic error that example-based tests miss.

   Stage 4.5 replaced the single monotonicity property with three, because
   `not_applicable` removes a requirement rather than failing it and so CAN raise a
   level without anything being implemented:

   - changing an answer from satisfying (`met`, `alternate_control`) to failing
     (`not_met`, `unknown`) can never raise the awarded level
   - changing an answer from failing to `not_applicable` can never lower it
   - `met` and `alternate_control` are scoring-equivalent, so swapping one for the
     other never changes the level

   The second is the formal statement of why `not_applicable` must be justified in
   writing and disclosed in every report: it is the only value in the system that
   improves a rating without improving security.
3. **A human gate. Completed.** Tests prove the engine implements the rules. They
   cannot prove the criteria were transcribed correctly, so no rating was to be
   trusted until a person had read `e8-2023-11.json` against the official model.
   Jackson has now done that review against Appendices A to C. He holds the ISO 27001
   Lead Auditor credential; this is the part of the project where that matters. The
   gate remains in the process: any future regeneration of the control set has to
   pass it again.

## 10. Plan

| Stage | Deliverable | Gate |
|---|---|---|
| 0 | Obtain the official maturity model | **Done.** November 2023 model and October 2024 assessment process guide supplied |
| 1 | Control set JSON for three strategies, schema validation, tests | **Built, 28 tests passing. Review gate passed:** Jackson checked the extracted criteria against Appendices A to C |
| 2 | Scoring engine, worked-example tests, invariant tests | **Built, 11 new tests passing (39 total).** Correct relative to the criteria in the control set, which have since passed the stage 1 review |
| 3 | CLI and answers file handling | **Built, 42 new tests passing (81 total).** Runs end to end on `examples/harbourline-freight.json` |
| 4 | Markdown and HTML report rendering | **Built, 25 new tests passing (106 total).** Golden files committed in `examples/`, regenerated by `tools/update_examples.py` |
| 4.5 | Not applicable and alternate control outcomes | **Built, 39 new tests passing. 149 total after the release-review fix to justification validation.** Control set untouched, hash and fingerprint unchanged |
| 5 | Example fixtures, README completed, repo made public | **Release gates passed.** Source edition verified against ASD's published page, criteria reviewed against Appendices A to C, final read-through for leaked data done. Publication is the remaining step |

## 11. Open questions

1. ~~The criteria themselves.~~ **Partly resolved. One check remains open.** Two
   things have to be kept apart here, and the first draft of this line ran them
   together.

   **The version of the PDF this project used.** Settled. The supplied file is the
   Essential Eight Maturity Model (November 2023), and its own first page reads
   "First published: June 2017, Last updated: November 2023". The Essential Eight
   Assessment Process Guide (October 2024) was supplied alongside it. The control
   set records that version, the date it was transcribed, and a fingerprint of the
   criteria themselves.

   **Whether November 2023 is still the current edition ASD publishes.** Open, and
   it is a manual check. It has NOT been verified against the live cyber.gov.au
   page, because that site blocks automated fetching and no attempt was made to
   work around it. Everything known here is indirect: no later maturity model
   edition appears in that site's search index, and the documents published since
   (the ISM mapping of October 2024 and the FAQ of April 2024) reference the
   November 2023 model rather than replacing it. That was supporting evidence, not
   confirmation, so the check stayed open until a person made it. **Jackson has now
   verified this against ASD's published page, and November 2023 is the current
   edition.** The `sourced_on` and `max_age_days` fields exist so that the answer
   stops being trusted on its own after 180 days rather than silently ageing.

   Separately, the extracted criteria were re-extracted by a second, independent
   parser using a different library and different structural signals, and matched
   all 114 level-tagged requirement instances with no discrepancies. That is
   corroboration between two parsers reading the same document. It does not
   establish that the document is current, and it does not replace the human review
   gate in section 9.
2. ~~Copyright.~~ **Resolved.** CC BY 4.0, attribution required, Coat of Arms and
   ASD logo excluded.
3. ~~`max_age_days` default.~~ **Resolved: 180.**
4. ~~Not applicable.~~ **Reopened and re-resolved in stage 4.5: now offered, with
   a mandatory written justification.** The original answer conflated two different
   things. Uncertainty and inapplicability are not the same, and ASD's own assessment
   process guide (October 2024, page 2) lists them as separate outcomes: "No visibility"
   and "Not applicable: the control does not apply to the system or environment".
   Without `not_applicable`, 25 of the 55 criteria, which are conditional on owning
   internet-facing servers, online customer services, data repositories, drivers or
   firmware, were failed against organisations that do not own them. A small business
   with everything implemented scored Maturity Level Zero for two of three strategies.
   That is a plausible wrong answer, which section 9 names as this tool's most
   dangerous failure mode. Same guide, same page: "Alternate control: the organisation
   is effectively meeting the control's objective through an alternate control" is an
   effective outcome, so that is offered too, scored as met and labelled in every
   report as self-declared and unverified.
5. ~~Test runner.~~ **Resolved: stdlib `unittest`, not pytest.** Changed from the
   original recommendation. The build environment has no package index, and a
   compliance tool whose own test suite needs one is a tool nobody will verify.
   `python3 -m unittest discover -s tests`, zero dependencies.

## 12. Risks and assumptions

| Risk | Mitigation |
|---|---|
| **Criteria transcribed wrong.** The entire tool is then confidently wrong, and no test can detect it | The stage 1 human gate. Jackson reviews against the official model. This is the single largest risk and it is not solvable by code |
| The framework is retired from ~mid-2027 | Control set is versioned data. The README states the position rather than hiding it |
| Someone treats the output as compliance evidence | Disclaimer in the README and in every generated report, in all three formats, so a report that escapes its context still says what it is. `init` output does not carry it; nothing is rated at that point |
| Scope creep to all eight strategies | Named in Out of Scope. Revisit only after stage 5 ships |
| An assessment file gets committed | `.gitignore` written before any such file can exist |

**Assumption:** the November 2023 model is still current. The supplied PDF is the
November 2023 edition and no later edition has been published, but ASD's consultation
on the Essentials series closed in July 2026 and a successor may appear during the
build. The `sourced_on` and `max_age_days` fields exist precisely so that this
assumption fails loudly rather than silently.

---

## 13. Where this is up to

**Stage 1 complete.** Control set built from the official PDF, 55 unique criteria
across three strategies, loader and validator with 28 passing tests.

**The one human step, now done.** Jackson read `tools/review_controls.py` output
against Appendices A to C. No test in this repository has read the source document
or has any judgement about what the requirements say, so this gate was the only thing
standing between an extraction bug and a tool that rates confidently against wrong
criteria. It was later corroborated by a second, independent extraction of the same
PDF, which matched all 114 level-tagged requirement instances.

**Stage 2 complete.** `e8/scoring.py` implements the rule from section 2: each maturity
level is evaluated against its own complete requirement set via
`model.criteria_for_level`, never that level plus everything below, and the awarded
level is the highest one fully met. Eleven new tests (39 total): worked examples for
each of Levels Zero through Three, a test proving Level Three is reachable while a
requirement Level Three has superseded stays unmet, and a monotonicity invariant,
run against 300 random answer sets over the real control set, proving that flipping
any single "met" answer to "not_met" or "unknown" can never raise the level it
belongs to.

This does not touch the stage 1 gate. The scorer is proven correct **relative to
the criteria in `e8-2023-11.json`**; it has no way to know if a criterion was
transcribed wrong, so a rating is still only as trustworthy as that review.

**Stage 3 complete.** `python3 -m e8 init` writes a blank answers file, one entry per
criterion set to `unknown`; `python3 -m e8 assess` validates it, scores it and prints
the rating with every unmet criterion named and the level it belongs to. Runs end to
end on `examples/harbourline-freight.json`, a fictional organisation built to land on
Levels One, Zero and Two across the three strategies so the output exercises a real
mix rather than a uniform pass.

Three decisions made during stage 3 that are not in the sections above:

- **`e8/answers.py` was added to the architecture in section 6.** Answers file
  validation is untrusted-input handling, which is a different concern from argument
  parsing, and putting it in `cli.py` would have made it untestable without going
  through argparse.
- **The answers file carries an optional `control_set_fingerprint`.** The version
  string alone is too coarse: the criteria are extracted from a PDF and that extraction
  is still subject to the stage 1 review, so the same "November 2023" control set can
  legitimately be regenerated with corrected criteria. The fingerprint covers each
  criterion's id, text digest and required levels, so answers collected against the
  earlier file are refused rather than silently scored against the corrected one. It is
  optional, so a hand-written file following section 7's schema is still valid.
- **Three affordances were deliberately left out:** `--allow-stale` on `assess`,
  `--fail-under` as a CI gate, and any single overall maturity figure. Each is
  reasoned in the `e8/cli.py` docstring.

**Stage 4 complete.** `e8/report.py` renders plain text, Markdown and HTML, selected
with `--format` and written with `--out`. The plain-text renderer moved here from
`cli.py`, so rendering has one home and `cli.py` is orchestration only.

Three decisions worth recording:

- **All three formats are built from one intermediate structure** (`report.build`)
  rather than three renderers walking the results independently. Independent renderers
  drift: someone adds the coverage figure to the HTML, forgets the Markdown, and two
  reports of the same assessment quietly disagree. The tests assert the shared
  guarantees by iterating the renderer registry, so a fourth format added later is
  covered by them the moment it is registered.
- **The golden files live in `examples/`, not `tests/`.** They do double duty: a reader
  sees real output without running anything, and the tests prove the committed examples
  match what the code produces. `tools/update_examples.py` regenerates them, and the
  dates are pinned to the fixture's own `answered_on` rather than the clock, because a
  golden file that changes daily is one people learn to ignore.
- **`--out` overwrites without asking, unlike `init`.** A report is regenerable from the
  answers file; a completed assessment is not. Refusing in both places would teach
  people to pass `--force` reflexively, which is how a real refusal stops being read.

**Stage 4.5 complete.** The assessment vocabulary went from three values to five.

`not_applicable` removes a requirement from a level's set rather than failing it.
`alternate_control` satisfies a requirement by other means and scores as met. Both
require a written justification, both are printed verbatim in every report format under
a Declarations heading, and alternate controls are labelled self-declared and
unverified wherever they appear, so a reader cannot mistake one for an implemented
control. `unknown` deliberately needs no justification.

Three guard rails stop `not_applicable` becoming a free pass. A level whose applicable
set is empty is never awarded, because "all of nothing is met" is vacuously true.
An answers file that marks an entire mitigation strategy not applicable is refused at
validation, citing ASD's position that a whole strategy cannot be scoped out. And every
level reports the applicable base it was computed from, so a rating drawn from three of
eight requirements is visibly a narrower claim than one drawn from eight of eight. No
minimum-coverage threshold was introduced: disclosure was preferred to an arbitrary
constant that would have to be defended.

The monotonicity invariant needed restating, because `not_applicable` is the one answer
that can raise a level without anything being implemented. It is now three properties:
satisfying to failing never raises a level; failing to not_applicable never lowers one;
and met and alternate_control are scoring-equivalent. The second is the formal statement
of why the justification and the disclosure are mandatory rather than optional.

The control set was not touched. `controls/e8-2023-11.json` is byte identical, and
answers files written before this stage still validate and score identically.

**Stage 5: gates passed, publication remaining.** The stage 1 review is complete, the
source edition is verified against ASD's published page, and a release audit confirmed
the control set is byte identical, no source material or assessment data has ever been
committed, and the working tree holds nothing unintended. What is left is the act of
publishing.

**Run everything:**

```
python3 -m unittest discover -s tests -v
python3 tools/review_controls.py --level 1
```
