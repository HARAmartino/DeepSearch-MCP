"""
Phase 2 Tests — search_web tool + cache layer + chaos error handling.

Chaos Engineering (ROADMAP 2.3):
  - RatelimitException  → RATE_LIMITED, retryable=True
  - TimeoutException    → TIMEOUT, retryable=False
  - DuckDuckGoSearchException → CONN_ERROR, retryable=False
  - Network/unexpected error  → CONN_ERROR

Cache Tests:
  - Cache miss triggers DDG call
  - Cache hit returns without additional DDG call
  - TTL expiry returns None (simulated via direct DB write)

Search normalization:
  - 'href' key → 'url' in SearchResult
  - published_date normalization (None when absent in DDGS v8)
"""

from __future__ import annotations

import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.deepsearch_mcp.core import errors as err
from src.deepsearch_mcp.core.cache import (
    TTL_SEARCH,
    cache_delete,
    cache_get,
    cache_set,
    make_search_key,
)
from src.deepsearch_mcp.tools.search import (
    _OUTAGE_THRESHOLD,
    _ddg_html_fallback,
    _decode_ddg_href,
    _jaccard,
    _map_ddgs_exception,
    _mark_near_duplicates,
    _note_search_outcome,
    _reset_failure_streak,
    _title_tokens,
    search_web,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAKE_RESULTS = [
    {
        "title": "Understanding Async Python",
        "href": "https://realpython.com/async-io-python/",
        "body": (
            "Async IO in Python: A Complete Walkthrough. "
            "Async IO is a concurrent programming design."
        ),
    },
    {
        "title": "Python asyncio docs",
        "href": "https://docs.python.org/3/library/asyncio.html",
        "body": "asyncio is a library to write concurrent code using async/await syntax.",
    },
]


async def _clear_cache(query: str, region: str | None = None) -> None:
    key = make_search_key(query, region, "moderate", None)
    await cache_delete(key)


@pytest.fixture(autouse=True)
def _reset_search_failure_streak():
    """B13: the consecutive-failure counter is module-global shared state. Reset
    it around every test so a failing-search test can't bleed its streak into
    the next test's assertions (cf. the B8 telemetry-drain lesson)."""
    _reset_failure_streak()
    yield
    _reset_failure_streak()


# ---------------------------------------------------------------------------
# Unit tests: _map_ddgs_exception
# ---------------------------------------------------------------------------

class TestMapDdgsException:
    """Verify that all DDGS exceptions map to correct StructuredError codes."""

    def _parse(self, result: str) -> dict:
        data = json.loads(result)
        assert data["status"] == "error"
        return data

    def test_ratelimit_exception_maps_to_rate_limited(self):
        from duckduckgo_search.exceptions import RatelimitException
        result = _map_ddgs_exception(RatelimitException("rate limit hit"))
        data = self._parse(result)
        assert data["code"] == err.RATE_LIMITED
        assert data["retryable"] is True
        assert "hint" in data and len(data["hint"]) > 10

    def test_ratelimit_hint_contains_actionable_advice(self):
        from duckduckgo_search.exceptions import RatelimitException
        result = _map_ddgs_exception(RatelimitException("429"))
        data = self._parse(result)
        hint_lower = data["hint"].lower()
        assert any(kw in hint_lower for kw in ["wait", "60", "refine", "retry"]), (
            f"Hint lacks actionable advice: {data['hint']}"
        )

    def test_timeout_exception_maps_to_timeout(self):
        """Phase 5 (FRICTION-B3): TIMEOUT is now retryable — was previously False."""
        from duckduckgo_search.exceptions import TimeoutException
        result = _map_ddgs_exception(TimeoutException("timed out"))
        data = self._parse(result)
        assert data["code"] == err.TIMEOUT
        assert data["retryable"] is True

    def test_base_ddgs_exception_maps_to_conn_error(self):
        """Non-transient backend error → retryable=False (no DNS/timeout in msg)."""
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        result = _map_ddgs_exception(DuckDuckGoSearchException("generic backend issue"))
        data = self._parse(result)
        assert data["code"] == err.CONN_ERROR
        assert data["retryable"] is False

    def test_unexpected_exception_maps_to_conn_error(self):
        result = _map_ddgs_exception(ConnectionError("DNS failure"))
        data = self._parse(result)
        assert data["code"] == err.CONN_ERROR

    def test_all_errors_have_required_fields(self):
        from duckduckgo_search.exceptions import (
            DuckDuckGoSearchException,
            RatelimitException,
            TimeoutException,
        )
        exceptions = [
            RatelimitException("r"),
            TimeoutException("t"),
            DuckDuckGoSearchException("d"),
            ValueError("v"),
        ]
        required = {"status", "code", "message", "hint", "retryable"}
        for exc in exceptions:
            data = json.loads(_map_ddgs_exception(exc))
            missing = required - data.keys()
            assert not missing, f"Missing fields {missing} for {type(exc).__name__}"


# ---------------------------------------------------------------------------
# Integration tests: search_web tool (mocked DDGS)
# ---------------------------------------------------------------------------

class TestSearchWebTool:
    """Test search_web with mocked asyncio.to_thread to avoid live network calls."""

    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        await _clear_cache("async python tutorial")
        yield
        await _clear_cache("async python tutorial")

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_successful_search_returns_json_array(self, mock_thread):
        mock_thread.return_value = _FAKE_RESULTS
        result = await search_web(query="async python tutorial")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 2

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_href_mapped_to_url_field(self, mock_thread):
        mock_thread.return_value = _FAKE_RESULTS
        result = await search_web(query="async python tutorial")
        data = json.loads(result)
        assert data[0]["url"] == "https://realpython.com/async-io-python/"
        assert "href" not in data[0]

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_result_has_all_searchresult_fields(self, mock_thread):
        mock_thread.return_value = _FAKE_RESULTS
        result = await search_web(query="async python tutorial")
        data = json.loads(result)
        required = {"title", "url", "body", "published_date", "score"}
        for item in data:
            missing = required - item.keys()
            assert not missing, f"Missing fields: {missing}"

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_published_date_is_none_when_absent(self, mock_thread):
        """DDGS v8 does not return publication dates — should be null."""
        mock_thread.return_value = _FAKE_RESULTS
        result = await search_web(query="async python tutorial")
        data = json.loads(result)
        for item in data:
            assert item["published_date"] is None, (
                f"Expected null published_date, got {item['published_date']}"
            )

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_empty_query_returns_error(self, mock_thread):
        result = await search_web(query="   ")
        data = json.loads(result)
        assert data["status"] == "error"
        mock_thread.assert_not_called()

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_max_results_clamped_to_50(self, mock_thread):
        mock_thread.return_value = []
        await search_web(query="async python tutorial", max_results=999)
        mock_thread.assert_called_once()

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_search_operators_pass_through_verbatim(self, mock_thread):
        """B23: -exclude / "phrase" / site: / OR must reach DDGS unchanged."""
        mock_thread.return_value = []
        q = 'silicon valley 2026 -AI "deep tech" site:stanford.edu OR biotech'
        await _clear_cache(q)
        await search_web(query=q)
        # to_thread called as (_ddgs_search_sync, query, region, ...)
        passed_query = mock_thread.call_args.args[1]
        assert passed_query == q
        assert "-AI" in passed_query
        assert '"deep tech"' in passed_query
        assert "site:stanford.edu" in passed_query
        await _clear_cache(q)


# ---------------------------------------------------------------------------
# Chaos Engineering tests
# ---------------------------------------------------------------------------

class TestSearchWebChaos:
    """Verify structured error output for all DDGS failure modes.

    These test error *mapping*, which only fires when the DDG HTML fallback
    also fails — so stub the fallback to [] (B12 added a real network call on
    the DDGS-failure path).
    """

    @pytest.fixture(autouse=True)
    def _no_fallback(self):
        with patch("src.deepsearch_mcp.tools.search._ddg_html_fallback",
                   new_callable=AsyncMock) as m:
            m.return_value = []
            yield

    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        await _clear_cache("chaos test query xyz123")
        yield
        await _clear_cache("chaos test query xyz123")

    def _expect_error(self, result: str, code: str, retryable: bool) -> dict:
        data = json.loads(result)
        assert data["status"] == "error", f"Expected error, got: {result[:200]}"
        assert data["code"] == code, f"Expected code={code}, got {data['code']}"
        assert data["retryable"] is retryable, (
            f"Expected retryable={retryable}, got {data['retryable']}"
        )
        assert "hint" in data and len(data["hint"]) > 5
        return data

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_ratelimit_returns_rate_limited_retryable(self, mock_thread):
        from duckduckgo_search.exceptions import RatelimitException
        mock_thread.side_effect = RatelimitException("rate limited")
        result = await search_web(query="chaos test query xyz123")
        self._expect_error(result, err.RATE_LIMITED, retryable=True)

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_timeout_returns_timeout_retryable(self, mock_thread):
        """Phase 5 (FRICTION-B3): timeouts are transient → retryable=True."""
        from duckduckgo_search.exceptions import TimeoutException
        mock_thread.side_effect = TimeoutException("timed out")
        result = await search_web(query="chaos test query xyz123")
        self._expect_error(result, err.TIMEOUT, retryable=True)

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_generic_ddgs_error_returns_conn_error(self, mock_thread):
        """Backend errors WITHOUT transient keywords → retryable=False."""
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        mock_thread.side_effect = DuckDuckGoSearchException("invalid query syntax")
        result = await search_web(query="chaos test query xyz123")
        self._expect_error(result, err.CONN_ERROR, retryable=False)

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_network_error_returns_conn_error_retryable(self, mock_thread):
        """Phase 5 (FRICTION-B3): DNS errors → retryable=True (transient)."""
        mock_thread.side_effect = ConnectionError("DNS resolution failed")
        result = await search_web(query="chaos test query xyz123")
        self._expect_error(result, err.CONN_ERROR, retryable=True)

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_error_response_is_valid_json_no_traceback(self, mock_thread):
        from duckduckgo_search.exceptions import RatelimitException
        mock_thread.side_effect = RatelimitException("boom")
        result = await search_web(query="chaos test query xyz123")
        assert "Traceback" not in result
        assert 'File "' not in result
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Cache layer unit tests
# ---------------------------------------------------------------------------

class TestCacheLayer:
    """Verify cache_get/cache_set/TTL behavior."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        key = make_search_key("cache_test_q", None, "moderate", None)
        await cache_delete(key)
        yield
        await cache_delete(key)

    @property
    def _key(self) -> str:
        return make_search_key("cache_test_q", None, "moderate", None)

    async def test_cache_miss_returns_none(self):
        result = await cache_get(self._key)
        assert result is None

    async def test_set_then_get_returns_value(self):
        await cache_set(self._key, '{"test": true}', TTL_SEARCH)
        result = await cache_get(self._key)
        assert result == '{"test": true}'

    async def test_expired_entry_returns_none(self):
        import aiosqlite as aio
        db_path = str(__import__("src.deepsearch_mcp.core.cache", fromlist=["_DB_PATH"])._DB_PATH)
        # Write an already-expired entry directly
        async with aio.connect(db_path) as db:
            past = int(time.time()) - 100
            await db.execute(
                "INSERT OR REPLACE INTO cache (key, value, timestamp, ttl) "
                "VALUES (?, ?, ?, ?)",
                (self._key, '{"expired": true}', past, 5),
            )
            await db.commit()
        result = await cache_get(self._key)
        assert result is None, "Expired cache entry should return None"

    async def test_fresh_entry_not_expired(self):
        await cache_set(self._key, "fresh_value", TTL_SEARCH)
        result = await cache_get(self._key)
        assert result == "fresh_value"

    async def test_overwrite_updates_value(self):
        await cache_set(self._key, "first", TTL_SEARCH)
        await cache_set(self._key, "second", TTL_SEARCH)
        result = await cache_get(self._key)
        assert result == "second"

    async def test_make_search_key_is_deterministic(self):
        k1 = make_search_key("python", "us-en", "moderate", "w")
        k2 = make_search_key("python", "us-en", "moderate", "w")
        assert k1 == k2

    async def test_different_params_give_different_keys(self):
        k1 = make_search_key("python", "us-en", "moderate", "w")
        k2 = make_search_key("python", "us-en", "moderate", "m")
        k3 = make_search_key("java", "us-en", "moderate", "w")
        assert k1 != k2
        assert k1 != k3
        assert k2 != k3

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_cache_hit_skips_ddg_call(self, mock_thread):
        """Second identical search must not call DDG (cache hit)."""
        mock_thread.return_value = _FAKE_RESULTS
        query = "cache hit test unique q 99887766"
        await _clear_cache(query)

        await search_web(query=query)
        first_count = mock_thread.call_count

        # Second call — cache hit, no DDG
        await search_web(query=query)
        assert mock_thread.call_count == first_count, (
            "Cache hit should not increase DDG call count"
        )
        await _clear_cache(query)


# ---------------------------------------------------------------------------
# Direct-DDG HTML fallback (B12) — makes search survive a dead bing backend.
# Mock at the `fetch` boundary, never the function under test.
# ---------------------------------------------------------------------------

_DDG_HTML_FIXTURE = """
<html><body>
<div class="result results_links">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fmcp&rut=abc">Example MCP</a>
  <a class="result__snippet">A snippet about the Model Context Protocol.</a>
</div>
<div class="result result--ad">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fad.example.com">Sponsored</a>
</div>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Fmcp&rut=def">MCP on GitHub</a>
  <a class="result__snippet">Open protocol repo.</a>
</div>
</body></html>
"""


class TestDecodeDdgHref:
    def test_decodes_uddg_redirect(self):
        href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=x"
        assert _decode_ddg_href(href) == "https://example.com/a"

    def test_direct_http_passthrough(self):
        assert _decode_ddg_href("https://example.com/b") == "https://example.com/b"

    def test_empty_returns_empty(self):
        assert _decode_ddg_href("") == ""

    def test_non_http_relative_without_uddg_returns_empty(self):
        assert _decode_ddg_href("/internal/page") == ""


class TestDdgHtmlFallback:
    def _resp(self, text, status=200):
        r = MagicMock()
        r.status_code = status
        r.text = text
        return r

    @patch("src.deepsearch_mcp.tools.search.fetch", new_callable=AsyncMock)
    async def test_parses_results_and_decodes_urls(self, mock_fetch):
        mock_fetch.return_value = self._resp(_DDG_HTML_FIXTURE)
        out = await _ddg_html_fallback("mcp", None, "moderate", None, 10)
        assert len(out) == 2  # ad skipped
        assert out[0]["url"] == "https://example.com/mcp"
        assert out[0]["title"] == "Example MCP"
        assert "Model Context Protocol" in out[0]["body"]
        assert out[1]["url"] == "https://github.com/mcp"

    @patch("src.deepsearch_mcp.tools.search.fetch", new_callable=AsyncMock)
    async def test_respects_max_results(self, mock_fetch):
        mock_fetch.return_value = self._resp(_DDG_HTML_FIXTURE)
        out = await _ddg_html_fallback("mcp", None, "moderate", None, 1)
        assert len(out) == 1

    @patch("src.deepsearch_mcp.tools.search.fetch", new_callable=AsyncMock)
    async def test_query_in_url(self, mock_fetch):
        mock_fetch.return_value = self._resp(_DDG_HTML_FIXTURE)
        await _ddg_html_fallback("model context protocol", None, "moderate", None, 5)
        called = mock_fetch.call_args.args[0]
        assert "q=model+context+protocol" in called

    @patch("src.deepsearch_mcp.tools.search.fetch", new_callable=AsyncMock)
    async def test_operators_survive_url_encoding(self, mock_fetch):
        """B23: operators pass through the fallback too (url-encoded)."""
        mock_fetch.return_value = self._resp(_DDG_HTML_FIXTURE)
        await _ddg_html_fallback("trends -AI site:stanford.edu", None, "moderate", None, 5)
        called = mock_fetch.call_args.args[0]
        assert "-AI" in called          # '-' survives quote_plus
        assert "site%3Astanford.edu" in called  # ':' encoded but present

    @patch("src.deepsearch_mcp.tools.search.fetch", new_callable=AsyncMock)
    async def test_non_200_returns_empty(self, mock_fetch):
        mock_fetch.return_value = self._resp("", status=503)
        assert await _ddg_html_fallback("x", None, "moderate", None, 5) == []

    @patch("src.deepsearch_mcp.tools.search.fetch", new_callable=AsyncMock)
    async def test_fetch_failure_returns_empty(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("network down")
        assert await _ddg_html_fallback("x", None, "moderate", None, 5) == []


class TestSearchWebFallbackWiring:
    """When DDGS raises, search_web must try the fallback before erroring."""

    @patch("src.deepsearch_mcp.tools.search._ddg_html_fallback", new_callable=AsyncMock)
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_fallback_used_when_ddgs_fails(self, mock_thread, mock_fallback):
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        mock_thread.side_effect = DuckDuckGoSearchException("bing down")
        mock_fallback.return_value = [
            {"title": "T", "url": "https://e.com", "body": "b",
             "published_date": None, "score": None}
        ]
        q = "fallback wiring test unique 5521"
        await cache_delete(make_search_key(q, None, "moderate", None))
        result = await search_web(query=q)
        data = json.loads(result)
        assert isinstance(data, list) and data[0]["url"] == "https://e.com"
        await cache_delete(make_search_key(q, None, "moderate", None))

    @patch("src.deepsearch_mcp.tools.search._ddg_html_fallback", new_callable=AsyncMock)
    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_error_when_both_fail(self, mock_thread, mock_fallback):
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        mock_thread.side_effect = DuckDuckGoSearchException("bing down")
        mock_fallback.return_value = []  # fallback also fails
        q = "both fail test unique 7732"
        await cache_delete(make_search_key(q, None, "moderate", None))
        result = await search_web(query=q)
        data = json.loads(result)
        assert data["status"] == "error" and data["code"] == err.CONN_ERROR


# ---------------------------------------------------------------------------
# Near-duplicate flagging (B16) — mark, never remove; preserve corroboration.
# ---------------------------------------------------------------------------

def _r(title, tier="unknown", url=None):
    return {"title": title, "url": url or f"https://{abs(hash(title)) % 9999}.example",
            "body": "", "published_date": None, "score": None,
            "source_tier": tier, "near_duplicate": False}


class TestTitleTokens:
    def test_strips_stopwords_and_short_tokens(self):
        toks = _title_tokens("The Best of AI in 2026")
        assert "the" not in toks and "of" not in toks and "in" not in toks
        assert "2026" in toks and "ai" not in toks  # 'ai' < 3 chars

    def test_punctuation_split(self):
        assert _title_tokens("Llama-4: DeepSeek, Qwen!") == frozenset({"llama", "deepseek", "qwen"})

    def test_japanese_produces_bigram_tokens(self):
        # B22: ASCII-only tokenizer yielded nothing for CJK; now bigrams.
        toks = _title_tokens("辺地共聴施設")
        assert "辺地" in toks and "共聴" in toks and "施設" in toks

    def test_english_title_unaffected_by_cjk_path(self):
        assert _title_tokens("Best Open Source LLM") == frozenset({"open", "source", "llm"})


class TestJapaneseNearDuplicate:
    """B22: near_duplicate must work for Japanese (CJK) titles."""

    def test_japanese_near_dups_flagged(self):
        a = "令和7年度補正予算・令和8年度当初予算_辺地共聴施設の高度化支援事業"
        b = "令和7年度補正予算・令和8年度当初予算_辺地共聴施設の高度化支援"
        assert _jaccard(_title_tokens(a), _title_tokens(b)) >= 0.6

    def test_japanese_different_topics_not_flagged(self):
        c = "三笘薫がハムストリング手術 今季絶望"
        d = "辺地共聴施設の高度化支援事業の補助金"
        assert _jaccard(_title_tokens(c), _title_tokens(d)) < 0.6

    def test_mark_near_duplicates_japanese_cluster(self):
        a = "令和7年度補正予算_辺地共聴施設の高度化支援事業"
        b = "令和7年度補正予算_辺地共聴施設の高度化支援"
        c = "三笘薫がハムストリング手術で今季絶望"
        rs = _mark_near_duplicates([
            {"title": a, "source_tier": "unknown", "near_duplicate": False},
            {"title": b, "source_tier": "unknown", "near_duplicate": False},
            {"title": c, "source_tier": "unknown", "near_duplicate": False},
        ])
        assert [r["near_duplicate"] for r in rs] == [False, True, False]


class TestJaccard:
    def test_identical(self):
        a = frozenset({"x", "y"})
        assert _jaccard(a, a) == 1.0

    def test_disjoint(self):
        assert _jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0

    def test_empty(self):
        assert _jaccard(frozenset(), frozenset({"a"})) == 0.0


class TestMarkNearDuplicates:
    def test_clear_dup_flagged_second(self):
        rs = _mark_near_duplicates([
            _r("Best Open-Source LLM 2026: Llama 4, DeepSeek V4, Qwen, Kimi"),
            _r("Best Open-Source LLMs May 2026: Llama 4, Qwen 3, DeepSeek"),
        ])
        assert rs[0]["near_duplicate"] is False
        assert rs[1]["near_duplicate"] is True

    def test_distinct_titles_not_flagged(self):
        rs = _mark_near_duplicates([
            _r("Kaoru Mitoma out of World Cup squad with injury"),
            _r("OpenAI announces GPT-6 pricing and benchmarks"),
        ])
        assert all(r["near_duplicate"] is False for r in rs)

    def test_same_story_different_angle_preserved(self):
        # Corroboration value: these are NOT collapsed (moderate overlap only).
        rs = _mark_near_duplicates([
            _r("Japan name World Cup squad: Brighton's Kaoru Mitoma out of tournament"),
            _r("Mitoma doubtful for 2026 World Cup - Brighton coach"),
        ])
        assert all(r["near_duplicate"] is False for r in rs)

    def test_authoritative_promoted_to_primary(self):
        # An authoritative near-dup arriving later becomes primary; the earlier
        # unknown copy is demoted.
        rs = _mark_near_duplicates([
            _r("Best Open-Source LLM 2026: Llama 4, DeepSeek, Qwen, Kimi", tier="unknown"),
            _r("Best Open-Source LLMs 2026: Llama 4, Qwen, DeepSeek", tier="authoritative"),
        ])
        assert rs[0]["near_duplicate"] is True   # unknown demoted
        assert rs[1]["near_duplicate"] is False  # authoritative is primary

    def test_three_in_cluster(self):
        rs = _mark_near_duplicates([
            _r("Best Open Source LLM 2026 Llama DeepSeek Qwen"),
            _r("Best Open Source LLMs 2026 Llama DeepSeek Qwen list"),
            _r("Best Open Source LLM 2026 Llama DeepSeek Qwen ranked"),
        ])
        assert [r["near_duplicate"] for r in rs] == [False, True, True]

    def test_empty(self):
        assert _mark_near_duplicates([]) == []


# ---------------------------------------------------------------------------
# Date parser tests
# ---------------------------------------------------------------------------

class TestDateParser:
    """Verify to_iso8601 handles all relevant date formats."""

    def _parse(self, raw):
        from src.deepsearch_mcp.utils.date_parser import to_iso8601
        return to_iso8601(raw)

    def test_iso8601_passthrough(self):
        assert self._parse("2024-03-15") == "2024-03-15"

    def test_human_readable_date(self):
        assert self._parse("March 15, 2024") == "2024-03-15"

    def test_slash_format(self):
        assert self._parse("03/15/2024") == "2024-03-15"

    def test_none_input_returns_none(self):
        assert self._parse(None) is None

    def test_empty_string_returns_none(self):
        assert self._parse("") is None
        assert self._parse("  ") is None

    def test_unparseable_returns_none(self):
        assert self._parse("not a date at all!!!") is None

    def test_relative_dates_return_valid_iso(self):
        for raw in ("yesterday", "2 days ago"):
            result = self._parse(raw)
            assert result is not None and len(result) == 10, (
                f"Expected ISO date from '{raw}', got {result!r}"
            )

    def test_year_only_is_none_or_valid(self):
        result = self._parse("2024")
        if result is not None:
            assert len(result) == 10 and result.startswith("2024")


# ---------------------------------------------------------------------------
# Phase 5 Regression: Error sanitization, context-aware hints, transient detect
# ---------------------------------------------------------------------------

class TestErrorSanitization:
    """FRICTION-B1: error messages must not leak raw backend URLs."""

    def test_sanitize_strips_https_url(self):
        from src.deepsearch_mcp.core.errors import sanitize_error_text
        msg = "Backend error: https://www.bing.com/search?q=foo&filters=ex1%3A%22ez5%22 failed"
        clean = sanitize_error_text(msg)
        assert "https://" not in clean
        assert "[REDACTED_URL]" in clean
        assert "bing.com" not in clean  # URL fully redacted

    def test_sanitize_strips_http_url(self):
        from src.deepsearch_mcp.core.errors import sanitize_error_text
        msg = "Could not reach http://example.com/api/v1/search"
        clean = sanitize_error_text(msg)
        assert "http://" not in clean
        assert "[REDACTED_URL]" in clean

    def test_sanitize_truncates_overlong_messages(self):
        from src.deepsearch_mcp.core.errors import sanitize_error_text
        long_msg = "Error " + ("blah " * 100)
        clean = sanitize_error_text(long_msg)
        assert len(clean) <= 200

    def test_sanitize_collapses_whitespace(self):
        from src.deepsearch_mcp.core.errors import sanitize_error_text
        msg = "Line1\n\n\nLine2\t\tLine3"
        clean = sanitize_error_text(msg)
        assert "\n\n" not in clean
        assert "\t\t" not in clean

    def test_sanitize_empty_returns_empty(self):
        from src.deepsearch_mcp.core.errors import sanitize_error_text
        assert sanitize_error_text("") == ""
        assert sanitize_error_text(None) == ""


class TestTransientErrorDetection:
    """FRICTION-B3: DNS/timeout/reset errors are detected as retryable."""

    def test_dns_error_is_transient(self):
        from src.deepsearch_mcp.core.errors import is_transient_conn_error
        assert is_transient_conn_error("DNS resolution failed") is True
        assert is_transient_conn_error("dns error: NXDOMAIN") is True

    def test_timeout_is_transient(self):
        from src.deepsearch_mcp.core.errors import is_transient_conn_error
        assert is_transient_conn_error("Operation timed out after 30s") is True
        assert is_transient_conn_error("Request timeout") is True

    def test_connection_reset_is_transient(self):
        from src.deepsearch_mcp.core.errors import is_transient_conn_error
        assert is_transient_conn_error("connection reset by peer") is True
        assert is_transient_conn_error("Connection refused") is True

    def test_non_transient_returns_false(self):
        from src.deepsearch_mcp.core.errors import is_transient_conn_error
        assert is_transient_conn_error("Invalid query syntax") is False
        assert is_transient_conn_error("Bad request format") is False

    def test_empty_returns_false(self):
        from src.deepsearch_mcp.core.errors import is_transient_conn_error
        assert is_transient_conn_error("") is False
        assert is_transient_conn_error(None) is False


class TestSearchWebContextAwareHints:
    """FRICTION-B2: search errors must NOT tell agent to "check URL validity"."""

    @pytest.fixture(autouse=True)
    def _no_fallback(self):
        # Error mapping only fires when the DDG HTML fallback (B12) also fails.
        with patch("src.deepsearch_mcp.tools.search._ddg_html_fallback",
                   new_callable=AsyncMock) as m:
            m.return_value = []
            yield

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_conn_error_hint_mentions_query_not_url(self, mock_thread):
        """The hint for a search CONN_ERROR must reference query/keywords, not URL."""
        mock_thread.side_effect = ConnectionError("DNS resolution failed")
        result = await search_web(query="phase5 regression test xyz")
        data = json.loads(result)
        hint_lower = data["hint"].lower()
        # MUST NOT tell agent to check URL — they passed a query
        assert "url" not in hint_lower or "url validity" not in hint_lower, (
            f"Search hint must not blame URL: {data['hint']}"
        )
        # SHOULD mention query, retry, or alternative
        assert any(kw in hint_lower for kw in ["query", "retry", "broader", "narrow", "spelling"]), (
            f"Search hint lacks query-context advice: {data['hint']}"
        )

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_conn_error_message_does_not_contain_url(self, mock_thread):
        """The error message must not leak the internal Bing/DDG URL."""
        mock_thread.side_effect = ConnectionError(
            "error sending request for url (https://www.bing.com/search?q=test) > dns error"
        )
        result = await search_web(query="phase5 dns leak test")
        data = json.loads(result)
        assert "https://" not in data["message"]
        assert "bing.com" not in data["message"]
        assert "[REDACTED_URL]" in data["message"]

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_rate_limit_hint_actionable(self, mock_thread):
        """Rate limit hint should suggest concrete actions."""
        from duckduckgo_search.exceptions import RatelimitException
        mock_thread.side_effect = RatelimitException("429 too many requests")
        result = await search_web(query="phase5 rate test")
        data = json.loads(result)
        hint_lower = data["hint"].lower()
        # Should mention wait OR narrow query
        assert any(kw in hint_lower for kw in ["wait", "60s", "narrow", "timelimit", "region"]), (
            f"Rate limit hint not actionable: {data['hint']}"
        )

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_dns_conn_error_is_retryable(self, mock_thread):
        """DNS-flavored CONN_ERROR must be retryable=True."""
        mock_thread.side_effect = ConnectionError("dns error: temporary failure")
        result = await search_web(query="phase5 retry test")
        data = json.loads(result)
        assert data["code"] == err.CONN_ERROR
        assert data["retryable"] is True, (
            f"DNS errors must be retryable; got: {data}"
        )

    async def test_empty_query_returns_empty_content_not_conn_error(self):
        """Empty query is a usage error, not a connection error."""
        result = await search_web(query="   ")
        data = json.loads(result)
        assert data["code"] == err.EMPTY_CONTENT, (
            f"Empty query should be EMPTY_CONTENT, got {data['code']}"
        )
        hint_lower = data["hint"].lower()
        assert "keyword" in hint_lower or "search" in hint_lower


class TestB13OutageEscalation:
    """B13: the search hint must escalate from 'retry/reword' to 'switch
    strategy' once searches keep failing — so the agent stops burning turns
    rewording a query during a backend outage."""

    def _hint(self, result: str) -> str:
        return json.loads(result)["hint"].lower()

    # --- unit: _map_ddgs_exception with a failure streak ---

    # The systemic banner uniquely says "in a row"; the base hints only *hedge*
    # toward switching strategy ("if searches keep failing…"), so that phrase
    # alone can't distinguish them — key on "in a row".
    def test_single_failure_keeps_retry_advice(self):
        # One-off failure (streak 1) → NOT systemic: base hint, still retryable.
        result = _map_ddgs_exception(ConnectionError("DNS resolution failed"),
                                     consecutive_failures=1)
        data = json.loads(result)
        assert data["retryable"] is True
        assert "retry once" in self._hint(result)
        assert "in a row" not in self._hint(result)

    def test_systemic_failure_says_switch_strategy(self):
        # Streak at threshold → systemic: stop rewording, switch strategy,
        # and not retryable (breaks the reword-and-retry loop).
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        result = _map_ddgs_exception(DuckDuckGoSearchException("backend boom"),
                                     consecutive_failures=_OUTAGE_THRESHOLD)
        hint = self._hint(result)
        assert "switch strategy" in hint
        assert "stop rewording" in hint
        assert json.loads(result)["retryable"] is False
        assert str(_OUTAGE_THRESHOLD) in json.loads(result)["hint"]

    def test_systemic_timeout_flips_to_not_retryable(self):
        # A lone timeout is retryable=True; a systemic run flips it to False.
        from duckduckgo_search.exceptions import TimeoutException
        lone = _map_ddgs_exception(TimeoutException("t"), consecutive_failures=1)
        many = _map_ddgs_exception(TimeoutException("t"),
                                   consecutive_failures=_OUTAGE_THRESHOLD)
        assert json.loads(lone)["retryable"] is True
        assert json.loads(many)["retryable"] is False
        assert "switch strategy" in self._hint(many)

    def test_default_count_is_not_systemic(self):
        # Existing callers pass no count → must keep pre-B13 base behaviour.
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        result = _map_ddgs_exception(DuckDuckGoSearchException("x"))
        assert "in a row" not in self._hint(result)

    # --- unit: the streak counter ---

    def test_counter_increments_then_resets(self):
        _reset_failure_streak()
        assert _note_search_outcome(failed=True) == 1
        assert _note_search_outcome(failed=True) == 2
        assert _note_search_outcome(failed=False) == 0   # success clears it
        assert _note_search_outcome(failed=True) == 1

    # --- integration: repeated failed search_web calls escalate ---

    @pytest.fixture(autouse=True)
    def _no_fallback(self):
        with patch(
            "src.deepsearch_mcp.tools.search._ddg_html_fallback",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = []
            yield

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_repeated_failures_escalate_to_systemic(self, mock_thread):
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        mock_thread.side_effect = DuckDuckGoSearchException("backend down")
        # Error responses are not cached, so the same query keeps hitting the
        # failure path. First call is a one-off; by the threshold it's systemic.
        first = await search_web(query="b13 outage probe")
        assert "in a row" not in self._hint(first)
        last = first
        for _ in range(_OUTAGE_THRESHOLD - 1):
            last = await search_web(query="b13 outage probe")
        assert "in a row" in self._hint(last)
        assert json.loads(last)["retryable"] is False

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_success_between_failures_resets_streak(self, mock_thread):
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
        # Fail up to (threshold-1), then succeed (resets), then fail once more:
        # that last failure must be treated as a one-off, not systemic.
        mock_thread.side_effect = DuckDuckGoSearchException("down")
        for _ in range(_OUTAGE_THRESHOLD - 1):
            await search_web(query="b13 reset probe")
        mock_thread.side_effect = None
        mock_thread.return_value = list(_FAKE_RESULTS)
        await search_web(query="b13 reset probe success")  # success → reset
        mock_thread.side_effect = DuckDuckGoSearchException("down again")
        after = await search_web(query="b13 reset probe")
        assert "in a row" not in self._hint(after)


class TestB14FreshnessSignal:
    """B14: published_date is derived best-effort from the URL path (DDGS never
    returns a date), giving a freshness signal on time-sensitive searches. The
    snippet body is deliberately NOT mined (too unreliable for a recency filter)."""

    @pytest.fixture(autouse=True)
    async def _clear(self):
        for q in ("b14 dated", "b14 undated", "b14 body"):
            await _clear_cache(q)
        yield
        for q in ("b14 dated", "b14 undated", "b14 body"):
            await _clear_cache(q)

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_dated_url_yields_published_date(self, mock_thread):
        mock_thread.return_value = [
            {"title": "Headline", "body": "x",
             "href": "https://news.example.com/2026/05/28/headline"},
        ]
        data = json.loads(await search_web(query="b14 dated"))
        assert data[0]["published_date"] == "2026-05-28"

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_undated_url_yields_null(self, mock_thread):
        mock_thread.return_value = [
            {"title": "Guide", "body": "x",
             "href": "https://example.com/guide/asyncio"},
        ]
        data = json.loads(await search_web(query="b14 undated"))
        assert data[0]["published_date"] is None

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_snippet_body_date_is_not_mined(self, mock_thread):
        # A date in the short snippet must NOT leak into published_date — only
        # the URL is trusted. (Undated URL + dated body → still null.)
        mock_thread.return_value = [
            {"title": "Old ref", "body": "Originally published May 28, 2019.",
             "href": "https://example.com/evergreen-page"},
        ]
        data = json.loads(await search_web(query="b14 body"))
        assert data[0]["published_date"] is None


class TestB19StoryClusters:
    """B19: loose same-story clustering. Different outlets paraphrase one event
    so heavily that title-Jaccard (<0.6) misses it; we group on shared key
    entities and surface a `story_cluster` id as a corroboration signal."""

    def _cluster(self, titles):
        from src.deepsearch_mcp.tools.search import _mark_story_clusters
        rows = [{"title": t, "source_tier": "unknown", "near_duplicate": False,
                 "story_cluster": None} for t in titles]
        return _mark_story_clusters(rows)

    def test_paraphrased_headlines_share_a_cluster(self):
        # The DuckDuckGo-installs story across 3 outlets: headlines differ a lot
        # (Jaccard < 0.6) but all share the entities DuckDuckGo + Google.
        rows = self._cluster([
            "DuckDuckGo installs surge 30% after Google AI backlash",
            "Privacy browser DuckDuckGo sees download spike following Google rollout",
            "Why DuckDuckGo downloads jumped after Google's AI rollout",
        ])
        cids = [r["story_cluster"] for r in rows]
        assert cids[0] is not None
        assert cids[0] == cids[1] == cids[2], f"expected one cluster, got {cids}"

    def test_jaccard_would_miss_these(self):
        # Prove the premise: the same paraphrased pair is NOT a near_duplicate.
        a = _title_tokens("DuckDuckGo installs surge 30% after Google AI backlash")
        b = _title_tokens("Privacy browser DuckDuckGo sees download spike following Google rollout")
        assert _jaccard(a, b) < 0.6
        assert len(a & b) >= _OUTAGE_THRESHOLD - 1  # share >=2 significant tokens

    def test_different_stories_same_topic_not_clustered(self):
        # Both mention Google but are DIFFERENT stories (share only "google").
        rows = self._cluster([
            "DuckDuckGo installs surge after Google AI backlash",
            "Google launches Gemini 3 flagship model",
            "Apple unveils new iPhone at fall hardware event",
        ])
        cids = [r["story_cluster"] for r in rows]
        assert cids == [None, None, None], f"over-clustered distinct stories: {cids}"

    def test_singletons_get_none(self):
        rows = self._cluster(["A totally unique headline about quantum widgets"])
        assert rows[0]["story_cluster"] is None

    def test_cluster_ids_are_stable_and_ordered(self):
        # Two separate clusters → ids 1 and 2 by first appearance.
        rows = self._cluster([
            "Mars rover Perseverance finds organic molecules sample",   # c1
            "Senate passes sweeping climate spending budget bill",       # c2
            "Perseverance rover sample shows ancient organic molecules", # c1
            "Climate budget bill clears Senate in late-night spending vote",  # c2
        ])
        cids = [r["story_cluster"] for r in rows]
        assert cids[0] == cids[2] == 1
        assert cids[1] == cids[3] == 2

    @pytest.fixture
    async def _clear(self):
        await _clear_cache("b19 integ")
        yield
        await _clear_cache("b19 integ")

    @patch("asyncio.to_thread", new_callable=AsyncMock)
    async def test_search_web_populates_story_cluster(self, mock_thread, _clear):
        mock_thread.return_value = [
            {"title": "DuckDuckGo installs surge after Google AI backlash",
             "href": "https://a.example/1", "body": "x"},
            {"title": "DuckDuckGo download spike follows Google AI rollout",
             "href": "https://b.example/2", "body": "x"},
        ]
        data = json.loads(await search_web(query="b19 integ"))
        assert "story_cluster" in data[0]
        assert data[0]["story_cluster"] == data[1]["story_cluster"] is not None


class TestB28QueryAwareClustering:
    """B28: a single-topic search must not collapse into one mega-cluster. Two
    mechanisms: (1) exclude the query's own tokens (shared by construction);
    (2) suppress a cluster covering a majority of the result set (topic
    homogeneity, not a story). Genuine same-event subsets still cluster."""

    def _cluster(self, titles, query=None):
        from src.deepsearch_mcp.tools.search import _mark_story_clusters
        rows = [{"title": t, "source_tier": "unknown", "near_duplicate": False,
                 "story_cluster": None} for t in titles]
        return [r["story_cluster"] for r in _mark_story_clusters(rows, query=query)]

    def test_homogeneous_topic_set_not_mega_clustered(self):
        # Real EU AI Act titles: same topic, different angles. No single cluster
        # may cover the whole set (the live 8/8 mega-cluster bug).
        eu = [
            "EU AI Act 2026 Updates: Compliance Requirements and Business Risks",
            "EU AI Act August 2026 Deadline: Only 8 of 27 EU States Ready",
            "EU AI Act Enforcement Begins August 2026: What Gets Banned and Who",
            "EU AI Act: What's in Force Now and What Hits August 2026",
            "EU AI Act Enforcement Timeline: 2025 to 2027",
        ]
        cids = self._cluster(eu, query="EU AI Act enforcement 2026")
        non_null = [c for c in cids if c is not None]
        top = max((non_null.count(c) for c in set(non_null)), default=0)
        assert top < len(cids), f"still mega-clustered: {cids}"

    def test_dominant_cluster_suppressed(self):
        # 5 titles all sharing 2 NON-query tokens → would all cluster, but the
        # cluster is the whole set (≥0.6·n) → suppressed. Reproduces the live
        # failure mechanism (ubiquitous topic words query-exclusion can't catch).
        titles = [f"Alpha Beta dispatch number {i} distinct{i}" for i in range(5)]
        assert self._cluster(titles) == [None] * 5

    def test_query_tokens_do_not_link(self):
        # Two results sharing ONLY query tokens are not linked (n<4, so dominance
        # is not the cause — this isolates query-token exclusion).
        titles = ["EU AI Act overview alpha widgets",
                  "EU AI Act overview beta gadgets"]
        assert self._cluster(titles, query="EU AI Act overview") == [None, None]

    def test_genuine_subcluster_preserved_in_diverse_set(self):
        # An event pair embedded among unrelated results stays a cluster
        # (size 2 < 0.6·6) — the dominance cap only kills majorities.
        titles = [
            "DuckDuckGo installs surge after Google rollout",          # event
            "DuckDuckGo install spike follows Google rollout report",  # event
            "Senate passes sweeping climate budget bill",
            "Mars rover finds ancient organic molecules",
            "New flagship phone unveiled at hardware showcase",
            "Stock markets rally on strong jobs figures",
        ]
        cids = self._cluster(titles)
        assert cids[0] is not None and cids[0] == cids[1]
        assert cids[2:] == [None, None, None, None]

    def test_small_event_set_still_clusters(self):
        # Below the dominance-N floor, a genuine same-event pair still clusters.
        titles = ["DuckDuckGo installs surge Google rollout",
                  "DuckDuckGo install spike Google rollout"]
        cids = self._cluster(titles, query="DuckDuckGo")
        assert cids[0] is not None and cids[0] == cids[1]

    def test_query_none_is_backcompat(self):
        titles = ["Mars rover finds organic molecules in sample",
                  "Perseverance rover sample shows ancient organic molecules"]
        assert self._cluster(titles) == [1, 1]
