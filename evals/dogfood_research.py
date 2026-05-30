"""
Real-world dogfooding session — DeepSearch-MCP using its own tools.

The script plays the role of an autonomous research agent investigating:
  "2025-2026 AI agent framework hegemony (LangGraph / CrewAI / AutoGen) and
   the impact of MCP on standardization — including critical perspectives
   (security risks, vendor lock-in)."

Telemetry is REAL: every tool call goes through `@track`, every row lands
in `${DEEPSEARCH_TELEMETRY_DIR}/telemetry.db`.

Network constraints (sandbox):
  - `search_web` calls hit the real DDGS backend; in restricted environments
    they fail with CONN_ERROR. That failure IS data — agents must recover.
  - `read_article` calls on inline HTML fixtures use `patch(fetch, ...)` so
    the extractor pipeline runs end-to-end against realistic 2026-style noise.

Output:
  - Console: agent's chain of thought + observed pain points.
  - DB: rows visible to `evals/analyze_telemetry.py` for SRE analysis.

Run:
    python evals/dogfood_research.py
    DEEPSEARCH_TELEMETRY_DIR=./.cache_dogfood python evals/dogfood_research.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Enable telemetry BEFORE importing tool modules — @track reads env at call time
os.environ["DEEPSEARCH_TELEMETRY"] = "1"
os.environ.setdefault("DEEPSEARCH_TELEMETRY_DIR", "./.cache_dogfood")

sys.path.insert(0, ".")
sys.path.insert(0, "evals")

from dogfood_audit import audit_report  # noqa: E402

from src.deepsearch_mcp.core import telemetry  # noqa: E402
from src.deepsearch_mcp.tools.extractor import read_article  # noqa: E402
from src.deepsearch_mcp.tools.search import search_web  # noqa: E402
from src.deepsearch_mcp.tools.suggest import suggest_queries  # noqa: E402

# ---------------------------------------------------------------------------
# Realistic HTML fixtures (2026-era pages with currently-uncaught noise)
# ---------------------------------------------------------------------------

# TechCrunch-style: newsletter CTA + consent gate + recommendation rail
TECHCRUNCH_HTML = """<!DOCTYPE html>
<html><head>
<title>The AI Agent Framework Wars: LangGraph vs CrewAI vs AutoGen | TechCrunch</title>
<meta name="author" content="Maria Santos">
<meta property="article:published_time" content="2026-04-12">
</head>
<body>
<nav>Home | Startups | AI | Venture</nav>
<article>
<h1>The AI Agent Framework Wars: LangGraph vs CrewAI vs AutoGen</h1>
<p class="meta">By Maria Santos | April 12, 2026 | 8 min read</p>

<p>The autumn of 2026 has seen an unprecedented battle for the soul of the
autonomous agent stack. Three frameworks now dominate production deployments:
LangChain's LangGraph, the community-driven CrewAI, and Microsoft's AutoGen.
Each takes a fundamentally different stance on how agents should be authored,
orchestrated, and observed.</p>

<h2>LangGraph: The Graph-First Approach</h2>
<p>LangGraph models agent workflows as explicit state machines with typed
edges between nodes. This gives developers predictable control flow at the
cost of more boilerplate. Major adopters include Notion, Stripe, and several
Fortune 500 banks that need auditable agent behavior.</p>

<h2>CrewAI: Role-Based Choreography</h2>
<p>CrewAI takes an opposite stance: instead of explicit graphs, you declare
agent "roles" (Researcher, Writer, Critic) and the framework handles delegation.
Startups love it for speed of iteration; enterprises worry about determinism.</p>

<h2>AutoGen: Multi-Agent Conversations</h2>
<p>Microsoft's AutoGen treats every interaction as a multi-agent conversation,
with each agent free to message any other. This is the most flexible model but
hardest to debug at scale.</p>

<h2>Where MCP Fits</h2>
<p>The Model Context Protocol has emerged as the unifying tool layer underneath
all three. By Q2 2026, LangGraph, CrewAI, and AutoGen had all shipped MCP
client integrations, letting agents share the same vetted tool catalog
regardless of orchestration framework.</p>

<!-- noise: newsletter CTA -->
<aside class="newsletter-cta">
  <h3>Get the latest in AI, delivered to your inbox</h3>
  <p>Sign up for our daily AI briefing.</p>
  <form><input type="email" placeholder="email@example.com"><button>Sign up</button></form>
  <p class="consent">By signing up, you agree to our Terms and Privacy Policy. You may unsubscribe at any time.</p>
</aside>

<h2>The Verdict</h2>
<p>Most production teams in 2026 don't pick a single framework — they wrap
agents in whichever orchestrator fits the use case and rely on MCP for tool
portability. The "framework war" is increasingly a non-issue at the
infrastructure layer.</p>

