"""MCP Tool: search_web — DuckDuckGo search with caching and structured error handling.

Implementation notes:
- DDGS v8 is a SYNCHRONOUS library (uses primp Rust client internally).
  All calls are wrapped in asyncio.to_thread() to avoid blocking the event loop.
- DDGS v8 result dicts use key 'href' (not 'url') for the page URL.
- DDGS v8 does not return publication dates in any backend (html/lite/bing).
  As a freshness signal (B14), published_date is derived best-effort from the
  result URL path (news URLs embed the pub date, e.g. /2026/05/28/); it stays
  None when the URL carries no date. The snippet body is intentionally not
  mined — a ~30-word excerpt's first date is too unreliable for a recency filter.
- DDGS already applies TLS fingerprinting via primp (impersonate='random').
  Additional stealth headers are passed via DDGS(headers={...}) constructor.
- A fresh DDGS instance is created per request (thread-safe, no shared state).
- RuntimeWarning about package rename (duckduckgo_search → ddgs) is suppressed.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import warnings
from typing import Literal
from urllib.parse import parse_qs, quote_plus, urlparse

from mcp.server.fastmcp import FastMCP

from ..core import errors as err
from ..core.cache import TTL_SEARCH, cache_get, cache_set, make_search_key
from ..core.http import fetch
from ..core.models import SearchResult
from ..core.source_quality import classify_source
from ..core.telemetry import track
from ..utils.date_parser import best_effort_date

mcp = FastMCP("deepsearch-search-web")

_JITTER_MIN = 0.5
_JITTER_MAX = 1.5

# B13: one failed search may be transient; many in a row means the backend is
# DOWN, and rewording/broadening the query is futile (the agent just burns
# turns). Track consecutive failed live searches so the error hint can escalate
# from "retry once" to "stop rewording — switch strategy". This mirrors the
# telemetry skew guard ("a 100%-failing tool is systemic, not per-query") but at
# the per-session call site, since the agent acts on the hint immediately.
_OUTAGE_THRESHOLD = 3
_consecutive_failures = 0


def _note_search_outcome(failed: bool) -> int:
    """Update and return the consecutive live-search failure streak.

    A success (results returned, even an empty list — the backend was reachable)
    resets the streak; a failure increments it. Cache hits don't touch it (they
    prove nothing about backend health).
    """
    global _consecutive_failures
    _consecutive_failures = _consecutive_failures + 1 if failed else 0
    return _consecutive_failures


def _reset_failure_streak() -> None:
    """Reset the failure streak (test helper; never needed in production)."""
    global _consecutive_failures
    _consecutive_failures = 0

# Extra headers layered on top of primp's built-in browser fingerprint
_DDGS_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
}

# Direct-DuckDuckGo HTML endpoint — the fallback when the `duckduckgo-search`
# library fails. The library proxies all backends through bing.com; if bing is
# unreachable (regional block, outage) the whole tool dies even though DDG's
# own endpoint is fine. This scrapes DDG directly via our stealth fetch.
# (Discovered 2026-05-30: a real research run dead-ended because bing was
# DNS-blocked while html.duckduckgo.com was perfectly reachable.)
_DDG_HTML_URL = "https://html.duckduckgo.com/html/"


@mcp.tool()
@track(tool_name="search_web", primary_input="query")
async def search_web(
    query: str,
    region: str = "wt-wt",
    safesearch: Literal["on", "moderate", "off"] = "moderate",
    timelimit: Literal["d", "w", "m", "y"] | None = None,
    max_results: int = 10,
) -> str:
    """
    Performs a web search using DuckDuckGo and returns structured results.

    ## USE WHEN
    - **First step** of any research task — get a wide net of URLs and snippets.
    - Looking up a specific factual answer ("when was X released?").
    - Discovering URLs to hand off to `read_article` for full content.

    ## DO NOT USE WHEN
    - You already have a URL → call `read_article` directly.
    - Your last 2+ search rounds returned the same sources/angle →
      call `suggest_queries` first, then pick a lateral query.
    - Query is empty or only whitespace — returns EMPTY_CONTENT error.

    ## PARAMETERS
    - `query`: Keywords only (not full sentences). Max 500 chars.
      DuckDuckGo search operators are passed through verbatim — use them:
        • `-term`  exclude a word: `electric cars -tesla`
        • `"..."`  exact phrase: `"model context protocol"`
        • `site:`  restrict to a domain: `RAG site:arxiv.org`
        • `OR`     either term: `llama OR mistral benchmarks`
      To answer a "NOT about X" / "X以外" request, exclude with `-X`
      (e.g. `Silicon Valley trends 2026 -AI -"artificial intelligence"`).
      ⚠️ Excluding a *dominant* topic surfaces long-tail / low-relevance pages
      (events, directories); expect to mine the remaining substantive results.
    - `region`: Country code like 'us-en', 'jp-jp', 'wt-wt' (global default).
    - `timelimit`: 'd'=last day, 'w'=week, 'm'=month, 'y'=year. None=all time.
    - `max_results`: 1–50. Default 10. Use lower values for targeted queries.

    ## RETURNS
    JSON array of result objects, each with:
    - `title`: Page title
    - `url`: Full URL of the result
    - `body`: Search snippet/summary (150–300 chars)
    - `published_date`: ISO 8601 date (YYYY-MM-DD) **derived from the URL** when
      it embeds one (e.g. news `/2026/05/28/` paths), else null. Best-effort
      freshness signal — use it to spot/sort recent results on time-sensitive
      topics; treat as approximate, and prefer `timelimit="d"/"w"/"m"/"y"` to
      filter recency at the source. Null does NOT mean old (most non-news URLs
      carry no date).
    - `source_tier`: 'authoritative' (curated trusted domain, .gov, .edu) or
      'unknown'. **Read 'authoritative' results first.** If a result set is all
      'unknown' (common for SEO-heavy topics), corroborate facts across several
      independent results before trusting them. 'unknown' ≠ low quality — it
      just means the domain isn't on the trust list.
    - `near_duplicate`: true if the title closely matches an earlier result
      (same story). **Don't re-read near-duplicates** — but their count is
      useful corroboration. The primary copy (false) prefers an authoritative
      source. Results are never removed, only flagged.
    - `story_cluster`: integer id (or null) grouping results that report the
      **same story across different outlets** — looser than `near_duplicate`,
      it links paraphrased headlines sharing key entities. Same id ⇒ same event:
      **read 1–2 per cluster for corroboration, but treat them as one source**
      (don't count N same-cluster hits as N independent confirmations). Unlike
      near-duplicates these ARE worth reading across.

    ## CONSTRAINTS
    - Results are cached for 24 hours. Repeated identical queries are free.
    - A random delay (0.5–1.5s) is inserted before each live request.
    - Returns a structured JSON error if rate-limited or network fails.

    ## EXAMPLES (Few-Shot)

    Good:
      query="Python asyncio tutorial 2026", timelimit="y"
      → [{"title":"...","url":"https://site/2026/05/28/post","body":"...",
          "published_date":"2026-05-28"}]   # date lifted from the URL path

    Good (targeted, low token cost):
      query="site:github.com trafilatura", max_results=5
      → 5 GitHub results for trafilatura

    Bad (too broad — use suggest_queries first to refine):
      query="machine learning"

    Bad (has a URL already — use read_article directly):
      query="https://docs.python.org/3/library/asyncio.html"
    """
    if not query or not query.strip():
        return err.structured_error(
            err.EMPTY_CONTENT,
            "query must be a non-empty string",
            hint_override="Provide search keywords (e.g. 'python asyncio tutorial').",
        )

    max_results = max(1, min(50, max_results))
    region_param = None if region == "wt-wt" else region

    # --- Cache check ---
    cache_key = make_search_key(query, region_param, safesearch, timelimit)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # --- Jitter delay (CLAUDE.md: 0.5–1.5s before live request) ---
    await asyncio.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))

    # --- DDG search (sync → thread) ---
    try:
        raw_results = await asyncio.to_thread(
            _ddgs_search_sync,
            query,
            region_param,
            safesearch,
            timelimit,
            max_results,
        )
        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                body=r.get("body", ""),
                # B14: DDGS never returns a date, so derive a best-effort
                # freshness signal from the URL path (news URLs embed the
                # pub date, e.g. /2026/05/28/). Snippet body is NOT used — a
                # ~30-word excerpt's first date is too unreliable for a recency
                # filter. Stays null when the URL carries no date.
                published_date=best_effort_date(
                    raw=r.get("published"), url=r.get("href", "")
                ),
                source_tier=classify_source(r.get("href", "")),
            ).model_dump()
            for r in (raw_results or [])
        ]
    except Exception as exc:
        # Primary library failed (e.g. bing backend unreachable). Try the
        # direct-DDG HTML fallback before giving up — it bypasses bing.
        results = await _ddg_html_fallback(
            query, region_param, safesearch, timelimit, max_results
        )
        if not results:
            # B13: record the failure and let the hint escalate if searches
            # keep failing (systemic outage vs a one-off).
            streak = _note_search_outcome(failed=True)
            return _map_ddgs_exception(exc, consecutive_failures=streak)

    # Reached only on a reachable backend (results, possibly empty) → not an
    # outage; clear the failure streak (B13).
    _note_search_outcome(failed=False)

    # Flag near-duplicate titles (B16) + loose same-story clusters (B19).
    # Query tokens are excluded from clustering (B28) — they match every result.
    results = _mark_near_duplicates(results)
    results = _mark_story_clusters(results, query=query)

    output = json.dumps(results, ensure_ascii=False, indent=None)

    # --- Cache store (24h TTL) ---
    await cache_set(cache_key, output, TTL_SEARCH)

    return output


async def _ddg_html_fallback(
    query: str,
    region: str | None,
    safesearch: str,
    timelimit: str | None,
    max_results: int,
) -> list[dict]:
    """Scrape DuckDuckGo's own HTML endpoint directly (no bing). Best-effort.

    Returns SearchResult dicts, or [] on any failure (so the caller can fall
    through to the original structured error).
    """
    try:
        from bs4 import BeautifulSoup

        params = [f"q={quote_plus(query)}"]
        if timelimit:
            params.append(f"df={timelimit}")          # d/w/m/y
        if region:
            params.append(f"kl={region}")             # e.g. us-en
        if safesearch == "off":
            params.append("kp=-2")
        elif safesearch == "on":
            params.append("kp=1")
        url = f"{_DDG_HTML_URL}?{'&'.join(params)}"

        resp = await fetch(url, timeout=8)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        out: list[dict] = []
        for res in soup.select("div.result"):
            if "result--ad" in (res.get("class") or []):
                continue
            a = res.select_one("a.result__a")
            if not a:
                continue
            real_url = _decode_ddg_href(a.get("href", ""))
            if not real_url:
                continue
            snippet_el = res.select_one(".result__snippet")
            out.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=real_url,
                    body=snippet_el.get_text(strip=True) if snippet_el else "",
                    published_date=best_effort_date(url=real_url),  # B14: URL date
                    source_tier=classify_source(real_url),
                ).model_dump()
            )
            if len(out) >= max_results:
                break
        return out
    except Exception:
        return []


def _decode_ddg_href(href: str) -> str:
    """Resolve a DDG result href to the real target URL.

    DDG wraps results as `//duckduckgo.com/l/?uddg=<encoded url>&rut=...`.
    Returns the decoded target, or the href itself if already direct, or "".
    """
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        q = parse_qs(urlparse(href).query)
        if "uddg" in q and q["uddg"]:
            return q["uddg"][0]
    except Exception:
        pass
    return href if href.startswith("http") else ""


# Near-duplicate detection (B16). Conservative: only flags HIGH-confidence
# title matches so it never collapses same-story-different-angle results
# (those carry corroboration value — see the Mitoma research run).
_DEDUP_THRESHOLD = 0.6  # Jaccard on significant title tokens
_STOPWORDS = frozenset(
    "the a an of for in on to and or vs is was are be by with from at as how "
    "why what when who new latest best top full list guide your you".split()
)


# CJK runs (kana + kanji). Japanese has no word spaces, so we can't word-split
# without a morphological analyzer (won't add that dep). Instead we emit
# character *bigrams* for CJK runs — a standard dependency-free way to get
# meaningful partial-overlap similarity. (B22, 2026-05-30: the ASCII-only
# tokenizer made `near_duplicate` a silent no-op for Japanese titles.)
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿々〆ヵヶ]+")


def _title_tokens(title: str) -> frozenset[str]:
    """Significant tokens of a title for near-duplicate comparison.

    - Latin/digit words: ≥3 chars, stopwords dropped (unchanged English behavior).
    - CJK runs: character bigrams (so Japanese/Chinese titles compare meaningfully).
    """
    t = (title or "").lower()
    tokens: set[str] = set()
    for w in re.findall(r"[a-z0-9]+", t):
        if len(w) >= 3 and w not in _STOPWORDS:
            tokens.add(w)
    for run in _CJK_RE.findall(t):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return frozenset(tokens)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _mark_near_duplicates(results: list[dict]) -> list[dict]:
    """Tag results whose title near-matches an earlier cluster's primary.

    Keeps everything (corroboration matters); only sets `near_duplicate`. The
    cluster primary (near_duplicate=False) prefers an `authoritative` source.
    """
    clusters: list[dict] = []  # each: {"tokens", "primary_idx"}
    for i, r in enumerate(results):
        toks = _title_tokens(r.get("title", ""))
        r["near_duplicate"] = False
        match = next(
            (c for c in clusters if _jaccard(toks, c["tokens"]) >= _DEDUP_THRESHOLD),
            None,
        )
        if match is None:
            clusters.append({"tokens": toks, "primary_idx": i})
            continue
        # This is a near-dup of an existing cluster.
        primary = results[match["primary_idx"]]
        this_auth = r.get("source_tier") == "authoritative"
        primary_auth = primary.get("source_tier") == "authoritative"
        if this_auth and not primary_auth:
            # Promote the authoritative copy to primary; demote the old one.
            primary["near_duplicate"] = True
            r["near_duplicate"] = False
            match["primary_idx"] = i
        else:
            r["near_duplicate"] = True
    return results


# Loose same-story clustering (B19). near_duplicate (Jaccard ≥ 0.6) catches
# near-identical titles, but different outlets paraphrase the SAME story so
# heavily that their headlines share only the key entities (e.g. the DuckDuckGo
# +30%-installs story ran across 8 outlets, none flagged). We link results that
# share ≥ _STORY_MIN_SHARED *significant* title tokens and surface the group as
# a CORROBORATION signal (story_cluster id), NOT a skip flag — same-story
# coverage from independent outlets is worth reading across; the id just tells
# the agent they aren't independent confirmations. A loose false grouping is
# therefore low-harm (the agent still reads them).
#
# B28: in a topic search every result shares the QUERY's tokens by construction
# (DDG returns matches), so clustering on raw shared tokens collapses the whole
# result set into one useless mega-cluster (live "EU AI Act enforcement 2026"
# run: 8/8 in cluster 1). The query's own tokens carry zero story-discrimination
# signal, so we strip them before comparing. Event coverage still clusters: the
# shared event entities (e.g. "Google"+"30%") exceed a short query and survive.
_STORY_MIN_SHARED = 2
# B28: a candidate cluster covering ≥ this fraction of the result set is topic
# homogeneity, not a story — suppressed (only when there are ≥ MIN results, so
# "majority" is meaningful). Genuine same-story *subsets* stay below the cap.
_STORY_MAX_CLUSTER_FRAC = 0.6
_STORY_DOMINANCE_MIN_N = 4


def _mark_story_clusters(results: list[dict], query: str | None = None) -> list[dict]:
    """Assign a `story_cluster` id to groups of ≥2 results that likely report
    the same story (≥ _STORY_MIN_SHARED shared significant title tokens,
    transitively unioned). Singletons keep story_cluster=None.

    `query` (B28): its significant tokens are excluded from the comparison — they
    are shared by every result by construction and would otherwise link the whole
    set. Omit it (None) to compare raw title tokens (back-compat)."""
    n = len(results)
    query_tokens = _title_tokens(query) if query else frozenset()
    toks = [_title_tokens(r.get("title", "")) - query_tokens for r in results]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # keep the lower index as root

    for i in range(n):
        for j in range(i + 1, n):
            if len(toks[i] & toks[j]) >= _STORY_MIN_SHARED:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    # B28: a cluster covering a large majority of the result set is topic
    # homogeneity (a single-topic search), not a story — it gives the agent no
    # differentiation, so suppress it. Only applied once there are enough results
    # for "majority" to mean something (small sets are left as-is). This is the
    # backstop for ubiquitous *non-query* topic words that query-exclusion can't
    # catch (live EU run: "august"/"compliance" chained all 8 → mega-cluster).
    dominance_cap = _STORY_MAX_CLUSTER_FRAC * n if n >= _STORY_DOMINANCE_MIN_N else n + 1

    cid = 0
    for root in sorted(groups):  # root == min member index → stable, ordered ids
        members = groups[root]
        if 2 <= len(members) < dominance_cap:
            cid += 1
            for m in members:
                results[m]["story_cluster"] = cid
    return results


def _ddgs_search_sync(
    query: str,
    region: str | None,
    safesearch: str,
    timelimit: str | None,
    max_results: int,
) -> list[dict]:
    """Synchronous DDGS call — runs in a thread via asyncio.to_thread."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import (
            DuckDuckGoSearchException,
            RatelimitException,
            TimeoutException,
        )

        try:
            ddgs = DDGS(headers=_DDGS_HEADERS)
            return ddgs.text(
                keywords=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
            ) or []
        except RatelimitException as exc:
            raise exc
        except TimeoutException as exc:
            raise exc
        except DuckDuckGoSearchException as exc:
            raise exc


