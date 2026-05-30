"""
Noise-Leak Auditor — the systematic CHECK step of the dogfooding loop.

**Why this exists (methodology improvement, 2026-05-29).**
The dogfooding loop's "CHECK" step was, until now, a human reading the whole
extraction body and *hoping* to notice leftover noise. That is unreproducible
(different reviewer → different catches) and does not scale.

Backlog item B5 originally proposed bolting a "noise leak hint" onto
`analyze_telemetry.py`. That is architecturally impossible: `telemetry.db`
stores no response bodies (only a status, a token *count*, and a truncated
input summary — by privacy/size design). The analyzer therefore has nothing
to scan. The auditor must live where the bodies actually exist: the
**dogfooding path**. This module is B5, relocated.

**How it works.**
`audit_markdown(text)` runs over the FINAL extraction output (post-cleaner).
Because anything `utils/cleaner.py` already removes is gone by this point,
every line the auditor flags is by definition a *leak the cleaner missed* —
a candidate for a new `_NOISE_LINE_RE` pattern or a domain adapter.

The heuristics here are deliberately **broader** than the cleaner's removal
patterns (the cleaner is precise to avoid eating prose; the auditor is
sensitive to surface candidates). To keep false-positives low it only
considers *short* prose lines — long paragraphs are essentially never
boilerplate even when they contain a word like "subscribe".

Contract: the auditor never mutates anything. It only *reports*. A human (or
LLM) triages the shortlist and decides what to patch. Findings are advisory.

Run:
    python evals/dogfood_audit.py path/to/output.md
    # or import audit_markdown() from the dogfooding harness
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------

# A prose line longer than this (words) is treated as real content for the
# SOFT heuristics only. Boilerplate CTAs / stubs are short; paragraphs are not.
# STRONG heuristics ignore this gate (see two-tier design below).
_MAX_SUSPECT_WORDS = 14

# ---------------------------------------------------------------------------
# Two-tier suspicion heuristics (INDEPENDENT of utils/cleaner._NOISE_LINE_RE).
#
# STRONG: signals that are never legitimate article prose regardless of line
#   length. Affiliate/sponsorship disclosures and legal footers are often full
#   sentences (>14 words) — the dogfooding session of 2026-05-29 found a
#   16-word affiliate-disclosure sentence that the old single-tier, length-
#   gated auditor silently skipped. Strong signals bypass the word gate.
#
# SOFT: signals that *can* legitimately appear inside prose (a paragraph may
#   say "we share a common goal"). These only fire on SHORT lines, where the
#   line is structurally a label/CTA rather than a sentence.
#
# Each entry is (category, compiled_regex). Order within a tier = report
# priority.
# ---------------------------------------------------------------------------

_STRONG_HEURISTICS: list[tuple[str, re.Pattern]] = [
    (
        "AFFILIATE_SPONSOR",
        re.compile(
            r"\b(affiliate\s+links?|may\s+earn\s+an?\s+commission|"
            r"this\s+(article|post|page)\s+(may\s+)?contains?|"
            r"sponsored(\s+(content|post|by))?|paid\s+(partnership|promotion)|"
            r"promoted\s+(content|post|by)|advertisement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "LEGAL_FOOTER",
        re.compile(
            r"(©|\(c\)\s*\d{4}|all\s+rights\s+reserved|privacy\s+policy|"
            r"terms\s+of\s+(use|service)|cookie\s+(policy|settings|consent))",
            re.IGNORECASE,
        ),
    ),
]

_SOFT_HEURISTICS: list[tuple[str, re.Pattern]] = [
    (
        "PROMO_CTA",
        re.compile(
            r"\b(subscribe|sign\s?up|sign\s?in|log\s?in|register|join\s+\d|"
            r"follow\s+us|follow\s+me|share\s+this|share\s+on|download\s+the|"
            r"unlock|upgrade\s+to|donate|buy\s+me\s+a\s+coffee|get\s+started|"
            r"learn\s+more|read\s+more|continue\s+reading|listen\s+to\s+this|"
            r"watch\s+(now|the\s+video)|play\s+audio|enable\s+notifications)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # No trailing \b: several alternatives end in punctuation (":", "|"),
        # where a trailing \b would (incorrectly) fail to match. The ^\s*
        # anchor already scopes these to line starts.
        "METADATA_STUB",
        re.compile(
            r"^\s*(by\s+[A-Z]|tags?\s*[:|]|posted\s+(in|on|by)|filed\s+under|"
            r"categor(y|ies)\s*[:|]|published\s+(in|on|by)|updated\s*[:|]|"
            r"photo\s+by|image(\s+credit)?\s*[:|]|credit\s*[:|]|source\s*[:|]|"
            r"originally\s+published)",
            re.IGNORECASE,
        ),
    ),
    (
        # Social counts may carry K/M suffixes and decimals ("1.2K shares").
        "ENGAGEMENT_BAIT",
        re.compile(
            r"(\b\d+\s*(min|minute)s?\s+read\b|(estimated\s+)?reading\s+time|"
            r"\bview\s+all\s+\d+|"
            # social counts: MUST start with a digit. A bare "[\d.,]+" also
            # matched a lone comma, so real prose like "...concurrency, like"
            # tripped it (",  like"). Real-usage check on docs.python.org,
            # 2026-05-30, surfaced this false positive. Require \d to lead.
            r"\b\d[\d.,]*\s*[km]?\s*(comments?|views?|shares?|claps?|likes?)\b)",
            re.IGNORECASE,
        ),
    ),
]


@dataclass
class Finding:
    line_no: int        # 1-based line number within the audited text
    category: str
    text: str           # the offending line (trimmed)

    def __str__(self) -> str:
        return f"L{self.line_no:<4} [{self.category:<15}] {self.text[:90]}"


# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_TABLE_RE = re.compile(r"^\s*\|")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")


def _is_structural(line: str) -> bool:
    """Headings / tables / blockquotes are content scaffolding, never noise."""
    return bool(
        _HEADING_RE.match(line)
        or _TABLE_RE.match(line)
        or _BLOCKQUOTE_RE.match(line)
    )


def _strip_list_marker(line: str) -> str:
    """Return the text of a list item without its bullet/number marker."""
    return re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line)


def matched_signal(line: str) -> tuple[str, str] | None:
    """Return (category, matched_substring) for a single line, or None.

    Unlike `audit_markdown` (which reports the whole line), this exposes the
    *substring* a heuristic actually matched — the salient signal phrase.
    `scripts/propose_noise_regex.py` generalizes a cleaner pattern around it.
    """
    candidate = _strip_list_marker(line.strip())
    word_count = len(candidate.split())
    for category, pattern in _STRONG_HEURISTICS:
        m = pattern.search(candidate)
        if m:
            return category, m.group(0)
    if word_count <= _MAX_SUSPECT_WORDS:
        for category, pattern in _SOFT_HEURISTICS:
            m = pattern.search(candidate)
            if m:
                return category, m.group(0)
    return None


def audit_markdown(text: str) -> list[Finding]:
    """Scan post-cleaner extraction output for suspected residual noise.

    Skips YAML frontmatter, fenced code blocks, and structural markdown
    (headings, tables, blockquotes). Considers only *short* prose / list
    lines, applying the broad suspicion heuristics above.
    """
    findings: list[Finding] = []
    if not text:
        return findings

    lines = text.splitlines()
    in_frontmatter = False
    in_code = False

    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        # YAML frontmatter: a leading --- opens it, the next --- closes it.
        if stripped == "---":
            # Only treat as frontmatter delimiter in the leading region.
            if idx <= 8 or in_frontmatter:
                in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue

        # Fenced code blocks: never noise.
        if _FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue

        if _is_structural(line):
            continue

        candidate = _strip_list_marker(stripped)
        word_count = len(candidate.split())

        # Tier 1 — STRONG: fire at any length (affiliate/sponsor/legal).
        matched = None
        for category, pattern in _STRONG_HEURISTICS:
            if pattern.search(candidate):
                matched = category
                break

        # Tier 2 — SOFT: only on short lines (long lines are real prose).
        if matched is None and word_count <= _MAX_SUSPECT_WORDS:
            for category, pattern in _SOFT_HEURISTICS:
                if pattern.search(candidate):
                    matched = category
                    break

        if matched is not None:
            findings.append(Finding(line_no=idx, category=matched, text=candidate))

    return findings


def audit_report(label: str, text: str) -> tuple[str, int]:
    """Render a human-readable audit block for one document. Returns (text, n)."""
    findings = audit_markdown(text)
    lines = [f"  ── {label} ── {len(findings)} suspected line(s)"]
    for f in findings:
        lines.append(f"     {f}")
    if not findings:
        lines.append("     ✅ clean (no residual noise candidates)")
    return "\n".join(lines), len(findings)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: python evals/dogfood_audit.py <file.md> [<file.md> ...]", file=sys.stderr)
        return 2

    total = 0
    print("=" * 70)
    print("  Noise-Leak Auditor — suspected residual noise (post-cleaner)")
    print("=" * 70)
    for path in argv:
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            print(f"  ⚠ cannot read {path}: {exc}", file=sys.stderr)
            continue
        block, n = audit_report(path, content)
        print(block)
        total += n

    print("-" * 70)
    print(f"  TOTAL suspected lines: {total}")
    print("  (Each line is a candidate for a new utils/cleaner._NOISE_LINE_RE")
    print("   pattern or a domain adapter. Triage manually — findings are advisory.)")
    print("=" * 70)
    # Exit non-zero if anything was flagged, so CI/cron can gate on it.
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