<!-- noise: estimated reading time + reporter card -->
<div class="reporter-bio">
  <p>Estimated reading time: 8 minutes</p>
  <p>Written by Maria Santos — Senior AI Correspondent</p>
  <p>Read more from Maria Santos</p>
</div>

<!-- noise: recommendation rail -->
<div class="related-content">
  <h3>More from TechCrunch</h3>
  <ul>
    <li><a href="/article1">Anthropic launches Claude 5 with native MCP support</a></li>
    <li><a href="/article2">OpenAI Realtime API hits 1B daily calls</a></li>
    <li><a href="/article3">The death of LangChain's framework era?</a></li>
  </ul>
</div>

<!-- noise: podcast / audio CTA -->
<div class="podcast-promo">
  <p>Listen to this article on the TechCrunch Daily Podcast.</p>
  <button>Play audio</button>
</div>
</article>

<footer>© 2026 TechCrunch. All rights reserved. Privacy Policy | Terms of Use</footer>
</body></html>"""


# LangChain blog-style: continue-reading gate + author rail
LANGCHAIN_HTML = """<!DOCTYPE html>
<html><head>
<title>Why LangGraph wins for production AI agents (2026 update)</title>
<meta name="author" content="Harrison Chase">
<meta property="article:published_time" content="2026-03-08">
</head>
<body>
<header><nav>Home | Blog | Docs | Cookbook</nav></header>
<article>
<h1>Why LangGraph wins for production AI agents (2026 update)</h1>
<p class="byline">By Harrison Chase · March 8, 2026 · 12 min read</p>

<p>Over the past year we've watched thousands of teams deploy LangGraph in
production. The patterns that emerge from those deployments are clear: agents
that survive contact with real users are graphs, not conversations. This post
distills what we learned and where LangGraph is heading next.</p>

<h2>The State-Machine Mindset</h2>
<p>Every production agent eventually becomes a state machine — the only
question is whether the state machine is explicit or accidental. LangGraph
forces you to declare it up front, which feels heavy for prototypes but pays
off enormously once the agent is on call.</p>

<h2>Why CrewAI's Role-Based Model Fights Production</h2>
<p>CrewAI's role-based approach is elegant in demos but breaks at scale: as
the agent count grows, the delegation graph becomes nondeterministic. Teams
report difficulty reproducing failure modes and high token costs from agents
repeatedly clarifying intent with each other.</p>

<h2>The MCP Bridge</h2>
<p>LangGraph 0.5 ships native MCP client support. Tools defined in any MCP
server (search, retrieval, custom domain APIs) become available to LangGraph
nodes without per-framework adapter code.</p>

<!-- noise: continue-reading gate -->
<div class="continue-reading-gate">
  <p>Continue reading to see the production deployment checklist.</p>
  <button>Continue reading</button>
</div>

<h2>Production Deployment Checklist</h2>
<ul>
  <li>Use TypedDict state schemas for every agent.</li>
  <li>Wrap every external tool in a retry-with-backoff node.</li>
  <li>Log every node entry/exit to a structured store.</li>
  <li>Set per-node token budgets to catch runaway loops early.</li>
</ul>

<!-- noise: tags + author card + recommended posts -->
<div class="post-meta">
  <p>Tags: LangGraph, Production, AI Agents, MCP</p>
  <p>Posted in: Engineering Blog</p>
</div>

<div class="author-bio">
  <h4>About the author</h4>
  <p>Harrison Chase is the co-founder of LangChain.</p>
  <p>Follow him on Twitter @hwchase17</p>
</div>

<div class="recommended">
  <h4>You might also like</h4>
  <ul>
    <li><a href="/post1">LangGraph 0.5 release notes</a></li>
    <li><a href="/post2">Migrating from LangChain to LangGraph</a></li>
  </ul>
</div>

</article>
<footer>© 2026 LangChain. Privacy Policy | Terms</footer>
</body></html>"""


# DEV.to-style: clean baseline (control case)
DEVTO_HTML = """<!DOCTYPE html>
<html><head>
<title>Benchmarking AutoGen vs LangGraph for tool-heavy workflows</title>
<meta name="author" content="Sample Dev">
<meta property="article:published_time" content="2026-04-20">
</head>
<body>
<article>
<h1>Benchmarking AutoGen vs LangGraph for tool-heavy workflows</h1>
<p class="meta">By Sample Dev · April 20, 2026 · 6 min read</p>

<p>I spent last month porting a 12-tool workflow from AutoGen to LangGraph
and back. Here are the latency, token, and observability numbers that
mattered for our production deployment.</p>