def _map_ddgs_exception(exc: Exception, consecutive_failures: int = 0) -> str:
    """Map DDGS exceptions to StructuredError JSON strings.

    Persona A FRICTION-B1/B2/B3 fix:
      - Messages are sanitized (raw Bing URLs stripped) inside structured_error.
      - Hints are search-context-aware (no "check URL" since the caller
        passed a query, not a URL).
      - Transient connection errors (DNS / reset) are marked retryable=True
        so the agent doesn't give up on flaky networks.

    B13: `consecutive_failures` is this session's run of back-to-back failed
    searches. Once it crosses `_OUTAGE_THRESHOLD`, the backend is almost
    certainly down — so the hint stops suggesting query tweaks (futile during an
    outage) and tells the agent to switch strategy, and `retryable` flips to
    False to break reword-and-retry loops.
    """
    try:
        from duckduckgo_search.exceptions import (
            DuckDuckGoSearchException,
            RatelimitException,
            TimeoutException,
        )
    except ImportError:
        DuckDuckGoSearchException = Exception
        RatelimitException = type(None)
        TimeoutException = type(None)

    exc_str = str(exc)
    systemic = consecutive_failures >= _OUTAGE_THRESHOLD
    switch_strategy_hint = (
        f"{consecutive_failures} searches in a row have now failed — the search "
        "backend is unavailable (outage or sustained rate-limiting), NOT your "
        "query. Stop rewording: rephrasing won't help. Switch strategy — use "
        "results/sources you already have, call read_article on known URLs, or "
        "pause and retry in a few minutes."
    )

    if isinstance(exc, RatelimitException):
        return err.structured_error(
            err.RATE_LIMITED,
            f"DuckDuckGo rate limit exceeded: {exc_str}",
            hint_override=switch_strategy_hint if systemic else (
                "DuckDuckGo rate-limited this session. Wait 60s, "
                "or narrow the query with timelimit/region to reduce volume."
            ),
        )
    if isinstance(exc, TimeoutException):
        return err.structured_error(
            err.TIMEOUT,
            f"DuckDuckGo search timed out: {exc_str}",
            hint_override=switch_strategy_hint if systemic else (
                "Search backend timed out. Retry once; if searches keep failing "
                "it's the backend, not your query — switch strategy, don't reword."
            ),
            retryable_override=not systemic,
        )

    # Generic DDGS error or unexpected: detect transient sub-causes
    transient = err.is_transient_conn_error(exc_str)
    if isinstance(exc, DuckDuckGoSearchException):
        msg = f"DuckDuckGo backend error: {exc_str}"
    else:
        msg = f"Unexpected error during search: {exc_str}"

    if systemic:
        hint = switch_strategy_hint
    elif transient:
        hint = (
            "Search backend unreachable (likely transient network/DNS). Retry "
            "once; if searches keep failing it's the backend, not your query — "
            "stop rewording and switch strategy."
        )
    else:
        hint = (
            "Search backend error. A one-off may be query-specific (try "
            "suggest_queries for alternative phrasings); but if every search is "
            "failing it's the backend, not your query — switch strategy instead "
            "of rewording."
        )

    return err.structured_error(
        err.CONN_ERROR,
        msg,
        hint_override=hint,
        retryable_override=False if systemic else transient,
    )
