#!/usr/bin/env python3
"""
research.py — one-command Deep Research digest for the maintaining agent.

**Why this exists (workload reduction).** Across the 2026-05 dogfooding runs the
agent hand-wrote the *same* throwaway orchestration script six times
(`.scratch_meta.py`, `.scratch_mitoma.py`, `.scratch_ddg.py`, …): multi-search →
triage by `source_tier` → drop `near_duplicate` → dedup by host → read the top N
→ print snippets. That scaffold is identical every time. This turns it into:

    python scripts/research.py "<topic>"
    python scripts/research.py "辺地共聴施設 政策" --region jp-jp --recent
    python scripts/research.py "Rust language 2026" --read 5

It only orchestrates existing tools (search_web / read_article / suggest_queries
+ the noise auditor) — no new retrieval logic — and prints a synthesis-ready
digest: authoritative sources first, near-dups skipped, each read source with a
snippet and a residual-noise flag, plus lateral query ideas. The agent then
*writes the report* from the digest; this just removes the plumbing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

from dogfood_audit import audit_markdown  # noqa: E402

from src.deepsearch_mcp.tools.extractor import read_article  # noqa: E402
from src.deepsearch_mcp.tools.search import search_web  # noqa: E402
from src.deepsearch_mcp.tools.suggest import suggest_queries  # noqa: E402


def triage(pool: list[dict], read_n: int) -> list[dict]:
    """The scaffold the agent kept re-writing: authoritative-first, drop
    near-duplicates, one result per host, capped at read_n. Pure + testable."""
    picks: list[dict] = []
    seen: set[str] = set()
    for x in sorted(pool, key=lambda y: 0 if y.get("source_tier") == "authoritative" else 1):
        if x.get("near_duplicate"):
            continue
        try:
            host = urlparse(x.get("url", "")).hostname or ""
        except Exception:
            host = ""
        if host and host not in seen:
            seen.add(host)
            picks.append(x)
        if len(picks) >= read_n:
            break
    return picks


def _results(raw: str) -> list[dict]:
    try:
        d = json.loads(raw)
        return d if isinstance(d, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def _snippet(body: str, n: int = 460) -> str:
    start = body.find("\n\n")
    s = body[start:].strip() if start > 0 else body.strip()
    return s[:n].replace("\n", " ")


async def run(topic: str, region: str | None, read_n: int, per_search: int,
              recent: bool) -> int:
    region_arg = region or "wt-wt"
    print("=" * 74)
    print(f"  RESEARCH DIGEST — {topic!r}")
    print("=" * 74)

    # 1. searches: broad + (optional) recent
    pool: list[dict] = []
    queries = [(topic, None)]
    if recent:
        queries.append((f"{topic} 2026", "m"))
    n_auth = n_dup = 0
    for q, tl in queries:
        res = _results(await search_web(query=q, region=region_arg, timelimit=tl,
                                        max_results=per_search))
        if not res:
            print(f"  ⚠ search {q!r} returned no results (backend error or empty)")
            continue
        pool.extend(res)
        n_auth += sum(1 for x in res if x.get("source_tier") == "authoritative")
        n_dup += sum(1 for x in res if x.get("near_duplicate"))
    if not pool:
        print("  ❌ No search results at all — cannot research. (search backend down?)")
        return 1
    print(f"  search: {len(pool)} results | {n_auth} authoritative | "
          f"{n_dup} near-duplicate")

    # 2. triage + read
    picks = triage(pool, read_n)
    print(f"\n  reading {len(picks)} source(s) (authoritative-first, deduped):\n")
    for x in picks:
        body = await read_article(url=x["url"])
        try:
            err = json.loads(body)
            print(f"  ✗ [{x['source_tier'][:4]}] {x['url'][:64]} → {err.get('code')}")
            continue
        except json.JSONDecodeError:
            pass
        noise = len(audit_markdown(body))
        flag = f" ⚠{noise} suspected-noise" if noise else ""
        print(f"  • [{x['source_tier'][:4]}] {x['title'][:66]}")
        print(f"    {x['url'][:72]}{flag}")
        print(f"    {_snippet(body)}\n")

    # 3. lateral angles (cheap; helps go deeper)
    lat = _results(await suggest_queries(topic=topic))
    if lat:
        print("  lateral angles (suggest_queries):")
        for q in lat[:6]:
            print(f"    - {q}")

    print("-" * 74)
    print("  Now WRITE THE REPORT from the above: lead with [auth] sources, "
          "corroborate")
    print("  [unkn] claims across independent results, label confidence.")
    print("=" * 74)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="One-command research digest.")
    p.add_argument("topic", help="Research topic (quote it).")
    p.add_argument("--region", default=None, help="DDG region, e.g. jp-jp.")
    p.add_argument("--read", type=int, default=4, help="How many sources to read.")
    p.add_argument("--max", type=int, default=8, dest="per_search",
                   help="Results per search query.")
    p.add_argument("--recent", action="store_true",
                   help="Add a second, time-limited (last-month) search.")
    args = p.parse_args(argv)
    return asyncio.run(run(args.topic, args.region, args.read, args.per_search,
                           args.recent))


if __name__ == "__main__":
    sys.exit(main())
