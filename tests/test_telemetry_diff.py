"""Tests for evals/telemetry_diff.py (B4) — before/after telemetry comparison."""

from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals import telemetry_diff as td

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


def _row(tool="read_article", status="success", tokens=1000, latency=200, domain="x.com"):
    return ("2026-06-01T00:00:00Z", tool, "u", status, tokens, latency, domain)


def _metrics(tmp_path, rows, name="t.db"):
    db = tmp_path / name
    _seed(db, rows)
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    try:
        return td.snapshot_metrics(con)
    finally:
        con.close()


class TestSnapshotMetrics:
    def test_counts_and_success_rate(self, tmp_path):
        rows = [_row(status="success"), _row(status="success"),
                _row(status="BLOCKED_403")]
        m = _metrics(tmp_path, rows)
        assert m["total_rows"] == 3
        assert m["overall_success_rate"] == 66.7
        assert m["tools"]["read_article"]["success_rate"] == 66.7

    def test_avg_tokens_only_over_successes(self, tmp_path):
        # Error rows (tiny token counts) must not drag the extraction-length avg.
        rows = [_row(status="success", tokens=2000),
                _row(status="success", tokens=2000),
                _row(status="BLOCKED_403", tokens=20)]
        m = _metrics(tmp_path, rows)
        assert m["tools"]["read_article"]["avg_tokens_success"] == 2000

    def test_error_codes_exclude_success(self, tmp_path):
        rows = [_row(status="success"), _row(status="TIMEOUT"),
                _row(status="TIMEOUT")]
        m = _metrics(tmp_path, rows)
        assert m["error_codes"] == {"TIMEOUT": 2}


class TestDiffSnapshots:
    def _m(self, rows, tmp_path, name):
        return _metrics(tmp_path, rows, name)

    def test_success_rate_drop_is_flagged(self, tmp_path):
        before = self._m([_row(status="success")] * 10, tmp_path, "b.db")
        after = self._m([_row(status="success")] * 5
                        + [_row(status="BLOCKED_403")] * 5, tmp_path, "a.db")
        d = td.diff_snapshots(before, after)
        assert d["overall_success_rate"]["delta_pts"] == -50.0
        assert any("success rate dropped" in n for n in d["notes"])

    def test_new_error_code_is_flagged(self, tmp_path):
        before = self._m([_row(status="success")] * 5, tmp_path, "b.db")
        after = self._m([_row(status="success")] * 4
                        + [_row(status="EMPTY_CONTENT")], tmp_path, "a.db")
        d = td.diff_snapshots(before, after)
        assert "EMPTY_CONTENT" in d["error_codes"]["new"]
        assert any("new error code" in n and "EMPTY_CONTENT" in n for n in d["notes"])

    def test_token_pct_change_computed(self, tmp_path):
        before = self._m([_row(status="success", tokens=1000)] * 4, tmp_path, "b.db")
        after = self._m([_row(status="success", tokens=1200)] * 4, tmp_path, "a.db")
        d = td.diff_snapshots(before, after)
        assert d["tools"]["read_article"]["avg_tokens_success"]["pct_change"] == 20.0

    def test_clean_diff_has_no_notes(self, tmp_path):
        before = self._m([_row(status="success")] * 60, tmp_path, "b.db")
        after = self._m([_row(status="success")] * 60, tmp_path, "a.db")
        d = td.diff_snapshots(before, after)
        assert d["notes"] == []
        assert d["provisional"] is False

    def test_thin_data_is_provisional(self, tmp_path):
        before = self._m([_row(status="success")] * 3, tmp_path, "b.db")
        after = self._m([_row(status="success")] * 3, tmp_path, "a.db")
        d = td.diff_snapshots(before, after)
        assert d["provisional"] is True


class TestDiffCli:
    def test_build_diff_exposes_expected_keys(self, tmp_path):
        b, a = tmp_path / "before.db", tmp_path / "after.db"
        _seed(b, [_row(status="success")] * 5)
        _seed(a, [_row(status="success")] * 5)
        d = td.build_diff(str(b), str(a))
        assert {"rows", "overall_success_rate", "tools", "error_codes", "notes"} <= set(d)

    def test_main_text_and_json_modes(self, tmp_path, capsys):
        b, a = tmp_path / "before.db", tmp_path / "after.db"
        _seed(b, [_row(status="success")] * 5)
        _seed(a, [_row(status="success")] * 5)
        assert td.main(["--before", str(b), "--after", str(a)]) == 0
        capsys.readouterr()  # discard text output
        assert td.main(["--before", str(b), "--after", str(a), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["rows"] == {"before": 5, "after": 5}


class TestExtractionDriftRule6:
    """B6 / Operations Rule 6: flag ±10% read_article extraction-length drift,
    with a sample-size guard so a 1-extraction average can't cry wolf."""

    def _m(self, rows, tmp_path, name):
        return _metrics(tmp_path, rows, name)

    def test_drift_above_threshold_is_flagged(self, tmp_path):
        before = self._m([_row(status="success", tokens=1000)] * 6, tmp_path, "b.db")
        after = self._m([_row(status="success", tokens=1200)] * 6, tmp_path, "a.db")  # +20%
        alert = td.extraction_length_drift(before, after)
        assert alert is not None and "Rule 6" in alert and "grew" in alert
        # …and it surfaces in the diff notes
        assert any("Rule 6" in n for n in td.diff_snapshots(before, after)["notes"])

    def test_shrink_is_flagged_with_direction(self, tmp_path):
        before = self._m([_row(status="success", tokens=2000)] * 6, tmp_path, "b.db")
        after = self._m([_row(status="success", tokens=1500)] * 6, tmp_path, "a.db")  # -25%
        alert = td.extraction_length_drift(before, after)
        assert alert is not None and "shrank" in alert

    def test_small_drift_not_flagged(self, tmp_path):
        before = self._m([_row(status="success", tokens=1000)] * 6, tmp_path, "b.db")
        after = self._m([_row(status="success", tokens=1050)] * 6, tmp_path, "a.db")  # +5%
        assert td.extraction_length_drift(before, after) is None

    def test_insufficient_samples_not_flagged(self, tmp_path):
        # Big swing but only a few extractions → must NOT flag (sample guard).
        before = self._m([_row(status="success", tokens=1000)] * 2, tmp_path, "b.db")
        after = self._m([_row(status="success", tokens=3000)] * 2, tmp_path, "a.db")
        assert td.extraction_length_drift(before, after) is None

    def test_only_read_article_counts(self, tmp_path):
        # search_web token swings are not "extraction length" → not Rule 6.
        before = self._m([_row(tool="search_web", status="success", tokens=100)] * 6,
                         tmp_path, "b.db")
        after = self._m([_row(tool="search_web", status="success", tokens=500)] * 6,
                        tmp_path, "a.db")
        assert td.extraction_length_drift(before, after) is None
