"""
Tests for the Noise-Leak Auditor (evals/dogfood_audit.py).

The auditor is the systematic CHECK step of the dogfooding loop: it scans
post-cleaner extraction output for residual noise the cleaner missed.

Two-tier design (regression target of the 2026-05-29 cycle):
  - STRONG signals (affiliate / sponsor / legal) flag at ANY line length —
    the bug that motivated this tier was a 16-word affiliate-disclosure
    sentence the old length-gated auditor silently skipped.
  - SOFT signals (promo CTA / metadata stub / engagement counts) flag ONLY
    on short lines, so real prose containing a word like "share" is spared.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evals"))

from dogfood_audit import audit_markdown, audit_report, matched_signal


def _categories(text: str) -> list[str]:
    return [f.category for f in audit_markdown(text)]


def _texts(text: str) -> list[str]:
    return [f.text for f in audit_markdown(text)]


# ---------------------------------------------------------------------------
# STRONG tier — fire regardless of line length
# ---------------------------------------------------------------------------

class TestStrongTier:
    def test_long_affiliate_disclosure_flagged(self):
        """The exact pattern dogfooding found: a >14-word affiliate sentence."""
        line = ("This article may contain affiliate links. If you buy through "
                "them we may earn a commission on the sale.")
        assert len(line.split()) > 14, "fixture must exceed the soft word gate"
        cats = _categories(line)
        assert cats == ["AFFILIATE_SPONSOR"], f"got {cats}"

    def test_sponsored_content_flagged(self):
        assert _categories("This is sponsored content from our partner.") == ["AFFILIATE_SPONSOR"]

    def test_paid_partnership_flagged(self):
        assert _categories("Produced in paid partnership with Acme Corp.") == ["AFFILIATE_SPONSOR"]

    def test_long_legal_footer_flagged(self):
        line = ("© 2026 ZDNet, a Red Ventures company. All rights reserved. "
                "Use of this site constitutes acceptance of our Terms of Service.")
        assert "LEGAL_FOOTER" in _categories(line)

    def test_advertisement_flagged(self):
        assert _categories("Advertisement") == ["AFFILIATE_SPONSOR"]


# ---------------------------------------------------------------------------
# SOFT tier — only on short lines
# ---------------------------------------------------------------------------

class TestSoftTier:
    def test_short_promo_cta_flagged(self):
        assert _categories("Subscribe to our newsletter") == ["PROMO_CTA"]

    def test_share_this_flagged(self):
        assert _categories("Share this article") == ["PROMO_CTA"]

    def test_metadata_by_author_flagged(self):
        assert _categories("By Jane Doe") == ["METADATA_STUB"]

    def test_metadata_tags_flagged(self):
        assert _categories("Tags: AI, agents, MCP") == ["METADATA_STUB"]

    def test_engagement_share_count_with_k_suffix(self):
        assert _categories("1.2K shares") == ["ENGAGEMENT_BAIT"]

    def test_engagement_comment_count(self):
        assert _categories("View all 23 comments") == ["ENGAGEMENT_BAIT"]

    def test_long_line_with_promo_word_NOT_flagged(self):
        """A real sentence containing 'share' must not trip the soft tier."""
        line = ("We share a common goal of building better developer tools, "
                "and that mission guides every design decision we make here.")
        assert audit_markdown(line) == []

    def test_long_line_with_published_NOT_flagged(self):
        line = ("The company published its quarterly results in a detailed "
                "report that analysts had been waiting for all spring.")
        assert audit_markdown(line) == []


# ---------------------------------------------------------------------------
# Structural skipping
# ---------------------------------------------------------------------------

class TestStructuralSkipping:
    def test_frontmatter_skipped(self):
        text = (
            "---\n"
            'title: "Subscribe Weekly: a newsletter about cats"\n'
            "author: \"By Someone\"\n"
            "---\n\n"
            "Real body paragraph that is clearly article content and long enough.\n"
        )
        # The frontmatter contains 'Subscribe' and 'By' but must be ignored.
        assert audit_markdown(text) == []

    def test_code_block_skipped(self):
        text = (
            "# Heading\n\n"
            "```python\n"
            "subscribe()  # Subscribe to the event bus\n"
            "share_on('twitter')\n"
            "```\n\n"
            "Normal prose paragraph that is long enough to be considered content.\n"
        )
        assert audit_markdown(text) == []

    def test_heading_skipped(self):
        # A heading literally named "Subscribe" is structure, not a CTA line.
        assert audit_markdown("## Subscribe") == []

    def test_table_row_skipped(self):
        assert audit_markdown("| Subscribe | Free |") == []

    def test_clean_article_zero_findings(self):
        text = (
            "---\n"
            'title: "How Async IO Works"\n'
            "---\n\n"
            "# How Async IO Works\n\n"
            "Asynchronous IO is a concurrent programming design supported in "
            "Python through the asyncio library and its event loop machinery.\n\n"
            "## The Event Loop\n\n"
            "The event loop schedules coroutines and runs callbacks when the "
            "underlying IO operations complete their work.\n"
        )
        assert audit_markdown(text) == []


# ---------------------------------------------------------------------------
# Report helper + edge cases
# ---------------------------------------------------------------------------

class TestMatchedSignal:
    """matched_signal() exposes the substring a heuristic matched (for B7)."""

    def test_returns_category_and_substring(self):
        line = "This article may contain affiliate links."
        result = matched_signal(line)
        assert result is not None
        category, signal = result
        assert category == "AFFILIATE_SPONSOR"
        # The matched span is the leftmost signal (the disclosure opener);
        # it must be a real substring of the line, not the whole line verbatim.
        assert signal.lower() in line.lower()
        assert len(signal.split()) >= 2

    def test_soft_signal_substring(self):
        result = matched_signal("View all 23 comments")
        assert result is not None
        category, signal = result
        assert category == "ENGAGEMENT_BAIT"
        assert "23" in signal  # the matched span includes the count

    def test_prose_returns_none(self):
        assert matched_signal("The event loop schedules coroutines to run.") is None

    # Real-usage regression (docs.python.org, 2026-05-30): the social-count
    # pattern's "[\d.,]+" matched a bare comma, so "...concurrency, like"
    # falsely flagged as ENGAGEMENT_BAIT. Counts must require a leading digit.
    def test_comma_then_word_not_flagged(self):
        assert matched_signal("The asyncio components that enable concurrency, like") is None
        assert matched_signal("we share, like comments below") is None

    def test_real_social_counts_still_flagged(self):
        assert matched_signal("1.2K shares")[0] == "ENGAGEMENT_BAIT"
        assert matched_signal("47 comments")[0] == "ENGAGEMENT_BAIT"


class TestAuditReport:
    def test_report_counts_findings(self):
        text = "Subscribe now\n\nReal long paragraph of genuine article content here.\n"
        block, n = audit_report("sample", text)
        assert n == 1
        assert "sample" in block
        assert "PROMO_CTA" in block

    def test_report_clean_says_clean(self):
        block, n = audit_report("clean", "A perfectly ordinary sentence of article prose.")
        assert n == 0
        assert "clean" in block.lower()

    def test_empty_text_no_findings(self):
        assert audit_markdown("") == []
        assert audit_markdown("   \n\n  ") == []

    def test_line_numbers_are_one_based(self):
        text = "Real opening paragraph long enough to be content.\n\nSubscribe now\n"
        findings = audit_markdown(text)
        assert len(findings) == 1
        assert findings[0].line_no == 3


# ---------------------------------------------------------------------------
# Integration: the auditor must agree with the cleaner on the real fixtures
# ---------------------------------------------------------------------------

class TestAgainstRealFixtures:
    """After cleaning, all dogfood fixtures must audit clean (0 residual noise)."""

    def _audit_fixture(self, html: str, url: str) -> list:
        from src.deepsearch_mcp.core.extractor import build_frontmatter, extract
        body, meta = extract(html, url=url)
        full = build_frontmatter(meta) + "\n\n" + body
        return audit_markdown(full)

    def test_zdnet_fixture_audits_clean_after_cleaner(self):
        """Regression: the affiliate disclosure must be gone post-cleaner."""
        from dogfood_research import ZDNET_HTML
        findings = self._audit_fixture(
            ZDNET_HTML, "https://www.zdnet.com/article/x/"
        )
        assert findings == [], f"residual noise leaked: {[str(f) for f in findings]}"

    def test_all_dogfood_fixtures_audit_clean(self):
        from dogfood_research import (
            DEVTO_HTML,
            LANGCHAIN_HTML,
            TECHCRUNCH_HTML,
            ZDNET_HTML,
        )
        for html, url in [
            (TECHCRUNCH_HTML, "https://techcrunch.com/x/"),
            (LANGCHAIN_HTML, "https://blog.langchain.dev/y/"),
            (DEVTO_HTML, "https://dev.to/z/"),
            (ZDNET_HTML, "https://www.zdnet.com/w/"),
        ]:
            findings = self._audit_fixture(html, url)
            assert findings == [], f"{url} leaked: {[str(f) for f in findings]}"
