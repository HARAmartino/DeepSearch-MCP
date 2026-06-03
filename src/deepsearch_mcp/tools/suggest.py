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
# The reserved set always includes a temporal, a criticism, an alternatives, and
# a PRIMARY-SOURCE angle. The primary-source slot is domain-adaptive (B29) — see
# `_primary_source_template`.
_RESERVED_BASE = [
    "{topic} 2025 OR 2026",       # temporal freshness (most research is time-bound)
    "{topic} criticism",          # criticism angle (guaranteed)
    "{topic} alternatives",       # alternative viewpoints
]

# B29: the primary-source angle was dev-only (`site:github`), so policy/legal/gov
# research (e.g. "EU AI Act enforcement") got *no* path to its actual primary
# source (eur-lex/europa.eu/.gov) — a live run returned 0 authoritative results
# and no way to reach one. Pick the primary-source template from the topic's
# domain. Default stays dev/code. (Word-level match, not substring: "React"
# must NOT trip on "act". Curated signal list — expect it to grow with real
# usage, like the other allowlists; see the [STALE]-list discipline.)
_PRIMARY_SOURCE_DEV = "{topic} site:github.com"
_PRIMARY_SOURCE_OFFICIAL = "{topic} site:.gov OR site:europa.eu OR site:.int"
# B36: medical / science topics also have non-dev primary sources. The
# semaglutide run's primary-source angle was `site:github` (useless for a drug
# topic). Detection is keyword-based, so a topic that is *only* a proper-noun
# entity ("semaglutide long-term effects" — no generic medical word) still
# defaults; common phrasings ("X drug trial", "vaccine safety", "cancer therapy")
# are caught. Lists grow with usage (B25 discipline).
_PRIMARY_SOURCE_MEDICAL = (
    "{topic} site:pubmed.ncbi.nlm.nih.gov OR site:nih.gov OR site:who.int"
)
_PRIMARY_SOURCE_SCIENCE = "{topic} site:arxiv.org OR site:.edu"
_POLICY_SIGNALS = frozenset(
    "law laws act regulation regulations regulatory policy directive treaty bill "
    "statute legislation legal court ruling sanctions tariff tax election gdpr "
    "compliance government ministry parliament senate congress antitrust "
    "constitution amendment".split()
)
# B37: economics/finance/central-banking topics also route to OFFICIAL — their
# primary source is `.gov`/official (federalreserve.gov, bls.gov, ecb.europa.eu),
# all caught by `_PRIMARY_SOURCE_OFFICIAL` — not GitHub. A "Federal Reserve
# interest rate decision" run got `site:github`. Only DISTINCTIVE words (no
# "rate"/"interest"/"bank" — too generic). "federal" is safe: a federal-anything
# research topic is US-government → `.gov`. (Bare-entity topics like "Bank of
# Japan" with no finance keyword still default — the B36 limit.)
_FINANCE_SIGNALS = frozenset(
    "federal fed fomc monetary inflation deflation recession gdp fiscal treasury "
    "ecb boj macroeconomic unemployment stagflation".split()
)
_MEDICAL_SIGNALS = frozenset(
    "disease drug drugs vaccine vaccines clinical symptom symptoms therapy "
    "treatment treatments diagnosis dose dosage efficacy pharmaceutical "
    "medication medications cancer infection epidemic pandemic fda "
    "pubmed antibody antibiotic".split()
)
# Clearly-science words that do NOT overlap dev (no algorithm/neural/model/dataset).
_SCIENCE_SIGNALS = frozenset(
    "physics chemistry biology quantum genome genomics protein proteins enzyme "
    "astronomy astrophysics exoplanet particle molecule molecular theorem "
    "hypothesis neuron synapse".split()
)

# EXTRA templates fill any slots left after reserved + a capped share of
# autocomplete + context entities. Dropped first when the cap is tight.
_EXTRA_TEMPLATES = [
    "{topic} problems limitations",
    "{topic} vs",
    "{topic} site:arxiv.org OR site:research.google.com",
]
# Full (dev-default) set, reserved first — kept for back-compat /
# `_build_template_queries`'s default argument.
_VIEWPOINT_TEMPLATES = _RESERVED_BASE + [_PRIMARY_SOURCE_DEV] + _EXTRA_TEMPLATES

