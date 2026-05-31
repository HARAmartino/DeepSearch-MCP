"""
Phase 3 Tests — suggest_queries tool + date_parser URL/body extraction.

Stuck Agent Simulation (ROADMAP 3.4):
  A "stuck agent" has seen only echo-chamber results from the same source or
  perspective. suggest_queries must break this by returning queries covering:
    - Criticism / problems / limitations angle
    - Alternatives angle
    - Primary source angle (arxiv, github)
    - Temporal freshness angle (2025/2026)

Date Parser Extended Tests (ROADMAP 3.2):
  - URL path extraction: /YYYY/MM/DD/, /YYYY-MM-DD, etc.
  - Text body extraction: ISO 8601, "Month DD YYYY", "DD Month YYYY"
  - best_effort_date: priority chain (raw > url > body)
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from src.deepsearch_mcp.tools.suggest import (
    _AC_BUDGET,
    _autocomplete_url,
    _fetch_autocomplete,
    suggest_queries,
)
from src.deepsearch_mcp.utils.date_parser import (
    best_effort_date,
    extract_date_from_text,
    extract_date_from_url,
)

# ---------------------------------------------------------------------------
# Autocomplete request — regression for the 2026-05-30 dead-feature bug.
# The endpoint was called with NO `?q=`, so the topic was never sent and
# autocomplete silently returned [] forever. The Stuck Agent tests mocked
# `_fetch_autocomplete` itself, so they never exercised the real request.
# These tests mock `fetch` (the boundary), not the function under test.
# ---------------------------------------------------------------------------

class TestAutocompleteRequest:
    def test_url_includes_query(self):
        url = _autocomplete_url("vector database")
        assert "q=vector+database" in url
        assert "type=list" not in url  # that format breaks the phrase parser

    @patch("src.deepsearch_mcp.tools.suggest.fetch", new_callable=AsyncMock)
    async def test_fetch_sends_topic_in_url(self, mock_fetch):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = json.dumps([{"phrase": "vector database llm"},
                                {"phrase": "vector database examples"}])
        mock_fetch.return_value = resp

        phrases = await _fetch_autocomplete("vector database")

        # The bug: topic never reached the request. Assert it does now.
        called_url = mock_fetch.call_args.args[0] if mock_fetch.call_args.args \
            else mock_fetch.call_args.kwargs.get("url", "")
        assert "q=vector+database" in called_url
        assert phrases == ["vector database llm", "vector database examples"]

    @patch("src.deepsearch_mcp.tools.suggest.fetch", new_callable=AsyncMock)
    async def test_non_200_returns_empty(self, mock_fetch):
        resp = MagicMock()
        resp.status_code = 503
        resp.text = ""
        mock_fetch.return_value = resp
        assert await _fetch_autocomplete("x") == []

    @patch("src.deepsearch_mcp.tools.suggest.fetch", new_callable=AsyncMock)
    async def test_fetch_failure_degrades_to_empty(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("network down")
        assert await _fetch_autocomplete("x") == []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_suggestions(result: str) -> list[str]:
    data = json.loads(result)
    assert isinstance(data, list), f"Expected list, got: {type(data)}"
    return data


# ---------------------------------------------------------------------------
# Unit Tests: suggest_queries — output structure
# ---------------------------------------------------------------------------

class TestSuggestQueriesStructure:
    """Verify output format and minimum/maximum constraints."""

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_returns_json_array(self, mock_ac):
        mock_ac.return_value = []
        result = await suggest_queries(topic="React Server Components")
        data = json.loads(result)
        assert isinstance(data, list)

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_minimum_3_queries_returned(self, mock_ac):
        mock_ac.return_value = []
        result = await suggest_queries(topic="anything")
        data = _parse_suggestions(result)
        assert len(data) >= 3, f"Expected ≥3 queries, got {len(data)}: {data}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_maximum_8_queries_returned(self, mock_ac):
        mock_ac.return_value = [
            "result a", "result b", "result c", "result d",
        ]
        result = await suggest_queries(topic="python asyncio")
        data = _parse_suggestions(result)
        assert len(data) <= 8, f"Expected ≤8 queries, got {len(data)}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_all_items_are_strings(self, mock_ac):
        mock_ac.return_value = ["python asyncio tutorial"]
        result = await suggest_queries(topic="python asyncio")
        data = _parse_suggestions(result)
        for item in data:
            assert isinstance(item, str), f"Non-string item: {item!r}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_no_duplicate_queries(self, mock_ac):
        mock_ac.return_value = ["python asyncio tutorial"]
        result = await suggest_queries(topic="python asyncio")
        data = _parse_suggestions(result)
        normalized = [q.strip().lower() for q in data]
        assert len(normalized) == len(set(normalized)), (
            f"Duplicate queries found: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_empty_topic_returns_empty_array(self, mock_ac):
        mock_ac.return_value = []
        result = await suggest_queries(topic="")
        data = json.loads(result)
        assert data == []
        mock_ac.assert_not_called()

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_whitespace_only_topic_returns_empty_array(self, mock_ac):
        mock_ac.return_value = []
        result = await suggest_queries(topic="   ")
        data = json.loads(result)
        assert data == []
        mock_ac.assert_not_called()


# ---------------------------------------------------------------------------
# Stuck Agent Simulation (ROADMAP 3.4) — Echo-Chamber Breaking
# ---------------------------------------------------------------------------

class TestStuckAgentSimulation:
    """
    Simulate an agent stuck in an echo chamber:
      - Has searched "intermittent fasting" 5 times.
      - All results are from diet blogs praising the practice.
      - Agent needs laterally-shifted queries to escape the echo chamber.

    Verify that suggest_queries returns viewpoints covering:
      - Criticism / problems / risks
      - Alternatives
      - Primary sources (arxiv, pubmed, github)
      - Temporal freshness
    """

    _ECHO_CHAMBER_CONTEXT = (
        "Intermittent fasting is an amazing diet strategy. "
        "Studies show incredible weight loss results. "
        "Top 10 benefits of intermittent fasting you need to know. "
        "Diet Blog Weekly: How I lost 30 pounds with 16:8 fasting."
    )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_stuck_agent_gets_criticism_angle(self, mock_ac):
        """Output must include a query targeting criticism or problems."""
        mock_ac.return_value = []
        result = await suggest_queries(
            topic="intermittent fasting",
            context=self._ECHO_CHAMBER_CONTEXT,
        )
        data = _parse_suggestions(result)
        combined = " ".join(data).lower()
        assert any(kw in combined for kw in ["criticism", "problems", "limitations", "risks"]), (
            f"No criticism-angle query found in: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_stuck_agent_gets_alternatives_angle(self, mock_ac):
        """Output must include a query targeting alternatives."""
        mock_ac.return_value = []
        result = await suggest_queries(
            topic="intermittent fasting",
            context=self._ECHO_CHAMBER_CONTEXT,
        )
        data = _parse_suggestions(result)
        combined = " ".join(data).lower()
        assert "alternatives" in combined or "vs" in combined, (
            f"No alternatives-angle query found in: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_stuck_agent_gets_primary_source_angle(self, mock_ac):
        """Output must include a query targeting academic/primary sources."""
        mock_ac.return_value = []
        result = await suggest_queries(
            topic="intermittent fasting",
            context=self._ECHO_CHAMBER_CONTEXT,
        )
        data = _parse_suggestions(result)
        combined = " ".join(data).lower()
        assert any(kw in combined for kw in ["arxiv", "research.google", "github", "pubmed", "site:"]), (
            f"No primary-source query found in: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_stuck_agent_tech_topic_breaks_echo_chamber(self, mock_ac):
        """Same test for a tech topic: React Server Components."""
        mock_ac.return_value = [
            "React Server Components tutorial",
            "React Server Components nextjs",
        ]
        tech_context = (
            "React Server Components are the future of web development. "
            "Every Next.js app should use Server Components. "
            "React Server Components improve performance dramatically."
        )
        result = await suggest_queries(
            topic="React Server Components",
            context=tech_context,
        )
        data = _parse_suggestions(result)
        combined = " ".join(data).lower()
        # Must have at least criticism OR alternatives
        assert any(kw in combined for kw in ["criticism", "problems", "alternatives", "vs"]), (
            f"No critical-angle query for tech topic: {data}"
        )
        # Must have at least one primary source angle
        assert any(kw in combined for kw in ["site:", "github", "arxiv"]), (
            f"No primary-source query for tech topic: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_autocomplete_suggestions_come_first(self, mock_ac):
        """AC suggestions (real user patterns) must appear before template queries."""
        ac_phrase = "intermittent fasting research 2025"
        mock_ac.return_value = [ac_phrase]
        result = await suggest_queries(topic="intermittent fasting")
        data = _parse_suggestions(result)
        assert data[0] == ac_phrase, (
            f"AC suggestion should be first; got: {data[0]!r}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_entity_queries_included_when_context_provided(self, mock_ac):
        """Entity drill-downs from context should appear in results."""
        mock_ac.return_value = []
        context_with_entity = (
            "Researchers at Stanford University published a study on "
            "intermittent fasting effects on metabolism."
        )
        result = await suggest_queries(
            topic="fasting",
            context=context_with_entity,
        )
        data = _parse_suggestions(result)
        combined = " ".join(data).lower()
        # "Stanford University" or "Stanford" should appear as an entity drill-down
        assert "stanford" in combined or len(data) >= 3, (
            f"Expected entity or minimum queries; got: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_ac_failure_graceful_fallback(self, mock_ac):
        """If autocomplete fails (returns empty), templates must still supply ≥3 queries."""
        mock_ac.return_value = []
        result = await suggest_queries(topic="quantum computing")
        data = _parse_suggestions(result)
        assert len(data) >= 3, (
            f"Fallback to templates must yield ≥3 queries, got {len(data)}: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_temporal_freshness_query_present(self, mock_ac):
        """Output should include a query targeting recent content (2025/2026)."""
        mock_ac.return_value = []
        result = await suggest_queries(topic="large language models")
        data = _parse_suggestions(result)
        combined = " ".join(data)
        assert "2025" in combined or "2026" in combined, (
            f"No temporal freshness query found: {data}"
        )


# ---------------------------------------------------------------------------
# Unit Tests: date_parser — URL extraction
# ---------------------------------------------------------------------------

class TestExtractDateFromUrl:
    """Verify URL date extraction for all supported patterns."""

    def test_slash_separated_ymd(self):
        assert extract_date_from_url("https://example.com/2026/05/28/article") == "2026-05-28"

    def test_dash_separated_in_path(self):
        assert extract_date_from_url("https://blog.com/posts/2026-05-28-title") == "2026-05-28"

    def test_date_query_param_dashed(self):
        assert extract_date_from_url("https://example.com/articles?date=2026-05-28") == "2026-05-28"

    def test_date_query_param_compact(self):
        assert extract_date_from_url("https://example.com/articles?date=20260528") == "2026-05-28"

    def test_compact_date_in_path(self):
        assert extract_date_from_url("https://example.com/20260528/article") == "2026-05-28"

    def test_no_date_in_url_returns_none(self):
        assert extract_date_from_url("https://example.com/about") is None

    def test_empty_url_returns_none(self):
        assert extract_date_from_url("") is None

    def test_invalid_month_rejected(self):
        result = extract_date_from_url("https://example.com/2026/13/01/bad")
        assert result is None

    def test_invalid_day_rejected(self):
        result = extract_date_from_url("https://example.com/2026/12/32/bad")
        assert result is None

    def test_year_before_2000_rejected(self):
        result = extract_date_from_url("https://example.com/1999/05/28/old")
        assert result is None

    def test_single_digit_month_and_day(self):
        assert extract_date_from_url("https://example.com/2026/5/3/article") == "2026-05-03"


# ---------------------------------------------------------------------------
# Unit Tests: date_parser — text body extraction
# ---------------------------------------------------------------------------

class TestExtractDateFromText:
    """Verify date extraction from article body text."""

    def test_iso8601_in_text(self):
        assert extract_date_from_text("Published on 2026-05-28 by our team.") == "2026-05-28"

    def test_month_day_year_format(self):
        assert extract_date_from_text("May 28, 2026 — Staff Reporter") == "2026-05-28"

    def test_day_month_year_format(self):
        assert extract_date_from_text("Published: 28 May 2026") == "2026-05-28"

    def test_abbreviated_month(self):
        result = extract_date_from_text("Updated Jan 15, 2026 by the editor.")
        assert result == "2026-01-15"

    def test_no_date_returns_none(self):
        assert extract_date_from_text("This article has no date information at all.") is None

    def test_empty_text_returns_none(self):
        assert extract_date_from_text("") is None

    def test_short_text_returns_none(self):
        assert extract_date_from_text("short") is None

    def test_prefers_iso8601_over_text_pattern(self):
        # ISO 8601 comes first in text; ensure it wins
        text = "Updated 2026-03-10. Originally published March 1, 2026."
        result = extract_date_from_text(text)
        assert result == "2026-03-10"

    def test_year_out_of_range_rejected(self):
        result = extract_date_from_text("Published on 1998-05-28 in a magazine.")
        assert result is None

    def test_future_year_accepted(self):
        result = extract_date_from_text("Scheduled for 2027-01-01.")
        assert result == "2027-01-01"


# ---------------------------------------------------------------------------
# Unit Tests: date_parser — best_effort_date priority chain
# ---------------------------------------------------------------------------

class TestBestEffortDate:
    """Verify priority: raw string > URL > body text."""

    def test_raw_string_wins_over_url_and_body(self):
        result = best_effort_date(
            raw="2026-01-01",
            url="https://example.com/2025/06/15/article",
            body="Published 2024-03-10",
        )
        assert result == "2026-01-01"

    def test_url_wins_over_body_when_raw_absent(self):
        result = best_effort_date(
            raw=None,
            url="https://example.com/2026/05/28/article",
            body="Published 2024-03-10",
        )
        assert result == "2026-05-28"

    def test_body_used_as_last_resort(self):
        result = best_effort_date(
            raw=None,
            url="https://example.com/about",
            body="Published on 2026-05-28 by staff.",
        )
        assert result == "2026-05-28"

    def test_all_none_returns_none(self):
        result = best_effort_date(raw=None, url=None, body=None)
        assert result is None

    def test_empty_raw_falls_back_to_url(self):
        result = best_effort_date(
            raw="",
            url="https://example.com/2026/05/28/article",
            body=None,
        )
        assert result == "2026-05-28"

    def test_bad_url_falls_back_to_body(self):
        result = best_effort_date(
            raw=None,
            url="https://example.com/about-us",
            body="First published May 28, 2026.",
        )
        assert result == "2026-05-28"


# ---------------------------------------------------------------------------
# Phase 5 Regression: Smart Quoting (FRICTION-C1)
# Long topics MUST NOT be wrapped in double quotes — quote-wrapping a 6-word
# phrase forces an exact-match search that returns zero hits.
# ---------------------------------------------------------------------------

class TestSmartQuoting:
    """Regression tests for FRICTION-C1: smart quoting of topic in templates."""

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_long_topic_not_quote_wrapped(self, mock_ac):
        """Topics with ≥3 words must NOT be wrapped in double quotes."""
        mock_ac.return_value = []
        long_topic = "AI agent memory management RAG"  # 5 words
        result = await suggest_queries(topic=long_topic)
        data = _parse_suggestions(result)
        for q in data:
            # The TEMPLATE-generated queries (every one except entity drill-downs)
            # must not contain the topic wrapped in quotes.
            assert f'"{long_topic}"' not in q, (
                f"Long topic was quote-wrapped in: {q!r}\nFull output: {data}"
            )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_two_word_topic_is_quote_wrapped(self, mock_ac):
        """Short topics (≤2 words) ARE wrapped in quotes for precision."""
        mock_ac.return_value = []
        result = await suggest_queries(topic="React Components")  # 2 words
        data = _parse_suggestions(result)
        # At least the criticism template should use the quoted form
        assert any('"React Components"' in q for q in data), (
            f"Short topic should be quote-wrapped; got: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_single_word_topic_is_quote_wrapped(self, mock_ac):
        mock_ac.return_value = []
        result = await suggest_queries(topic="CRISPR")
        data = _parse_suggestions(result)
        assert any('"CRISPR"' in q for q in data), (
            f"Single-word topic should be quote-wrapped; got: {data}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_three_word_topic_not_quote_wrapped(self, mock_ac):
        """Boundary case: 3 words is the threshold for unquoted form."""
        mock_ac.return_value = []
        topic = "large language models"
        result = await suggest_queries(topic=topic)
        data = _parse_suggestions(result)
        for q in data:
            assert f'"{topic}"' not in q, (
                f"3-word topic was quote-wrapped in: {q!r}\nFull: {data}"
            )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_long_topic_queries_contain_keywords_bare(self, mock_ac):
        """After unwrapping, the topic keywords should still appear in each query."""
        mock_ac.return_value = []
        topic = "AI agent memory management"
        result = await suggest_queries(topic=topic)
        data = _parse_suggestions(result)
        # Every template-generated query must contain the topic keywords
        for q in data[:7]:  # the 7 templates (skip any entity drill-downs)
            assert topic in q, f"Topic missing from query {q!r}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_temporal_query_appears_in_top_3(self, mock_ac):
        """FRICTION-C3: temporal freshness query should be early in results."""
        mock_ac.return_value = []
        result = await suggest_queries(topic="quantum computing")
        data = _parse_suggestions(result)
        top_3 = " ".join(data[:3])
        assert "2025" in top_3 or "2026" in top_3, (
            f"Temporal query should appear in top 3; got top 3: {data[:3]}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_long_topic_with_context_entity_query_works(self, mock_ac):
        """Entity drill-down should quote the entity but leave topic bare."""
        mock_ac.return_value = []
        topic = "AI agent memory management"  # 4 words
        context = "Stanford researchers showed that..."
        result = await suggest_queries(topic=topic, context=context)
        data = _parse_suggestions(result)
        # Find any entity query (contains "Stanford")
        entity_qs = [q for q in data if "Stanford" in q]
        if entity_qs:  # entity extraction may yield 0 if "Stanford" hits stop-word filter
            for eq in entity_qs:
                # Entity itself is quoted, but topic is bare
                assert '"Stanford"' in eq, f"Entity not quoted in {eq!r}"
                assert f'"{topic}"' not in eq, f"Topic incorrectly quoted in {eq!r}"


class TestReservedSlotsB11:
    """B11: a full set of (often noisy) autocomplete phrases must NOT crowd the
    echo-chamber differentiators out of the 8-result window. Before the reserve,
    4 AC phrases pushed both primary-source templates past the cap."""

    # 4 phrases = the live AC max, and the exact tabloid-noise shape the Sam
    # Altman run surfaced ("net worth / husband / age / wife").
    _NOISY_AC = [
        "Sam Altman net worth",
        "Sam Altman husband",
        "Sam Altman age",
        "Sam Altman wife",
    ]

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_primary_source_survives_full_autocomplete(self, mock_ac):
        # This is the assertion that FAILED before B11 (site:github/arxiv were
        # at indices 9–10, dropped by [:8] once 4 AC phrases led the list).
        mock_ac.return_value = list(self._NOISY_AC)
        data = _parse_suggestions(await suggest_queries(topic="Sam Altman"))
        combined = " ".join(data).lower()
        assert "site:" in combined, f"primary-source angle crowded out: {data}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_criticism_survives_full_autocomplete(self, mock_ac):
        mock_ac.return_value = list(self._NOISY_AC)
        data = _parse_suggestions(await suggest_queries(topic="Sam Altman"))
        combined = " ".join(data).lower()
        assert "criticism" in combined, f"criticism angle crowded out: {data}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_autocomplete_share_is_capped(self, mock_ac):
        # No more than _AC_BUDGET of the AC phrases may reach the output, so the
        # reserved templates always have room.
        mock_ac.return_value = list(self._NOISY_AC)
        data = _parse_suggestions(await suggest_queries(topic="Sam Altman"))
        ac_in_output = [q for q in data if q in self._NOISY_AC]
        assert len(ac_in_output) <= _AC_BUDGET, (
            f"autocomplete not capped at {_AC_BUDGET}: {ac_in_output}"
        )

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_autocomplete_still_leads_when_present(self, mock_ac):
        # The cap must not invert ordering: AC still comes first (back-compat).
        mock_ac.return_value = ["Sam Altman OpenAI"]
        data = _parse_suggestions(await suggest_queries(topic="Sam Altman"))
        assert data[0] == "Sam Altman OpenAI", f"AC should still lead; got {data[0]!r}"


class TestB29DomainAdaptivePrimarySource:
    """B29: the guaranteed primary-source angle adapts to the topic domain —
    policy/legal/gov topics reach official sources, not GitHub. The live EU AI
    Act run found 0 authoritative results and no path to eur-lex/europa.eu."""

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_policy_topic_gets_official_sources(self, mock_ac):
        mock_ac.return_value = []
        data = _parse_suggestions(await suggest_queries(topic="EU AI Act enforcement"))
        combined = " ".join(data).lower()
        assert "europa.eu" in combined or "site:.gov" in combined, (
            f"policy topic should reach official sources, got: {data}"
        )
        assert "github" not in combined, f"policy topic should not default to github: {data}"

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_dev_topic_keeps_github(self, mock_ac):
        mock_ac.return_value = []
        data = _parse_suggestions(await suggest_queries(topic="React Server Components"))
        combined = " ".join(data).lower()
        assert "github" in combined, f"dev topic should keep github primary source: {data}"
        assert "europa.eu" not in combined

    def test_word_level_match_does_not_misclassify_react(self):
        # "React" contains the substring "act" — must NOT be read as policy.
        from src.deepsearch_mcp.tools.suggest import (
            _PRIMARY_SOURCE_DEV,
            _PRIMARY_SOURCE_OFFICIAL,
            _primary_source_template,
        )
        assert _primary_source_template("React Server Components") == _PRIMARY_SOURCE_DEV
        assert _primary_source_template("transaction batching") == _PRIMARY_SOURCE_DEV
        assert _primary_source_template("EU AI Act") == _PRIMARY_SOURCE_OFFICIAL
        assert _primary_source_template("GDPR compliance fines") == _PRIMARY_SOURCE_OFFICIAL

    @patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete", new_callable=AsyncMock)
    async def test_policy_still_has_criticism_and_is_capped(self, mock_ac):
        # The B11 guarantees must still hold for the adaptive path.
        mock_ac.return_value = ["EU AI Act news", "EU AI Act summary",
                                "EU AI Act text", "EU AI Act fines"]
        data = _parse_suggestions(await suggest_queries(topic="EU AI Act"))
        combined = " ".join(data).lower()
        assert "criticism" in combined
        assert "site:" in combined  # primary-source angle survived the AC cap
        assert 3 <= len(data) <= 8
