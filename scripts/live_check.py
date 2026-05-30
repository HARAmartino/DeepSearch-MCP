#!/usr/bin/env python3
"""
live_check.py — the *real-usage* CHECK the dogfooding loop was missing.

**Why this exists.** Until 2026-05-30 the loop's Check ran against
hand-written HTML fixtures and `--demo` data. That is self-authored: the
fixtures only ever contained noise I already thought of, so the Check could
never surprise me. The moment the tools were pointed at the **live web**, one
pass found two real bugs in minutes:
  - the auditor false-flagged real prose ("...concurrency, like") because a
    social-count regex matched a bare comma;
  - real Wikipedia citations ("[1]", "[12]") leaked into extracted prose.
Neither could occur in my fixtures. Fixtures ≠ real usage.

This script makes real-usage Check a one-command habit: run the **real**
`read_article` over a curated set of live, diverse pages, audit each output,
and print samples to *read critically*. It is NOT a gate (the web changes;
pages 403; this is non-deterministic) — it is a periodic probe whose findings
become fixtures, cleaner patterns, or backlog items.

Run (needs network):
    python scripts/live_check.py
    python scripts/live_check.py --full   # print full bodies, not samples
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

os.environ["DEEPSEARCH_TELEMETRY"] = "0"  # this is a quality probe, not telemetry
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

from dogfood_audit import audit_markdown  # noqa: E402

from src.deepsearch_mcp.tools.extractor import read_article  # noqa: E402

# Curated, diverse, reasonably-stable real pages. Edit freely — the point is
# breadth (code docs / spec / wiki-with-citations / product docs / blog).
LIVE_URLS = [
    "https://docs.python.org/3/library/asyncio-task.html",   # code-heavy docs
    "https://peps.python.org/pep-0008/",                     # long structured spec
    "https://en.wikipedia.org/wiki/Large_language_model",    # wiki: citations, infobox
    "https://modelcontextprotocol.io/docs/concepts/architecture",  # product docs
]


def _sample(body: str, n: int = 600) -> str:
    head = body[:n]
    mid = body[len(body) // 2: len(body) // 2 + n // 2]
    return head + "\n   …[middle]…\n" + mid


async def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    full = "--full" in argv

    print("=" * 74)
    print("  live_check — real-usage CHECK (live web, read the output critically)")
    print("=" * 74)
    total_findings = 0
    for url in LIVE_URLS:
        result = await read_article(url=url)
        try:
            d = json.loads(result)
            print(f"\n### {url}\n  ERROR {d.get('code')} — {d.get('hint', '')[:60]}")
            continue
        except json.JSONDecodeError:
            pass
        findings = audit_markdown(result)
        total_findings += len(findings)
        print(f"\n### {url}")
        print(f"  size={len(result)}c (~{len(result) // 4} tok)  "
              f"auditor_findings={len(findings)}")
        for f in findings[:8]:
            print(f"    AUDIT: {f}")
        print("  ---- output ----")
        print(result if full else _sample(result))

    print("\n" + "=" * 74)
    print(f"  auditor findings across {len(LIVE_URLS)} live pages: {total_findings}")
    print("  Read the samples above by hand — the auditor is one heuristic, not")
    print("  the whole Check. Noise it misses → new cleaner pattern / fixture.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
