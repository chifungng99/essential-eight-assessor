#!/usr/bin/env python3
"""Build the versioned control set from ASD's published Essential Eight Maturity Model.

The control set is GENERATED, never hand-typed. Transcribing ~114 requirements by
hand would introduce errors that no test could detect: the tool would score against
subtly wrong criteria and return numbers that looked entirely reasonable. Generating
it from ASD's own document means the provenance is checkable and the whole thing can
be rebuilt when a new edition is published.

Input is the plain text of the official PDF, produced with:

    pdftotext -layout "Essential Eight maturity model (November 2023).pdf" e8.txt

The PDF itself is deliberately NOT committed to this repository. Its text is licensed
CC BY 4.0, but the Commonwealth Coat of Arms and the ASD logo it contains are
explicitly excluded from that licence, so redistributing the file would redistribute
those marks. The generated JSON contains text only.

Usage:
    python3 tools/extract_controls.py e8.txt controls/e8-2023-11.json
"""

import hashlib
import json
import re
import sys
from datetime import date

# Column 27 is where the Description column begins in the -layout output. The
# Mitigation Strategy name sits to its left and wraps across lines ("Multi-factor"
# then "authentication"), so both columns are accumulated per block.
DESC_COL = 27

LEVEL_WORDS = {"One": 1, "Two": 2, "Three": 3}

# Short, stable id prefixes. Keyed by the strategy name as printed in the model.
STRATEGY_IDS = {
    "Application control": "app-control",
    "Patch applications": "patch-apps",
    "Restrict Microsoft Office macros": "office-macros",
    "User application hardening": "app-hardening",
    "Restrict administrative privileges": "admin-privs",
    "Patch operating systems": "patch-os",
    "Multi-factor authentication": "mfa",
    "Regular backups": "backups",
}

# Version one deliberately covers three strategies completely rather than eight
# shallowly. See docs/PRD.md.
IN_SCOPE = ["Patch applications", "Patch operating systems", "Multi-factor authentication"]

FOOTER = re.compile(r"^\s*Essential Eight maturity model\s+\d+\s*$")
APPENDIX = re.compile(r"^\s*Appendix ([A-D]): .*$")
MATURITY_APPENDIX = re.compile(r"^\s*Appendix ([A-C]): Maturity Level (One|Two|Three)\s*$")

# Every maturity level appendix must yield exactly the eight mitigation strategies.
# This assertion is not decoration. The first version of this parser did not bound
# Appendix C, so Appendix D and the copyright page were parsed as Maturity Level
# Three requirements. The criterion counts it produced looked high but not absurd,
# and would have been easy to accept. A structural check on the source catches that
# class of error; no test of the scoring engine ever would.
EXPECTED_STRATEGIES = 8


def join_wrapped(parts):
    """Join wrapped lines into one string.

    A line ending in '-' is a word split across the line break ('non-' then
    'internet-facing'), so it joins with no space. Getting this wrong produces
    'non- internet-facing', which then fails to match the identical requirement
    printed at another maturity level and silently duplicates it in the output.
    """
    out = ""
    for p in parts:
        if not out:
            out = p
        elif out.endswith("-"):
            out += p
        else:
            out += " " + p
    return re.sub(r"\s+", " ", out).strip()


def parse(text):
    """-> {level: {strategy_name: [criterion, ...]}}"""
    lines = text.split("\n")

    # Every appendix heading, so that Appendix C is bounded by Appendix D rather
    # than running to the end of the document.
    headings = [i for i, line in enumerate(lines) if APPENDIX.match(line.replace("\f", ""))]

    starts = []
    for i, line in enumerate(lines):
        m = MATURITY_APPENDIX.match(line.replace("\f", ""))
        if m:
            starts.append((i, LEVEL_WORDS[m.group(2)]))
    if len(starts) != 3:
        raise ValueError(f"expected 3 maturity level appendices, found {len(starts)}")

    result = {}
    for start, level in starts:
        later = [h for h in headings if h > start]
        end = later[0] if later else len(lines)
        strategies = parse_appendix(lines[start + 1:end])
        if len(strategies) != EXPECTED_STRATEGIES:
            raise ValueError(
                f"Maturity Level {level}: parsed {len(strategies)} mitigation strategies, "
                f"expected {EXPECTED_STRATEGIES}. Parsed: {sorted(strategies)}"
            )
        result[level] = strategies
    return result


def parse_appendix(lines):
    strategies, current = {}, None
    label_parts, body_parts = [], []

    def flush():
        nonlocal current, label_parts, body_parts
        label = join_wrapped(label_parts)
        body = join_wrapped(body_parts)
        if label and label != "Mitigation Strategy":
            current = label
            strategies.setdefault(current, [])
        if body and body != "Description" and current:
            strategies[current].append(body)
        label_parts, body_parts = [], []

    for raw in lines:
        line = raw.replace("\f", "")
        if FOOTER.match(line) or not line.strip():
            flush()
            continue
        label, body = line[:DESC_COL].strip(), line[DESC_COL:].strip()
        if label:
            label_parts.append(label)
        if body:
            body_parts.append(body)
    flush()
    return strategies


def canonicalise(by_level, in_scope):
    """Collapse per-level lists into one criterion per requirement.

    Each appendix restates the complete requirement set for its level rather than
    listing only additions, so the same requirement appears verbatim at several
    levels. Storing it once and tagging the levels that require it keeps the data
    honest and means a user answers each question once rather than three times.
    """
    strategies = []
    for name in in_scope:
        seen, order = {}, []
        for level in (1, 2, 3):
            for text in by_level[level].get(name, []):
                if text not in seen:
                    seen[text] = []
                    order.append(text)
                seen[text].append(level)

        criteria = []
        for i, text in enumerate(order, start=1):
            criteria.append({
                "id": f"{STRATEGY_IDS[name]}-{i:02d}",
                "text": text,
                "required_at_levels": seen[text],
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            })
        strategies.append({"id": STRATEGY_IDS[name], "name": name, "criteria": criteria})
    return strategies


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()
    by_level = parse(text)
    control_set = {
        "model": "ASD Essential Eight Maturity Model",
        "version": "November 2023",
        "source_url": "https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight/essential-eight-maturity-model",
        "sourced_on": date.today().isoformat(),
        "max_age_days": 180,
        "licence": {
            "name": "CC BY 4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Essential Eight Maturity Model (November 2023), © Commonwealth of Australia 2023, "
                           "Australian Signals Directorate, licensed under CC BY 4.0. "
                           "The Commonwealth Coat of Arms and the ASD logo are excluded from this licence "
                           "and are not reproduced here.",
        },
        "strategies": canonicalise(by_level, IN_SCOPE),
    }
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(control_set, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    for s in control_set["strategies"]:
        per = {lv: sum(1 for c in s["criteria"] if lv in c["required_at_levels"]) for lv in (1, 2, 3)}
        print(f"{s['name']:32} {len(s['criteria']):3} unique   ML1 {per[1]:2}  ML2 {per[2]:2}  ML3 {per[3]:2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
