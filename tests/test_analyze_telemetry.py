"""
Tests for the aggregate analyzer's cold-start honesty (evals/analyze_telemetry.py).

Motivated by the 2026-05-30 live-activation run: a 9-row real telemetry DB made
the analyzer confidently say "add a domain adapter" off 3 samples. With thin
data, an alert is a coin-flip and "no alerts" is not "healthy". These tests pin
the verdict logic so it can never silently over-claim again.
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evals"))

from evals import analyze_telemetry as az


def _report(total_rows, hotspots=None, skew=None):
    return az.Report(
        db_path="(test)",
        total_rows=total_rows,
        failure_hotspots=hotspots or [],
        token_inefficiency=[],
        error_patterns=[],
        skew_warnings=skew or [],
    )


def _hotspot():
    return az.DomainFailure(
        domain="httpbin.org", total_calls=3, failures=1,
        failure_rate_pct=33.3, top_failure_code="BLOCKED_403", alert=True,
    )


# ---------------------------------------------------------------------------
# Cold-start verdict: thin data must not present as healthy / actionable
# ---------------------------------------------------------------------------

class TestColdStartVerdict:
    def test_thin_data_shows_low_confidence_banner(self, capsys):
        az._print_report_text(_report(total_rows=9))
        out = capsys.readouterr().out
        assert "LOW CONFIDENCE" in out

    def test_thin_data_no_alerts_is_not_healthy(self, capsys):
        az._print_report_text(_report(total_rows=9))
        out = capsys.readouterr().out
        assert "not enough data" in out.lower()
        assert "System is healthy" not in out

    def test_thin_data_alert_is_provisional(self, capsys):
        az._print_report_text(_report(total_rows=9, hotspots=[_hotspot()]))
        out = capsys.readouterr().out
        assert "PROVISIONAL" in out
        assert "httpbin.org" in out

    def test_enough_data_no_alerts_is_healthy(self, capsys):
        az._print_report_text(_report(total_rows=120))
        out = capsys.readouterr().out
        assert "System is healthy" in out
        assert "LOW CONFIDENCE" not in out

    def test_enough_data_alert_is_not_provisional(self, capsys):
        az._print_report_text(_report(total_rows=120, hotspots=[_hotspot()]))
        out = capsys.readouterr().out
        assert "PROVISIONAL" not in out
        assert "httpbin.org" in out

    def test_threshold_boundary(self, capsys):
        # Exactly at the floor counts as enough (not thin).
        az._print_report_text(_report(total_rows=az.MIN_ROWS_FOR_CONFIDENCE))
        assert "LOW CONFIDENCE" not in capsys.readouterr().out


class TestSkewGuard:
    """Row count alone is not trust — a tool that is ~100% one error skews it."""

    def test_skew_keeps_low_confidence_even_with_many_rows(self, capsys):
        # 500 rows, but a tool is 100% one error → still PROVISIONAL.
        rep = _report(total_rows=500, hotspots=[_hotspot()],
                      skew=["search_web: 100% CONN_ERROR (200/200) — systemic failure, not a health signal"])
        az._print_report_text(rep)
        out = capsys.readouterr().out
        assert "LOW CONFIDENCE" in out
        assert "skewed data" in out
        assert "PROVISIONAL" in out

    def test_skew_message_names_the_tool(self, capsys):
        az._print_report_text(_report(total_rows=500, skew=["search_web: 100% CONN_ERROR (200/200) — systemic"]))
        out = capsys.readouterr().out
        assert "search_web" in out
        assert "more rows will NOT fix skew" in out

    def test_no_skew_no_banner_when_enough_rows(self, capsys):
        az._print_report_text(_report(total_rows=500, skew=[]))
        assert "LOW CONFIDENCE" not in capsys.readouterr().out


class TestToolSkewDetection:
    """tool_skew() over a seeded DB."""

    def test_detects_single_tool_total_failure(self, tmp_path):
        db = tmp_path / "telemetry.db"
        rows = [("2026-05-30T00:00:00Z", "search_web", "q", "CONN_ERROR", 98, 100, None)
                for _ in range(5)]
        _seed(db, rows)
        rep = az.build_report(db)
        assert any("search_web" in w and "CONN_ERROR" in w for w in rep.skew_warnings)

    def test_healthy_tool_no_skew(self, tmp_path):
        db = tmp_path / "telemetry.db"
        rows = [("2026-05-30T00:00:00Z", "read_article", "u", "success", 100, 200, "example.com")
                for _ in range(5)]
        _seed(db, rows)
        rep = az.build_report(db)
        assert rep.skew_warnings == []

    def test_below_min_calls_not_judged(self, tmp_path):
        db = tmp_path / "telemetry.db"
        rows = [("2026-05-30T00:00:00Z", "search_web", "q", "CONN_ERROR", 98, 100, None)
                for _ in range(2)]  # < SKEW_MIN_CALLS
        _seed(db, rows)
        rep = az.build_report(db)
        assert rep.skew_warnings == []


# ---------------------------------------------------------------------------
# build_report end-to-end on a small seeded DB
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, tool_name TEXT, input_summary TEXT, status TEXT,
    tokens_approx INTEGER, latency_ms INTEGER, domain TEXT
);
"""


def _seed(path, rows):
    con = sqlite3.connect(str(path))
    con.executescript(_SCHEMA)
    con.executemany(
        "INSERT INTO telemetry "
        "(timestamp,tool_name,input_summary,status,tokens_approx,latency_ms,domain) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    con.close()


class TestBuildReport:
    def test_counts_rows_and_finds_hotspot(self, tmp_path):
        db = tmp_path / "telemetry.db"
        rows = []
        # httpbin.org: 3 read_article calls, 2 failures → hotspot (≥15%, ≥3)
        for status in ("success", "BLOCKED_403", "BLOCKED_403"):
            rows.append(("2026-05-30T00:00:00Z", "read_article", "u", status,
                         100, 200, "httpbin.org"))
        _seed(db, rows)
        report = az.build_report(db)
        assert report.total_rows == 3
        domains = {h.domain: h for h in report.failure_hotspots}
        assert "httpbin.org" in domains
        assert domains["httpbin.org"].alert is True
        assert domains["httpbin.org"].top_failure_code == "BLOCKED_403"

    def test_clean_domain_no_alert(self, tmp_path):
        db = tmp_path / "telemetry.db"
        rows = [
            ("2026-05-30T00:00:00Z", "read_article", "u", "success", 100, 200, "example.com")
            for _ in range(5)
        ]
        _seed(db, rows)
        report = az.build_report(db)
        hot = {h.domain: h for h in report.failure_hotspots}
        assert hot["example.com"].alert is False
