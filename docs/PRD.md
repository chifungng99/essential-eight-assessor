# PRD: Essential Eight Assessor

**Status:** draft, awaiting sign-off
**Written:** 11-09-2026
**Author:** Jackson Ng, with Claude

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
   at which every criterion of that level and all levels below it is met.** Partial
   achievement of a level awards the level below. Proven by tests, including the
   case where a single Maturity Level One criterion fails and the result is Zero.
3. Every rating is traceable. The report names the specific criteria that were not
   met and which level each belongs to. No summary number appears without the
   criteria behind it.
4. An unanswered or unknown criterion is treated as **not met**. Never as met.
5. The tool refuses to produce a rating when the control set is older than its
   configured maximum age, rather than rating against superseded criteria.
6. Every branch of the scoring logic is covered by a test, including Maturity Level
   Zero and every partial-level combination.
7. Runs offline, with no network access at runtime.
8. Contains no verbatim ASD text unless and until the licence position is confirmed.

## 3. Scope

Version one:

- Three mitigation strategies, complete across Maturity Levels One to Three:
  Patch Applications, Patch Operating Systems, Multi-factor Authentication
- A versioned control set as a JSON data file
- A CLI: answers file in, maturity results and a gap report out
- Report output in Markdown and HTML
- Example fixtures for a fictional organisation
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

- **No verbatim ASD text** until the copyright position is confirmed. Criteria are
  stored as paraphrase plus official identifier plus source link.
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
e8/scoring.py                pure functions: answers + control set -> results
e8/report.py                 results -> Markdown / HTML
e8/cli.py                    argparse entry point
tests/                       unit tests
examples/                    fictional organisation fixtures
```

The organising principle, carried over from Mission Control: **rules in tested code,
judgement in the human's answers.** `scoring.py` knows how to evaluate criteria. It
knows nothing about the Essential Eight. It never infers, never estimates, and never
fills a gap on the user's behalf.

## 7. Data

**Control set** (`controls/e8-2023-11.json`):

```
version        "November 2023"
sourced_on     ISO date the criteria were transcribed from the official model
source_url     link to the published model
max_age_days   how stale the set may be before the tool refuses to rate
strategies[]   id, name, official_ref
  levels{1,2,3}
    criteria[]   id, requirement (paraphrase), question, official_ref
```

**Answers** (user-supplied, gitignored):

```
control_set_version   must match the control set, or the tool refuses
organisation          a label only, no identifying detail required
answered_on           ISO date
answers{}             criterion_id -> "met" | "not_met" | "unknown"
```

`unknown` is a first-class value and scores as not met. Making the honest answer
available is what keeps the result honest.

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
2. **Invariants.** Properties that must hold for every possible input. The strongest
   is monotonicity: **changing any answer from met to not_met can never increase the
   awarded maturity level.** Generate random answer sets, flip answers, assert the
   level never goes up. This catches whole classes of logic error that example-based
   tests miss.
3. **A human gate.** Tests prove the engine implements the rules. They cannot prove
   the criteria were transcribed correctly. Jackson reviews `e8-2023-11.json` against
   the official model line by line before any rating is trusted. He holds the ISO
   27001 Lead Auditor credential; this is the part of the project where that matters.

## 10. Plan

| Stage | Deliverable | Gate |
|---|---|---|
| 0 | Obtain the official maturity model | **Blocked, see below** |
| 1 | Control set JSON for three strategies, schema validation, tests | Jackson reviews criteria against the official model |
| 2 | Scoring engine, worked-example tests, invariant tests | All tests pass |
| 3 | CLI and answers file handling | Runs end to end on a fixture |
| 4 | Markdown and HTML report rendering | Golden-file tests |
| 5 | Example fixtures, README completed, repo made public | Final read-through for leaked data |

## 11. Open questions

1. **The criteria themselves.** Claude's research tool is blocked from cyber.gov.au,
   so it cannot read the official model. **Jackson must supply it**, by downloading
   the PDF or pasting the criteria. This is stage 0 and nothing proceeds without it.
   This is arguably the right division of labour anyway: the Lead Auditor should be
   the one transcribing the control text.
2. **Copyright.** Is cyber.gov.au content Creative Commons, and under what
   attribution? If it is, the real text can be included properly attributed, which
   makes the tool considerably more useful.
3. **`max_age_days` default.** 180 or 365. Given the Essentials transition, shorter
   is arguably more honest.
4. **Not applicable.** ASD does not really contemplate N/A for Essential Eight
   criteria. Proposal: do not offer it. `unknown` covers genuine uncertainty and
   scores safely.
5. **Test runner.** Plain Python test files, matching Mission Control, or pytest.
   pytest is more recognisable to a reviewer and makes the invariant tests easier.

## 12. Risks and assumptions

| Risk | Mitigation |
|---|---|
| **Criteria transcribed wrong.** The entire tool is then confidently wrong, and no test can detect it | The stage 1 human gate. Jackson reviews against the official model. This is the single largest risk and it is not solvable by code |
| The framework is retired from ~mid-2027 | Control set is versioned data. The README states the position rather than hiding it |
| Someone treats the output as compliance evidence | Disclaimer in the README, in the CLI output and in every generated report |
| Scope creep to all eight strategies | Named in Out of Scope. Revisit only after stage 5 ships |
| An assessment file gets committed | `.gitignore` written before any such file can exist |

**Assumption:** the November 2023 model is still current. Reported as such as at
August 2026, but not verified by Claude directly against ASD.

---

**Please review and approve before I build.**
