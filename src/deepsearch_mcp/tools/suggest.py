"""MCP Tool: suggest_queries — generate diverse search queries to break research dead-ends.

Design rationale:
  Primary:  DDG Autocomplete API (https://duckduckgo.com/ac/?q=<topic>)
            Returns real user search patterns, most relevant to the topic.
  Fallback: Template-based viewpoint-shifting queries (runs always as enrichment).
            Provides criticism/alternatives/primary-source angles even when
            autocomplete returns few results or is unavailable.

DDGS v8 has NO built-in suggestions method — only text/news/images/videos.
The /ac/ endpoint is DDG's public autocomplete API, called directly via curl_cffi.

Output is a deduplicated list of 3–8 query strings ready to pass to search_web.
"""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import quote_plus

from mcp.server.fastmcp import FastMCP

from ..core.http import fetch
from ..core.telemetry import track

mcp = FastMCP("deepsearch-suggest-queries")

_AC_URL = "https://duckduckgo.com/ac/"
_AC_TIMEOUT = 5  # Fast endpoint; fail quickly and fall back to templates

# Viewpoint-shifting template queries for breaking echo chambers.
# The "{topic}" placeholder is rendered with smart quoting in _render_topic():
#   - ≤2 words: wrapped in quotes for precise phrase targeting
#   - ≥3 words: rendered bare so DDG can apply per-word ranking
# (a 6-word phrase in quotes would produce zero hits — see Persona A FRICTION-C1)
#
# Order matters: temporal freshness is ranked early because most real research
# tasks are time-bounded (Persona A FRICTION-C3).
# RESERVED templates are the echo-chamber differentiators that MUST survive the
# 8-result cap, even when live autocomplete returns a full set of (often noisy)
# phrases — for a person, real autocomplete is tabloid noise like "net worth /
# husband / age" (Sam Altman run, 2026-05-30). B11: guarantee that ≥1 criticism
# AND ≥1 primary-source angle always reach the agent, since that is the tool's
# actual mission (breaking echo chambers), not surfacing popular queries.
_RESERVED_TEMPLATES = [
    "{topic} 2025 OR 2026",       # temporal freshness (most research is time-bound)
    "{topic} criticism",          # criticism angle (guaranteed)
    "{topic} alternatives",       # alternative viewpoints
    "{topic} site:github.com",    # primary source (guaranteed)
]
# EXTRA templates fill any slots left after reserved + a capped share of
# autocomplete + context entities. Dropped first when the cap is tight.
_EXTRA_TEMPLATES = [
    "{topic} problems limitations",
    "{topic} vs",
    "{topic} site:arxiv.org OR site:research.google.com",
]
# Full set, reserved first (kept for back-compat / _build_template_queries).
_VIEWPOINT_TEMPLATES = _RESERVED_TEMPLATES + _EXTRA_TEMPLATES

# Autocomplete is enrichment, not the mission: cap its share so it cannot crowd
# the reserved templates out of the 8-result window (B11).
_AC_BUDGET = 3
_MAX_RESULTS = 8

# Word count above which quote-wrapping causes empty result sets
_QUOTE_WORD_LIMIT = 2

# For snippet-based entity extraction (capitalize-word heuristic)
_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*)\b")
_STOP_WORDS = frozenset(
    "The A An In On At To For Of With And Or But Is Are Was Were Be Been"
    " Being Have Has Had Do Does Did Will Would Could Should May Might Must"
    " Shall Can This That These Those It Its We They He She You I".split()
)


