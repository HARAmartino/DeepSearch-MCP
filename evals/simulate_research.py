"""
E2E Research Simulation — Phase 4 (ROADMAP 4.1)

Simulates a ReAct-style Deep Research agent using DeepSearch-MCP tools directly
(no MCP transport layer required). Demonstrates a 4-step investigation loop:

  Step 1: Initial search for the research topic
  Step 2: Read top 2 articles in full
  Step 3: Detect coverage gaps → call suggest_queries
  Step 4: Follow-up search on a laterally-shifted query

Reports:
  - Character counts (token proxy: chars ÷ 4 ≈ tokens)
  - Error codes encountered and how the agent recovered
  - Source diversity (hostname variety)

Usage:
    python evals/simulate_research.py          # live network (default)
    python evals/simulate_research.py --demo   # pre-set realistic data (no network)

Requires the .venv to be active (or run via: .venv/bin/python evals/simulate_research.py).
Live network calls are made in default mode; results vary. Errors are handled gracefully.
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
import time
from urllib.parse import urlparse

# Ensure src/ is on the path when run from project root
sys.path.insert(0, ".")

DEMO_MODE = "--demo" in sys.argv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESEARCH_TOPIC = "MCP Model Context Protocol 2025 2026 trends"
RESEARCH_TOPIC_SHORT = "MCP Model Context Protocol"
MAX_ARTICLE_RESULTS = 5
MAX_FOLLOWUP_RESULTS = 5
CHAR_PER_TOKEN = 4  # rough approximation

# ---------------------------------------------------------------------------
# Pre-set realistic data for --demo mode
# ---------------------------------------------------------------------------

_DEMO_SEARCH_RESULTS = [
    {
        "title": "Model Context Protocol: The Emerging Standard for AI Tool Integration (2025)",
        "url": "https://blog.langchain.dev/mcp-emerging-standard-2025/",
        "body": (
            "Anthropic's Model Context Protocol (MCP) has seen explosive adoption in 2025, "
            "with over 2,000 community-built servers on GitHub. MCP standardizes how LLMs "
            "connect to tools, databases, and APIs using a JSON-RPC 2.0 message format over "
            "stdio or SSE transports. Major IDE vendors including VS Code and JetBrains have "
            "added native MCP support."
        ),
        "published_date": "2025-11-14",
        "score": None,
    },
    {
        "title": "MCP vs OpenAPI: Choosing the Right Integration Pattern for AI Agents",
        "url": "https://www.infoq.com/articles/mcp-vs-openapi-ai-agents/",
        "body": (
            "While OpenAPI describes REST endpoints, MCP describes *capabilities* — a higher "
            "abstraction suited to agentic workflows. MCP's stateful session model allows "
            "agents to maintain context across tool calls, which REST cannot do natively. "
            "However, MCP's binary dependency on stdio creates deployment challenges in "
            "serverless and containerized environments."
        ),
        "published_date": "2026-02-08",
        "score": None,
    },
    {
        "title": "Security Considerations in MCP Server Deployments — 2026 Analysis",
        "url": "https://research.nccgroup.com/2026/03/mcp-security-analysis/",
        "body": (
            "NCC Group's 2026 security audit of popular MCP servers identified three "
            "common vulnerability classes: tool-injection attacks (malicious tool descriptions "
            "hijacking agent behavior), excessive permission scopes, and lack of "
            "input sanitization in shell-executing servers. Recommendations include "
            "tool sandboxing and cryptographic server attestation."
        ),
        "published_date": "2026-03-21",
        "score": None,
    },
]

_DEMO_ARTICLE_1 = """\
---
title: "Model Context Protocol: The Emerging Standard for AI Tool Integration (2025)"
published_date: "2025-11-14"
url: "https://blog.langchain.dev/mcp-emerging-standard-2025/"
hostname: blog.langchain.dev
---

# Model Context Protocol: The Emerging Standard

MCP defines a client-server architecture where **MCP Hosts** (LLM applications like Claude
Desktop) connect to **MCP Servers** (tool providers) via a standardized protocol.

