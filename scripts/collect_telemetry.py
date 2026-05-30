#!/usr/bin/env python3
"""
collect_telemetry.py — bootstrap the *aggregate* half of the PDCA loop.

**Why this exists.** The loop has two probes (see ARCHITECTURE.md §3): the
*semantic* one (dogfooding/auditor) has been exercised heavily; the *aggregate*
one (`analyze_telemetry.py` over `telemetry.db`) has been dormant because no
real traffic ever accumulated — dev runs mocked `fetch`, so the DB only ever
held synthetic rows. This script drives the **real** tools over a curated
battery so `telemetry.db` fills with production-shaped data, then hands off to
the analyzer. It is the network-having operator's "day 1" activation.

**Honesty about connectivity.** `read_article` (curl_cffi) reaches live sites;
`search_web` (DDGS→bing backend) may be blocked in restricted networks. Both
are run anyway — a `CONN_ERROR` row is real telemetry too, and the analyzer's
error-pattern report is exactly how you'd notice a dead backend in production.

Politeness: the tools already insert jitter + capped retries; we add a small
inter-call sleep. The battery is intentionally small and uses neutral targets
(example.com, httpbin.org status codes, a bogus domain, a PDF) plus a couple of
real doc pages, so outcomes span success / 403 / 5xx / DNS / unsupported-format.

Run (in an environment with network):
    DEEPSEARCH_TELEMETRY_DIR=.cache_live python scripts/collect_telemetry.py
    DEEPSEARCH_TELEMETRY_DIR=.cache_live python evals/analyze_telemetry.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

# Telemetry ON, isolated to a live-collection dir by default (not dev/.cache).
os.environ["DEEPSEARCH_TELEMETRY"] = "1"
os.environ.setdefault("DEEPSEARCH_TELEMETRY_DIR", ".cache_live")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.deepsearch_mcp.core import telemetry  # noqa: E402
from src.deepsearch_mcp.tools.extractor import read_article  # noqa: E402
from src.deepsearch_mcp.tools.search import search_web  # noqa: E402

INTER_CALL_SLEEP = 0.4  # politeness on top of the tools' own jitter

# Real queries — exercise the search path (may be CONN_ERROR on blocked nets).
SEARCH_QUERIES = [
    "model context protocol 2026",
    "LangGraph production agents",
]

# URL battery chosen so outcomes SPAN the error space on real infrastructure:
#   - example.com / mcp.io docs   → success
#   - httpbin.org/html            → success (3rd httpbin call ⇒ a real domain
#                                     with ≥3 samples ⇒ a hotspot to report)
#   - httpbin.org/status/403      → BLOCKED_403
#   - httpbin.org/status/503      → CONN_ERROR (retryable 5xx exhausts retries)
#   - bogus domain                → CONN_ERROR (DNS)
#   - .pdf                        → UNSUPPORTED_FORMAT (no network needed)
READ_URLS = [
    "https://example.com/",
    "https://modelcontextprotocol.io/introduction",
    "https://httpbin.org/html",
    "https://httpbin.org/status/403",
    "https://httpbin.org/status/503",
    "https://nonexistent-domain-zzz-998877.example.invalid/",
    "https://arxiv.org/pdf/2401.00001.pdf",
]


def _outcome(result: str) -> str:
    try:
        d = json.loads(result)
        if isinstance(d, dict) and d.get("status") == "error":
            return f"ERROR:{d.get('code', '?')}"
        if isinstance(d, list):
            return f"OK:{len(d)} results"
    except (json.JSONDecodeError, ValueError):
        pass
    return f"OK:body ({len(result)}c)"


async def collect() -> None:
    print("=" * 70)
    print("  collect_telemetry — activating the AGGREGATE half (live tools)")
    print(f"  Telemetry DB: {telemetry.get_db_path()}")
    print("=" * 70)

    await telemetry.reset_for_tests()  # clean slate for this collection run

    print("\n[search_web] (DDGS backend — may be blocked on restricted nets)")
    for q in SEARCH_QUERIES:
        out = _outcome(await search_web(query=q, max_results=3))
        print(f"  {q[:48]:48} → {out}")
        await asyncio.sleep(INTER_CALL_SLEEP)

    print("\n[read_article] (curl_cffi — reaches live sites)")
    for url in READ_URLS:
        t0 = time.perf_counter()
        out = _outcome(await read_article(url=url))
        dt = time.perf_counter() - t0
        print(f"  {url[:52]:52} → {out:22} {dt:4.1f}s")
        await asyncio.sleep(INTER_CALL_SLEEP)

    await telemetry.drain()
    print("\n✓ Telemetry collected. Now run the aggregate analyzer:")
    print(f"    DEEPSEARCH_TELEMETRY_DIR={os.environ['DEEPSEARCH_TELEMETRY_DIR']} "
          f"python evals/analyze_telemetry.py")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(collect())