@mcp.tool()
@track(tool_name="suggest_queries", primary_input="topic")
async def suggest_queries(
    topic: str,
    context: str | None = None,
) -> str:
    """
    Suggests 3–8 diverse search queries to escape research dead-ends.

    ## USE WHEN
    - **Stuck in an echo chamber:** last 2+ `search_web` rounds returned the
      same sources or all praise/criticism with no counter-perspective.
    - **Initial results are poor:** few hits, or all from low-quality SEO blogs.
    - **Starting a deep research loop:** call once up-front to pre-plan a
      diverse query set covering criticism, alternatives, and primary sources.

    ## DO NOT USE WHEN
    - You already have a clear targeted query → call `search_web` directly.
    - You need actual results — this tool generates queries, not answers.

    ## PARAMETERS
    - `topic`: The **core concept** (1–4 words is ideal: "React Server Components",
      "CRISPR base editing", "MCP servers"). Long phrases (>2 words) will not be
      quote-wrapped — they will be passed as bare keywords to maximize recall.
    - `context`: Optional. 1–3 search snippets from results you've already seen.
      Proper-noun entities are extracted for drill-down queries (e.g. seeing
      "Stanford" in snippets yields a `"Stanford" <topic>` query).

    ## RETURNS
    JSON array of 3–8 query strings. Live autocomplete is **capped** so it can
    never crowd out the echo-chamber differentiators — for a person, real
    autocomplete is often tabloid noise ("net worth", "husband"). The output
    always reserves slots for ≥1 criticism and ≥1 primary-source angle:
    1. DDG autocomplete (real user patterns), if available — capped to the top 3
    2. Temporal-freshness ("2025 OR 2026") — first template because most research is time-bound
    3. Criticism angle — **always present** (breaks echo chambers)
    4. Alternatives angle
    5. Primary-source `site:github.com` — **always present**
    6. Entity drill-downs from context, then overflow templates (`problems
       limitations`, `vs`, `site:arxiv.org`) and any leftover autocomplete

    ## EXAMPLES (Few-Shot)

    Good (short topic, quote-wrapped for precision):
      topic="CRISPR"
      → ['"CRISPR" 2025 OR 2026', '"CRISPR" criticism', '"CRISPR" alternatives',
         '"CRISPR" site:arxiv.org OR site:research.google.com', ...]

    Good (long topic, bare keywords for recall):
      topic="AI agent memory management"
      → ["AI agent memory management 2025 OR 2026",
         "AI agent memory management criticism",
         "AI agent memory management alternatives",
         "AI agent memory management site:github.com", ...]

    Good (with context — entity drill-down):
      topic="fasting", context="Stanford study on metabolism..."
      → [..., '"Stanford" fasting', ...]

    Bad (full sentence — use search_web instead):
      topic="what is machine learning"
    """
    topic = topic.strip()
    if not topic:
        return json.dumps([], ensure_ascii=False)

    # Run autocomplete and template generation concurrently
    ac_task = asyncio.create_task(_fetch_autocomplete(topic))
    reserved_queries = _build_template_queries(topic, _RESERVED_TEMPLATES)
    extra_queries = _build_template_queries(topic, _EXTRA_TEMPLATES)

    ac_suggestions = await ac_task

    # Entity extraction from context snippets (optional enrichment).
    # Quote the entity (proper noun → precision) but leave the topic bare.
    entity_queries: list[str] = []
    if context and context.strip():
        entities = _extract_entities(context)
        clean_topic = topic.strip().strip('"').strip("'")
        entity_queries = [f'"{e}" {clean_topic}' for e in entities[:2]]

    # Merge: autocomplete first, then viewpoint templates, then entities
    combined: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        normalized = q.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            combined.append(q.strip())

    # 1. Autocomplete — real user patterns, but CAPPED (B11): a full set of AC
    #    phrases must not crowd the reserved differentiator templates out of the
    #    8-result window. AC stays first (it can surface useful sub-topics), but
    #    only its top _AC_BUDGET; the rest is overflow.
    for q in ac_suggestions[:_AC_BUDGET]:
        _add(q)

    # 2. Reserved viewpoint templates — GUARANTEED to survive the cap, because
    #    capped-AC (≤3) + reserved (4) ≤ 7 < _MAX_RESULTS. This is what keeps
    #    ≥1 criticism + ≥1 primary-source angle reaching the agent.
    for q in reserved_queries:
        _add(q)

    # 3. Entity drill-downs from context.
    for q in entity_queries:
        _add(q)

    # 4. Fill any remaining slots: extra templates first, then leftover AC.
    for q in extra_queries + ac_suggestions[_AC_BUDGET:]:
        _add(q)

    # Return 3–8 results
    output = combined[:_MAX_RESULTS] if len(combined) >= 3 else combined
    if len(output) < 3:
        # Ensure minimum 3 by adding basic templates even if duplicates
        for q in [f"{topic} tutorial", f"{topic} examples", f"{topic} documentation"]:
            if len(output) >= 3:
                break
            if q not in output:
                output.append(q)

    return json.dumps(output, ensure_ascii=False)


def _autocomplete_url(topic: str) -> str:
    """Build the DDG autocomplete request URL WITH the query term.

    BUG history (found 2026-05-30 by real-usage PDCA): this previously fetched
    the bare endpoint with no `?q=`, so the topic was never sent — autocomplete
    silently returned [] forever and the feature was dead. The Stuck Agent
    tests mocked `_fetch_autocomplete` itself, so they never exercised this.

    NOTE: plain `?q=` returns `[{"phrase": "..."}]` (what the parser expects).
    Do NOT add `&type=list` — that switches the response to the OpenSearch
    shape `["query", [...]]`, which the parser can't read (verified live).
    """
    return f"{_AC_URL}?q={quote_plus(topic)}"


async def _fetch_autocomplete(topic: str) -> list[str]:
    """Call DDG /ac/ autocomplete endpoint. Returns up to 4 suggestions."""
    try:
        resp = await fetch(
            _autocomplete_url(topic),
            headers={
                "Accept": "application/json",
                "Referer": "https://duckduckgo.com/",
            },
            timeout=_AC_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = json.loads(resp.text)
        # Response: [{"phrase": "..."}, ...]
        phrases = [item["phrase"] for item in data if isinstance(item, dict) and "phrase" in item]
        # Skip the trivial exact-match first result
        if phrases and phrases[0].lower() == topic.lower():
            phrases = phrases[1:]
        return phrases[:4]
    except Exception:
        # Best-effort enrichment: any failure (network, JSON, schema) → templates.
        return []


def _render_topic(topic: str) -> str:
    """Render the topic for template substitution with smart quoting.

    Short topics (≤2 words) are wrapped in quotes for precise targeting.
    Longer topics are rendered bare to avoid zero-result phrase searches.
    """
    clean = topic.strip().strip('"').strip("'")
    word_count = len(clean.split())
    if word_count <= _QUOTE_WORD_LIMIT and word_count >= 1:
        return f'"{clean}"'
    return clean


def _build_template_queries(
    topic: str, templates: list[str] | None = None
) -> list[str]:
    """Build viewpoint-shifting queries from the topic string.

    `templates` defaults to the full viewpoint set; callers pass
    `_RESERVED_TEMPLATES` / `_EXTRA_TEMPLATES` to render each tier separately.
    """
    rendered = _render_topic(topic)
    return [t.format(topic=rendered) for t in (templates or _VIEWPOINT_TEMPLATES)]


def _extract_entities(context: str) -> list[str]:
    """Extract proper nouns from context snippets for entity drill-down."""
    matches = _PROPER_NOUN_RE.findall(context)
    seen: set[str] = set()
    entities: list[str] = []
    for m in matches:
        words = m.split()
        # Filter stop words and single words < 4 chars
        if all(w not in _STOP_WORDS for w in words) and len(m) >= 4:
            normalized = m.lower()
            if normalized not in seen:
                seen.add(normalized)
                entities.append(m)
    return entities[:5]