# B32: the viewpoint WORDS above are English — appending "criticism"/"alternatives"
# to a Japanese query won't surface Japanese content (a live "日本 新興 ガジェット
# メーカー" run produced "… criticism / alternatives / vs", a silent no-op). Detect
# a CJK (Japanese) topic and localize the word-based angles. The site:/temporal/
# year angles are language-agnostic and stay as-is. Japanese-first (the observed
# need); the table extends to more languages with real usage — B25 discipline.
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿]")  # kana + CJK ideographs
_RESERVED_BASE_JA = [
    "{topic} 2025 OR 2026",       # temporal (language-agnostic)
    "{topic} 批判",                # criticism
    "{topic} 代替案",              # alternatives
]
_EXTRA_TEMPLATES_JA = [
    "{topic} 問題点 デメリット",    # problems / limitations
    "{topic} 比較",                # vs / comparison
    "{topic} site:arxiv.org OR site:research.google.com",  # primary (lang-agnostic)
]


def _topic_lang(topic: str) -> str:
    """'ja' if the topic contains CJK (Japanese) characters, else 'en' (B32)."""
    return "ja" if _CJK_RE.search(topic) else "en"

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
    5. Primary-source angle — **always present**, and **domain-adaptive**
       (B29/B36/B37): policy/legal/gov **and economics/finance** → official
       sources (`site:.gov`/`europa.eu`/`.int` — e.g. federalreserve.gov);
       medical → `pubmed`/`nih.gov`/`who.int`; science → `arxiv`/`.edu`;
       everything else → `site:github.com` (dev/code default)

    The word-based angles (criticism / alternatives / problems / comparison) are
    **language-localized** (B32): a Japanese (CJK) topic gets 批判 / 代替案 /
    問題点 / 比較 instead of English, so the queries actually surface Japanese
    content. site:/year angles are language-agnostic.
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
    reserved_queries = _build_template_queries(topic, _reserved_templates(topic))
    extra_queries = _build_template_queries(topic, _extra_templates(topic))

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


def _primary_source_template(topic: str) -> str:
    """Pick a domain-appropriate primary-source angle (B29 + B36 + B37).
    Policy/legal/gov AND economics/finance → official sites; medical →
    pubmed/nih/who; science → arxiv/.edu; everything else → the dev/code default
    (GitHub). Word-level match so "React" doesn't trip "act". First match wins
    (policy|finance → medical → science → dev)."""
    words = set(re.findall(r"[a-z]+", topic.lower()))
    if words & _POLICY_SIGNALS or words & _FINANCE_SIGNALS:
        return _PRIMARY_SOURCE_OFFICIAL
    if words & _MEDICAL_SIGNALS:
        return _PRIMARY_SOURCE_MEDICAL
    if words & _SCIENCE_SIGNALS:
        return _PRIMARY_SOURCE_SCIENCE
    return _PRIMARY_SOURCE_DEV


def authority_query(topic: str) -> str:
    """The domain-appropriate primary-source ("authority") query for a topic,
    rendered ready to pass to `search_web` (B35).

    Real DDG result sets are dominated by SEO content farms — `source_tier`
    `authoritative` rarely fires even when authorities exist (4/4 live runs were
    ~0 authoritative). When a search returns 0 authoritative results, run THIS
    query to reach the primary source directly: policy → `.gov`/`europa.eu`/
    `.int`, medical → `pubmed`/`nih.gov`/`who.int`, science → `arxiv`/`.edu`,
    else → `github.com`. (Same routing as the suggest_queries primary angle.)
    """
    return _build_template_queries(topic, [_primary_source_template(topic)])[0]


def _reserved_templates(topic: str) -> list[str]:
    """Reserved viewpoint templates: language-localized base (B32) + the
    domain-adaptive primary source (B29) as the guaranteed primary-source slot."""
    base = _RESERVED_BASE_JA if _topic_lang(topic) == "ja" else _RESERVED_BASE
    return [*base, _primary_source_template(topic)]


def _extra_templates(topic: str) -> list[str]:
    """Overflow viewpoint templates, language-localized (B32)."""
    return _EXTRA_TEMPLATES_JA if _topic_lang(topic) == "ja" else _EXTRA_TEMPLATES


def _build_template_queries(
    topic: str, templates: list[str] | None = None
) -> list[str]:
    """Build viewpoint-shifting queries from the topic string.

    `templates` defaults to the full (dev) viewpoint set; callers pass
    `_reserved_templates(topic)` / `_EXTRA_TEMPLATES` to render each tier.
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