## Why MCP Won

Unlike previous attempts at AI tool standardization (OpenAI's Plugin API, LangChain's
ToolSpec), MCP succeeded because:

1. **Open specification** — maintained by Anthropic but community-governed via GitHub.
2. **Transport agnostic** — supports stdio (local), SSE, and WebSocket transports.
3. **Rich capability model** — Tools, Resources, and Prompts as first-class primitives.

## Adoption Milestones (2025)

| Month | Event |
|-------|-------|
| Jan 2025 | Claude Desktop ships MCP support |
| Mar 2025 | VS Code MCP extension: 500k installs |
| Jul 2025 | GitHub Copilot adds MCP server support |
| Oct 2025 | 1,000+ community servers on mcp.so registry |

## Key Technical Decisions

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_web",
    "arguments": {"query": "MCP adoption 2025"}
  }
}
```

The JSON-RPC 2.0 message format ensures compatibility with existing tooling while
the capability negotiation handshake prevents version mismatch errors at startup.
"""

_DEMO_ARTICLE_2 = """\
---
title: "MCP vs OpenAPI: Choosing the Right Integration Pattern for AI Agents"
published_date: "2026-02-08"
url: "https://www.infoq.com/articles/mcp-vs-openapi-ai-agents/"
hostname: www.infoq.com
---

# MCP vs OpenAPI: A Practical Comparison

## The Core Difference

OpenAPI describes *what an endpoint does*. MCP describes *what a capability provides
to an agent*. This distinction matters because:

- **OpenAPI** is request-response: stateless, document-centric.
- **MCP** is session-based: the server can push updates, stream results, and
  maintain context across multiple tool invocations.

## When to Use Each

| Scenario | Recommendation |
|----------|---------------|
| Public REST API | OpenAPI |
| Agent-native tool | MCP |
| Mixed (API + agent) | MCP with an OpenAPI bridge server |

## Limitations of MCP in 2026

The stateful session requirement creates friction in serverless deployments:
functions must maintain WebSocket connections or rely on stdio, which doesn't
compose well with auto-scaling infrastructure. Several teams are building
"stateless MCP" adapters to bridge this gap.
"""

_DEMO_SUGGESTIONS = [
    '"MCP Model Context Protocol" security risks',
    '"MCP Model Context Protocol" alternatives',
    '"MCP Model Context Protocol" problems limitations',
    '"MCP Model Context Protocol" site:github.com',
    '"MCP Model Context Protocol" site:arxiv.org OR site:research.google.com',
    '"MCP Model Context Protocol" 2025 OR 2026',
]

_DEMO_FOLLOWUP_RESULTS = [
    {
        "title": "Tool-Injection Attacks in MCP: A New Attack Vector for AI Agents",
        "url": "https://research.nccgroup.com/2026/03/mcp-tool-injection/",
        "body": "Researchers at NCC Group demonstrate how malicious MCP server descriptions can redirect agent behavior, bypassing safety guardrails.",
        "published_date": "2026-03-21",
        "score": None,
    },
    {
        "title": "MCP Security RFC: Cryptographic Server Attestation Proposal",
        "url": "https://github.com/modelcontextprotocol/specification/discussions/412",
        "body": "A community RFC proposing a PKI-based server attestation model to prevent man-in-the-middle attacks on MCP stdio connections.",
        "published_date": "2026-04-05",
        "score": None,
    },
    {
        "title": "Anthropic MCP Security Hardening Guide (2026)",
        "url": "https://modelcontextprotocol.io/docs/security/hardening",
        "body": "Official guidance on sandboxing MCP servers, minimal permission scopes, and input validation requirements for production deployments.",
        "published_date": "2026-04-18",
        "score": None,
    },
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _tok(chars: int) -> str:
    return f"~{chars // CHAR_PER_TOKEN:,} tokens ({chars:,} chars)"


def _hostname(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


def _is_error(result: str) -> tuple[bool, str]:
    try:
        data = json.loads(result)
        if isinstance(data, dict) and data.get("status") == "error":
            return True, data.get("code", "UNKNOWN")
    except (json.JSONDecodeError, AttributeError):
        pass
    return False, ""


def _sep(title: str = "", width: int = 70) -> None:
    if title:
        print(f"\n{'─' * 3} {title} {'─' * max(0, width - len(title) - 5)}")
    else:
        print("─" * width)


def _indent(text: str, prefix: str = "    ") -> str:
    return textwrap.indent(textwrap.shorten(text, width=300, placeholder=" [...]"), prefix)


def _report_summary(
    total_chars: int,
    sources_seen: set[str],
    errors_encountered: list[dict],
    step_timings: list[float],
) -> None:
    _sep("SIMULATION REPORT", width=70)

    print("\n  📊 Token Budget")
    print(f"     Total chars consumed : {total_chars:,}")
    print(f"     Approx token usage   : {total_chars // CHAR_PER_TOKEN:,} tokens")

    print(f"\n  🌐 Source Diversity ({len(sources_seen)} unique hosts)")
    for host in sorted(sources_seen):
        print(f"     • {host}")

    labels = ["Initial search", "Article #1", "Article #2", "suggest_queries", "Follow-up search"]
    if step_timings:
        print("\n  ⏱  Step Timings")
        for i, t in enumerate(step_timings):
            label = labels[i] if i < len(labels) else f"Step {i + 1}"
            print(f"     {label:<22}: {t:.2f}s")
        print(f"     {'Total':<22}: {sum(step_timings):.2f}s")

    if errors_encountered:
        print("\n  ⚠  Errors & Recovery")
        for e in errors_encountered:
            step = e.get("step", "?")
            code = e.get("code", "?")
            action = e.get("action", "")
            url = e.get("url", "")
            loc = f" ({_hostname(url)})" if url else ""
            print(f"     Step {step}{loc}: [{code}] → {action}")
    else:
        print("\n  ✓  No errors encountered — clean run!")

    print(f"\n  {'✅' if not errors_encountered else '🟡'} Research loop complete.")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Demo simulation (pre-set data, no network)
# ---------------------------------------------------------------------------

async def run_demo_simulation() -> None:
    print("=" * 70)
    print("  DeepSearch-MCP — E2E Research Simulation  [DEMO MODE]")
    print(f"  Topic: {RESEARCH_TOPIC!r}")
    print("  (Pre-set realistic data — run without --demo for live network)")
    print("=" * 70)

    total_chars = 0
    sources_seen: set[str] = set()
    errors_encountered: list[dict] = []
    step_timings: list[float] = []

    # Step 1: Initial search
    _sep("STEP 1 — Initial Search")
    print(f"  Query: {RESEARCH_TOPIC!r}")
    t0 = time.perf_counter()
    await asyncio.sleep(0.05)  # simulate network latency
    search_json = json.dumps(_DEMO_SEARCH_RESULTS, ensure_ascii=False)
    step_timings.append(time.perf_counter() - t0 + 0.82)
    total_chars += len(search_json)

    print(f"  ✓ {len(_DEMO_SEARCH_RESULTS)} results ({_tok(len(search_json))})")
    for i, r in enumerate(_DEMO_SEARCH_RESULTS, 1):
        host = _hostname(r["url"])
        sources_seen.add(host)
        snippet = textwrap.shorten(r.get("body", ""), width=90, placeholder="...")
        print(f"  [{i}] {r['title'][:65]}")
        print(f"       {host} | date={r.get('published_date', 'n/a')}")
        print(f"       {snippet}")

    # Step 2: Read top 2 articles
    _sep("STEP 2 — Article Extraction (top 2 URLs)")
    article_snippets: list[str] = []

    for url, article_text in [
        (_DEMO_SEARCH_RESULTS[0]["url"], _DEMO_ARTICLE_1),
        (_DEMO_SEARCH_RESULTS[1]["url"], _DEMO_ARTICLE_2),
    ]:
        print(f"\n  → Fetching: {url}")
        t0 = time.perf_counter()
        await asyncio.sleep(0.05)
        step_timings.append(time.perf_counter() - t0 + 1.34)
        total_chars += len(article_text)
        sources_seen.add(_hostname(url))
        body_preview = article_text[article_text.find("\n\n"):].strip()[:400]
        article_snippets.append(body_preview)
        print(f"  ✓ Extracted ({_tok(len(article_text))})")
        print(_indent(body_preview[:200]))

    # Step 3: suggest_queries
    _sep("STEP 3 — suggest_queries (echo-chamber detection)")
    context_for_suggest = " ".join(article_snippets)[:800]
    print(f"  Context length: {len(context_for_suggest)} chars")

    # Call the real suggest_queries (no network needed — it uses templates + entity extraction)
    t0 = time.perf_counter()
    from src.deepsearch_mcp.tools.suggest import _build_template_queries, _extract_entities
    template_qs = _build_template_queries(RESEARCH_TOPIC_SHORT)
    entity_qs = [f'"{e}" {RESEARCH_TOPIC_SHORT}' for e in _extract_entities(context_for_suggest)[:2]]
    suggested = []
    seen: set[str] = set()
    for q in (template_qs + entity_qs):
        if q.strip().lower() not in seen:
            seen.add(q.strip().lower())
            suggested.append(q.strip())
    suggested = suggested[:8]
    step_timings.append(time.perf_counter() - t0 + 0.03)
    suggest_json = json.dumps(suggested, ensure_ascii=False)
    total_chars += len(suggest_json)

    print(f"  ✓ {len(suggested)} query suggestions generated:")
    for i, q in enumerate(suggested, 1):
        print(f"    [{i}] {q}")

    followup_query = suggested[0]
    for q in suggested:
        if any(kw in q.lower() for kw in ["security", "criticism", "problems", "risk"]):
            followup_query = q
            break

    # Step 4: Follow-up search
    _sep("STEP 4 — Follow-Up Search (lateral angle)")
    print(f"  Query: {followup_query!r}")
    t0 = time.perf_counter()
    await asyncio.sleep(0.05)
    followup_json = json.dumps(_DEMO_FOLLOWUP_RESULTS, ensure_ascii=False)
    step_timings.append(time.perf_counter() - t0 + 0.91)
    total_chars += len(followup_json)

    print(f"  ✓ {len(_DEMO_FOLLOWUP_RESULTS)} results ({_tok(len(followup_json))})")
    for r in _DEMO_FOLLOWUP_RESULTS:
        host = _hostname(r["url"])
        sources_seen.add(host)
        print(f"    • {r['title'][:65]} [{host}]")

    _report_summary(total_chars, sources_seen, errors_encountered, step_timings)


# ---------------------------------------------------------------------------
# Live simulation (real network calls)
# ---------------------------------------------------------------------------

async def run_live_simulation() -> None:
    from src.deepsearch_mcp.tools.extractor import read_article
    from src.deepsearch_mcp.tools.search import search_web
    from src.deepsearch_mcp.tools.suggest import suggest_queries

    total_chars = 0
    sources_seen: set[str] = set()
    errors_encountered: list[dict] = []
    step_timings: list[float] = []

    print("=" * 70)
    print("  DeepSearch-MCP — E2E Research Simulation  [LIVE]")
    print(f"  Topic: {RESEARCH_TOPIC!r}")
    print("=" * 70)

    # Step 1: Initial search
    _sep("STEP 1 — Initial Search")
    print(f"  Query: {RESEARCH_TOPIC!r}")

    t0 = time.perf_counter()
    search_result = await search_web(query=RESEARCH_TOPIC, timelimit="y",
                                      max_results=MAX_ARTICLE_RESULTS)
    step_timings.append(time.perf_counter() - t0)
    total_chars += len(search_result)

    is_err, err_code = _is_error(search_result)
    if is_err:
        errors_encountered.append({"step": 1, "code": err_code, "action": "abort"})
        print(f"  ⚠ Search error [{err_code}] — cannot continue. Try --demo mode.")
        _report_summary(total_chars, sources_seen, errors_encountered, step_timings)
        return

    search_data = json.loads(search_result)
    if not search_data:
        print("  ⚠ No results — try removing timelimit or different query.")
        return

    print(f"  ✓ {len(search_data)} results ({_tok(len(search_result))})")
    for i, r in enumerate(search_data, 1):
        host = _hostname(r["url"])
        sources_seen.add(host)
        snippet = textwrap.shorten(r.get("body", ""), width=90, placeholder="...")
        print(f"  [{i}] {r['title'][:65]}")
        print(f"       {host} | date={r.get('published_date', 'n/a')}")
        print(f"       {snippet}")

    # Step 2: Read top 2 articles
    _sep("STEP 2 — Article Extraction (top 2 URLs)")
    article_snippets: list[str] = []
    articles_read = 0

    for r in search_data[:4]:
        if articles_read >= 2:
            break
        url = r["url"]
        print(f"\n  → Fetching: {url}")

        t0 = time.perf_counter()
        article_result = await read_article(url=url)
        step_timings.append(time.perf_counter() - t0)
        total_chars += len(article_result)

        is_err, err_code = _is_error(article_result)
        if is_err:
            hint = ""
            try:
                hint = json.loads(article_result).get("hint", "")
            except Exception:
                pass
            errors_encountered.append({"step": 2, "url": url, "code": err_code,
                                        "action": "skip, try next"})
            print(f"  ⚠ [{err_code}] — skipping. Hint: {hint}")
            continue

        articles_read += 1
        sources_seen.add(_hostname(url))
        body_start = article_result.find("\n\n")
        body_preview = article_result[body_start:body_start + 400].strip()
        article_snippets.append(body_preview)
        print(f"  ✓ Extracted ({_tok(len(article_result))})")
        print(_indent(body_preview[:200]))

    if articles_read == 0:
        article_snippets = [r.get("body", "") for r in search_data[:3]]

    # Step 3: suggest_queries
    _sep("STEP 3 — suggest_queries (echo-chamber detection)")
    context_for_suggest = " ".join(article_snippets)[:800]
    print(f"  Context length: {len(context_for_suggest)} chars")

    t0 = time.perf_counter()
    suggest_result = await suggest_queries(topic=RESEARCH_TOPIC_SHORT,
                                           context=context_for_suggest)
    step_timings.append(time.perf_counter() - t0)
    total_chars += len(suggest_result)

    suggested = json.loads(suggest_result)
    print(f"  ✓ {len(suggested)} query suggestions generated:")
    for i, q in enumerate(suggested, 1):
        print(f"    [{i}] {q}")

    followup_query = suggested[0]
    for q in suggested:
        if any(kw in q.lower() for kw in ["criticism", "problems", "alternatives",
                                            "security", "risk", "limitation", "vs "]):
            followup_query = q
            break

    # Step 4: Follow-up search
    _sep("STEP 4 — Follow-Up Search (lateral angle)")
    print(f"  Query: {followup_query!r}")

    t0 = time.perf_counter()
    followup_result = await search_web(query=followup_query, timelimit="y",
                                        max_results=MAX_FOLLOWUP_RESULTS)
    step_timings.append(time.perf_counter() - t0)
    total_chars += len(followup_result)

    is_err, err_code = _is_error(followup_result)
    if is_err:
        errors_encountered.append({"step": 4, "code": err_code, "action": "report and finish"})
        print(f"  ⚠ Follow-up error [{err_code}]")
    else:
        followup_data = json.loads(followup_result)
        print(f"  ✓ {len(followup_data)} results ({_tok(len(followup_result))})")
        for r in followup_data:
            sources_seen.add(_hostname(r["url"]))
            print(f"    • {r['title'][:65]} [{_hostname(r['url'])}]")

    _report_summary(total_chars, sources_seen, errors_encountered, step_timings)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if DEMO_MODE:
        asyncio.run(run_demo_simulation())
    else:
        asyncio.run(run_live_simulation())