<h2>Setup</h2>
<p>Both frameworks pointed at the same MCP server (deepsearch-mcp, ironically),
the same set of 12 tools, and the same gpt-4.1-mini-2026 model. Each test
scenario ran 100 iterations on identical inputs.</p>

<h2>Latency Numbers</h2>
<p>LangGraph had a p50 of 4.2 seconds; AutoGen averaged 6.1 seconds. The
difference came almost entirely from AutoGen's inter-agent chatter
overhead.</p>

<h2>Token Costs</h2>
<p>LangGraph used 38% fewer tokens per scenario, primarily because state
machine transitions are deterministic and don't require LLM-mediated
delegation.</p>

<h2>Observability</h2>
<p>Both frameworks now ship OpenTelemetry integrations. LangGraph's spans
align cleanly with node boundaries; AutoGen's are harder to interpret
when multiple agents are speaking concurrently.</p>

<h2>Conclusion</h2>
<p>For tool-heavy workflows in 2026, LangGraph is the safer production
choice. AutoGen remains compelling for exploration and prototyping.</p>
</article>
</body></html>"""


# ZDNet-style review: affiliate disclosure + social counts + comment rail.
# Added 2026-05-29 to exercise the noise-leak auditor against patterns the
# v2 cleaner did NOT yet catch (affiliate links, "N shares", "view all N
# comments"). See LESSONS.md "Noise-Leak Auditor" entry.
ZDNET_HTML = """<!DOCTYPE html>
<html><head>
<title>I tested LangGraph, CrewAI and AutoGen for 30 days — here's the winner</title>
<meta name="author" content="Jordan Lee">
<meta property="article:published_time" content="2026-05-02">
</head>
<body>
<nav>Home | Reviews | AI | Best Picks</nav>
<article>
<h1>I tested LangGraph, CrewAI and AutoGen for 30 days — here's the winner</h1>
<p class="byline">By Jordan Lee | May 2, 2026</p>

<p>This article may contain affiliate links. If you buy through them we may earn a commission.</p>

<p>Over the last month I rebuilt the same customer-support agent three times,
once in each of the major 2026 frameworks, and measured developer experience,
runtime cost, and how easily each one integrated with external tools over MCP.
The differences were larger than the marketing suggests.</p>

<h2>Developer Experience</h2>
<p>LangGraph's explicit graph definitions felt verbose on day one but saved
hours of debugging by day ten. CrewAI was the fastest to a working prototype.
AutoGen sat in the middle: flexible, but its multi-agent chatter was hard to
trace without extra tooling.</p>

<h2>Cost and Performance</h2>
<p>Measured over identical workloads, CrewAI's role delegation produced the
highest token bills, while LangGraph's deterministic transitions kept costs
predictable. AutoGen's costs varied wildly with conversation depth.</p>

<h2>MCP Integration</h2>
<p>All three now speak the Model Context Protocol, but the integration depth
differs. LangGraph treats MCP tools as first-class nodes; CrewAI wraps them as
agent capabilities; AutoGen exposes them as callable functions in the
conversation. Vendor lock-in is lowest when you keep tools behind MCP.</p>

<h2>The Verdict</h2>
<p>For a production support agent in 2026, LangGraph took the win on
maintainability and cost. CrewAI remains my pick for hackathons.</p>

<!-- noise the v2 cleaner does NOT yet catch -->
<div class="social-bar">
  <p>Share this article</p>
  <p>1.2K shares</p>
</div>
<div class="comments-rail">
  <p>View all 23 comments</p>
</div>
<div class="trending">
  <h3>Trending Now</h3>
  <ul>
    <li><a href="/a">The best laptops for developers in 2026</a></li>
    <li><a href="/b">OpenAI vs Anthropic: the 2026 enterprise showdown</a></li>
  </ul>
