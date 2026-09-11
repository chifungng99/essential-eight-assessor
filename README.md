# Essential Eight Assessor

A command line self-assessment tool for the Australian Signals Directorate's
**Essential Eight Maturity Model**. You answer a structured set of questions about
your environment, and it computes a maturity level per mitigation strategy and
writes a gap report telling you what is missing and what to fix first.

> **This is an indicative self-assessment, not a certified ASD assessment.**
> It has no affiliation with, and no endorsement from, the Australian Signals
> Directorate or the Australian Cyber Security Centre. Its output is a starting
> point for a conversation, not evidence of compliance.

**Status: in development.** Nothing here is usable yet.

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
criteria file carries a `sourced_on` date. Past a configured age the tool warns
loudly, and it will not silently produce a maturity rating from a stale model. A
tool that returns "Maturity Level Two" against superseded criteria is worse than one
that stops, because nobody checks a number that looks plausible.

## Scope

Version one covers three mitigation strategies in full, across Maturity Levels One
to Three:

- Patch Applications
- Patch Operating Systems
- Multi-factor Authentication

Three strategies covered properly is more useful, and more honest, than eight
covered shallowly. The remaining five are additive once the engine is proven.

## Source material and attribution

Control criteria are the work of the Australian Signals Directorate and are
published at [cyber.gov.au](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight).
This repository stores paraphrased criteria alongside the official identifiers, the
model version, and links back to the source, rather than reproducing ASD's text.
Always read the official model. This tool is not a substitute for it.

## Licence

MIT, see [LICENSE](LICENSE). The licence covers this tool's own code and data
structures. It does not and cannot extend to ASD's published material.
