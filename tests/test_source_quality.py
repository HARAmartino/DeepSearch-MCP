"""Tests for source-quality classification (B15)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.deepsearch_mcp.core.source_quality import (
    AUTHORITATIVE,
    UNKNOWN,
    classify_source,
)


class TestAuthoritative:
    def test_wire_service(self):
        assert classify_source("https://www.reuters.com/tech/x") == AUTHORITATIVE

    def test_tech_press(self):
        assert classify_source("https://www.theverge.com/2026/x") == AUTHORITATIVE

    def test_arxiv(self):
        assert classify_source("https://arxiv.org/abs/2401.00001") == AUTHORITATIVE

    def test_gov_tld(self):
        assert classify_source("https://www.nasa.gov/news") == AUTHORITATIVE

    def test_edu_tld(self):
        assert classify_source("https://cs.stanford.edu/page") == AUTHORITATIVE

    def test_ac_uk_tld(self):
        assert classify_source("https://www.cam.ac.uk/research") == AUTHORITATIVE

    # B21: non-US/UK national government TLDs.
    def test_japanese_government(self):
        assert classify_source("https://www.soumu.go.jp/menu_seisaku/x.html") == AUTHORITATIVE

    def test_japanese_local_government(self):
        assert classify_source("https://www.city.kure.lg.jp/soshiki/x.html") == AUTHORITATIVE

    def test_india_government_subdomain(self):
        assert classify_source("https://india.gov.in/page") == AUTHORITATIVE

    def test_france_government(self):
        assert classify_source("https://economie.gouv.fr/page") == AUTHORITATIVE

    def test_eu_institutions(self):
        assert classify_source("https://ec.europa.eu/info") == AUTHORITATIVE

    def test_full_domain_suffix_matches_bare_host(self):
        # canada.ca / europa.eu are full domains: www-stripped host == suffix.
        assert classify_source("https://www.canada.ca/en") == AUTHORITATIVE
        assert classify_source("https://www.europa.eu/x") == AUTHORITATIVE

    def test_official_company_blog(self):
        assert classify_source("https://ai.meta.com/blog/llama") == AUTHORITATIVE
        assert classify_source("https://openai.com/index/x") == AUTHORITATIVE

    def test_github_primary_source(self):
        assert classify_source("https://github.com/modelcontextprotocol") == AUTHORITATIVE

    # B24: industry analysts / research / consulting.
    def test_analyst_firms(self):
        for url in ["https://www.gartner.com/en/x", "https://www.forrester.com/x",
                    "https://www.idc.com/x"]:
            assert classify_source(url) == AUTHORITATIVE

    def test_consulting_research(self):
        for url in ["https://www.deloitte.com/us/en/insights/x",
                    "https://www.mckinsey.com/insights/x", "https://www.bcg.com/x"]:
            assert classify_source(url) == AUTHORITATIVE

    def test_crunchbase_news_subdomain(self):
        assert classify_source("https://news.crunchbase.com/venture/x") == AUTHORITATIVE

    def test_ieee_computer_society_and_hbr(self):
        assert classify_source("https://www.computer.org/press-room/x") == AUTHORITATIVE
        assert classify_source("https://hbr.org/2026/05/x") == AUTHORITATIVE

    def test_subdomain_of_authoritative(self):
        # news.bbc.co.uk → bbc.co.uk is trusted
        assert classify_source("https://news.bbc.co.uk/story") == AUTHORITATIVE

    def test_www_stripped(self):
        assert classify_source("https://www.bbc.com/news") == AUTHORITATIVE


class TestUnknown:
    def test_content_farms_are_unknown_not_misjudged(self):
        # The real Meta-run farms: we do NOT claim "low quality", just "unknown".
        for url in [
            "https://codersera.com/blog/best-open-source-llm-2026",
            "https://futureagi.com/blog/best-llms-may-2026/",
            "https://www.web3aiblog.com/blog/x",
            "https://benchlm.ai/best/meta-models",
        ]:
            assert classify_source(url) == UNKNOWN

    def test_random_blog_is_unknown(self):
        assert classify_source("https://someones-blog.example/post") == UNKNOWN

    def test_empty_or_malformed_is_unknown(self):
        assert classify_source("") == UNKNOWN
        assert classify_source("not a url") == UNKNOWN

    def test_lookalike_domain_not_authoritative(self):
        # A domain that merely CONTAINS a trusted name must not match.
        assert classify_source("https://reuters.com.phishing.example/x") == UNKNOWN
        assert classify_source("https://notreuters.com/x") == UNKNOWN

    def test_non_gov_jp_is_unknown(self):
        # B21 safety: a regular Japanese company / geographic .jp is NOT gov.
        assert classify_source("https://www.sony.co.jp/") == UNKNOWN
        assert classify_source("https://town.otoyo.kochi.jp/x") == UNKNOWN  # geographic .jp

    def test_contributor_networks_excluded(self):
        # B24: Forbes/Inc. run contributor networks → quality is per-author,
        # not per-domain → deliberately NOT authoritative.
        assert classify_source("https://www.forbes.com/sites/x/2026/x") == UNKNOWN
        assert classify_source("https://www.inc.com/x") == UNKNOWN


class TestSearchResultIntegration:
    def test_searchresult_defaults_unknown(self):
        from src.deepsearch_mcp.core.models import SearchResult
        r = SearchResult(title="t", url="https://x.example", body="b")
        assert r.source_tier == "unknown"

    def test_searchresult_carries_tier(self):
        from src.deepsearch_mcp.core.models import SearchResult
        r = SearchResult(title="t", url="https://reuters.com/x", body="b",
                         source_tier=classify_source("https://reuters.com/x"))
        assert r.model_dump()["source_tier"] == "authoritative"