</div>
</article>
<footer>© 2026 ZDNet. All rights reserved.</footer>
</body></html>"""


# ---------------------------------------------------------------------------
# Mock helper
# ---------------------------------------------------------------------------

def make_mock_response(html: str, status: int = 200, content_type: str = "text/html") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    resp.headers = {"content-type": content_type}
    return resp


# ---------------------------------------------------------------------------
# Research workflow
# ---------------------------------------------------------------------------

RESEARCH_TOPIC = (
    "2025-2026 AI agent framework hegemony LangGraph CrewAI AutoGen "
    "MCP standardization security risks vendor lock-in"
)

INITIAL_QUERIES = [
    "LangGraph vs CrewAI vs AutoGen 2026 production",
    "MCP Model Context Protocol framework standardization",
    "AI agent framework security vulnerabilities 2026",
    "AI agent framework vendor lock-in criticism",
]

# (URL, optional HTML fixture). If HTML is None, the real fetch runs
# (will fail in sandbox → real CONN_ERROR / UNSUPPORTED_FORMAT telemetry).
URLS = [
    # PDFs — should be rejected by UNSUPPORTED_FORMAT guard
    ("https://arxiv.org/pdf/2606.12345.pdf", None),
    ("https://research.langchain.com/whitepaper-langgraph-0.5.pdf", None),
    # Real-looking HTML pages with noise (mocked)
    ("https://techcrunch.com/2026/04/12/ai-agent-framework-wars/", TECHCRUNCH_HTML),
    ("https://blog.langchain.dev/why-langgraph-wins-2026/", LANGCHAIN_HTML),
    ("https://dev.to/sample/autogen-vs-langgraph-benchmarks", DEVTO_HTML),
    ("https://www.zdnet.com/article/langgraph-crewai-autogen-30-day-test/", ZDNET_HTML),
    # Live URL with no mock — will hit real network (fail in sandbox)
    ("https://www.anthropic.com/news/mcp-2026-update", None),
]

TOPICS_FOR_SUGGEST = [
    "AI agent framework",
    "MCP Model Context Protocol",
    "LangGraph vs CrewAI",
]


def _short_status(result: str) -> tuple[str, int]:
    """Return (status_label, char_count)."""
    try:
        data = json.loads(result)
        if isinstance(data, dict) and data.get("status") == "error":
            return (f"ERROR:{data.get('code', '?')}", len(result))
        if isinstance(data, list):
            return (f"OK:{len(data)} items", len(result))
    except Exception:
        pass
    return ("OK:body", len(result))


async def dogfood() -> None:
    print("═" * 72)
    print("  🤖 DOGFOODING SESSION — DeepSearch-MCP as a Research Agent")
    print(f"  Topic: {RESEARCH_TOPIC[:60]}…")
    print(f"  Telemetry DB: {telemetry.get_db_path()}")
    print("═" * 72)

    # Reset DB for a clean session
    await telemetry.reset_for_tests()

    # ── Step 1: Initial searches ───────────────────────────────────────────
    print("\n[STEP 1] Initial searches (broad-net coverage)")
    for q in INITIAL_QUERIES:
        result = await search_web(query=q, timelimit="y", max_results=5)
        label, n = _short_status(result)
        print(f"  search_web {q[:50]:50}  → {label} ({n} chars)")

    # ── Step 2: Read articles ──────────────────────────────────────────────
    print("\n[STEP 2] Article extraction (PDFs + HTML mix)")
    successful_extractions: list[tuple[str, str]] = []  # (url, body) for the auditor
    for url, html in URLS:
        if html is None:
            # Either a PDF (will short-circuit) or a live fetch (will fail)
            result = await read_article(url=url)
        else:
            with patch(
                "src.deepsearch_mcp.tools.extractor.fetch", new_callable=AsyncMock
            ) as mock_fetch:
                mock_fetch.return_value = make_mock_response(html)
                result = await read_article(url=url)
        label, n = _short_status(result)
        print(f"  read_article {url[:55]:55}  → {label} ({n} chars)")
        if label == "OK:body":
            successful_extractions.append((url, result))

    # ── Step 3: Echo-chamber detection ─────────────────────────────────────
    print("\n[STEP 3] suggest_queries — lateral angles")
    for topic in TOPICS_FOR_SUGGEST:
        result = await suggest_queries(
            topic=topic,
            context="LangGraph CrewAI AutoGen production comparison",
        )
        label, n = _short_status(result)
        print(f"  suggest_queries {topic:40}  → {label} ({n} chars)")

    # ── Step 4: Noise-Leak Audit (the systematic CHECK step) ────────────────
    # Every successful extraction is scanned for residual noise the cleaner
    # missed. This replaces the old "human reads the whole body and hopes to
    # notice" step with a reproducible shortlist. See evals/dogfood_audit.py.
    print("\n[STEP 4] Noise-leak audit (post-cleaner residual scan)")
    total_suspected = 0
    for url, body in successful_extractions:
        block, n = audit_report(url, body)
        print(block)
        total_suspected += n
    if total_suspected:
        print(f"\n  ⚠ {total_suspected} suspected noise line(s) — triage and patch "
              f"utils/cleaner.py or add a domain adapter (see METHODOLOGY.md §3 Rule 1/2).")
    else:
        print("\n  ✅ No residual noise across all extractions.")

    # Flush all fire-and-forget telemetry writes
    await telemetry.drain()
    print("\n✓ All telemetry rows flushed.")
    print(f"  Next: uv run python evals/analyze_telemetry.py "
          f"(with DEEPSEARCH_TELEMETRY_DIR={os.environ['DEEPSEARCH_TELEMETRY_DIR']})")
    print("═" * 72)


if __name__ == "__main__":
    asyncio.run(dogfood())
