#!/usr/bin/env python3
"""
propose_noise_regex.py — turn an auditor finding into a *safe* cleaner pattern.

**Honest scope.** Writing a regex from a known noise line is not an agent's
bottleneck — an LLM does that in seconds. The real, error-prone, tedious part
is verifying the pattern is **not too broad**: a `_NOISE_LINE_RE` alternative
that accidentally matches real prose silently eats article content (the
cleaner's worst failure mode). Checking that by hand means grepping every
fixture and eyeballing. This tool mechanizes exactly that.

So this is a regex **safety preview**, not a magic regex writer:

  1. Generalize a conservative candidate around the auditor's matched signal
     (whitespace-flexible, escaped, `\b`-guarded — and deliberately *no*
     trailing `\b` after a punctuation-ending token, the trap that broke
     `Tags:` matching on 2026-05-29).
  2. Confirm it matches the offending line.
  3. **Blast radius**: run it against every dogfood fixture's extracted body
     and report what else it would remove — split into "already-clean prose"
     (⚠️ over-broad: it would eat content) vs the intended noise.

The agent still decides whether the line is noise at all, and still reviews
the candidate before pasting it into `utils/cleaner.py`. The tool removes the
*verification* toil, not the *judgment*.

Run:
    python scripts/propose_noise_regex.py "This article may contain affiliate links."
    # no arg → propose from the live audit of the dogfood fixtures (may be empty)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from dogfood_audit import audit_markdown, matched_signal  # noqa: E402

_NUMBERISH_RE = re.compile(r"^[\d.,]+[kKmM]?$")


def _tokenize(signal: str) -> list[str]:
    """Per-token regex fragments, generalizing numbers so counts vary.

    - pure digits      ("23")    → r"\\d+"
    - number-ish       ("1.2K")  → r"[\\d.,]+[kKmM]?"   (social counts)
    - literal word     ("shares")→ re.escape("shares")
    Numbers in noise are almost always variable (counts, IDs); literalizing
    them would make the pattern match only the one example we saw.
    """
    frags: list[str] = []
    for tok in signal.split():
        if tok.isdigit():
            frags.append(r"\d+")
        elif _NUMBERISH_RE.match(tok):
            frags.append(r"[\d.,]+[kKmM]?")
        else:
            frags.append(re.escape(tok))
    return frags


def candidate_regex(signal: str) -> str:
    """Build a conservative, whitespace-flexible regex from a signal phrase.

    - Generalize numeric tokens (see `_tokenize`) so counts vary.
    - Join tokens with `\\s+` (tolerate reflow / &nbsp).
    - Leading `\\b` iff the phrase starts with a word char.
    - Trailing `\\b` iff the phrase *ends* with a word char — never after
      punctuation (the 2026-05-29 trailing-`\\b` trap that broke `Tags:`).
    """
    s = signal.strip()
    body = r"\s+".join(_tokenize(s))
    lead = r"\b" if s[:1].isalnum() else ""
    tail = r"\b" if s[-1:].isalnum() else ""
    return f"{lead}{body}{tail}"


def _fixture_bodies() -> dict[str, str]:
    """Extracted (final) body of every dogfood fixture, by name."""
    from dogfood_research import (  # noqa: PLC0415
        DEVTO_HTML,
        LANGCHAIN_HTML,
        TECHCRUNCH_HTML,
        ZDNET_HTML,
    )

    from src.deepsearch_mcp.core.extractor import build_frontmatter, extract  # noqa: PLC0415

    fixtures = {
        "techcrunch": (TECHCRUNCH_HTML, "https://techcrunch.com/x/"),
        "langchain": (LANGCHAIN_HTML, "https://blog.langchain.dev/y/"),
        "devto": (DEVTO_HTML, "https://dev.to/z/"),
        "zdnet": (ZDNET_HTML, "https://www.zdnet.com/w/"),
    }
    out: dict[str, str] = {}
    for name, (html, url) in fixtures.items():
        body, meta = extract(html, url=url)
        out[name] = build_frontmatter(meta) + "\n\n" + body
    return out


def _looks_like_prose(line: str) -> bool:
    """A line is 'prose' (content, not noise) if the auditor does NOT flag it."""
    return matched_signal(line) is None


def blast_radius(pattern: str) -> tuple[list[str], list[str]]:
    """Run a candidate pattern across all fixtures' final (clean) bodies.

    Returns (prose_hits, noise_hits): lines the pattern would match, split by
    whether they look like real content. ANY prose_hit ⇒ the pattern is too
    broad. (Fixtures are already cleaned, so a noise_hit here is rare but still
    informative.)
    """
    rx = re.compile(pattern, re.IGNORECASE)
    prose_hits: list[str] = []
    noise_hits: list[str] = []
    for _name, body in _fixture_bodies().items():
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", "|", ">", "---")):
                continue
            if rx.search(line):
                (prose_hits if _looks_like_prose(line) else noise_hits).append(line)
    return prose_hits, noise_hits


def propose_for_line(line: str) -> int:
    print("=" * 72)
    print("  propose_noise_regex — candidate + blast-radius safety preview")
    print("=" * 72)
    print(f"  Input line : {line.strip()[:84]}")

    sig = matched_signal(line)
    if sig is None:
        print("  ⚠ The auditor does not flag this line — nothing to generalize.")
        print("    Either it is not noise, or it needs a new heuristic in")
        print("    dogfood_audit.py first. Write the cleaner regex by hand.")
        print("=" * 72)
        return 1

    category, signal = sig
    pattern = candidate_regex(signal)
    matches_target = bool(re.search(pattern, line, re.IGNORECASE))

    print(f"  Matched    : [{category}] {signal!r}")
    print(f"  Candidate  : r\"{pattern}\"")
    print(f"  Matches input line? {'✅ yes' if matches_target else '❌ NO (bug — do not use)'}")

    prose_hits, noise_hits = blast_radius(pattern)
    print("-" * 72)
    print("  Blast radius across dogfood fixtures (already-clean bodies):")
    if prose_hits:
        print(f"  ⚠️  TOO BROAD — would remove {len(prose_hits)} PROSE line(s):")
        for h in prose_hits[:5]:
            print(f"       {h[:80]}")
        print("     → narrow the signal before adding to _NOISE_LINE_RE.")
    else:
        print("  ✅ No prose lines matched — safe to add.")
    if noise_hits:
        print(f"  (also matches {len(noise_hits)} residual noise line(s) — bonus cleanup)")

    print("-" * 72)
    print("  Paste into utils/cleaner.py _NOISE_LINE_RE (review first):")
    print(f"    r\"|{pattern}\"")
    print("  Then: add a TestDogfoodingNoisePatterns case, run scripts/verify.py.")
    print("=" * 72)
    return 0 if (matches_target and not prose_hits) else 1


def propose_from_live_audit() -> int:
    """No CLI line given: pull suspected lines from the live fixtures."""
    bodies = _fixture_bodies()
    findings: list[str] = []
    for body in bodies.values():
        findings.extend(f.text for f in audit_markdown(body))
    if not findings:
        print("No current audit findings across dogfood fixtures — corpus is clean.")
        print("Pass a noise line explicitly to get a proposal:")
        print('  python scripts/propose_noise_regex.py "<the noise line>"')
        return 0
    rc = 0
    for line in dict.fromkeys(findings):  # dedupe, keep order
        rc |= propose_for_line(line)
    return rc


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv:
        return propose_for_line(" ".join(argv))
    return propose_from_live_audit()


if __name__ == "__main__":
    sys.exit(main())
