"""
Day 2 Operations — Telemetry analyzer.

Reads `<DEEPSEARCH_TELEMETRY_DIR>/telemetry.db` and emits three reports that
drive automated improvements:

  1. Extraction Failure Hotspots
     Domains where `read_article` returns BLOCKED_403 / EMPTY_CONTENT /
     UNSUPPORTED_FORMAT / TIMEOUT most often.
     ➜ Target for domain-specific adapters in `core/extractor.py`.

  2. Token Inefficiency
     Domains with high mean `tokens_approx` for successful read_article
     responses — high outputs may indicate residual noise that escaped
     the cleaner.
     ➜ Target for new regex patterns in `utils/cleaner.py` or
        domain pre-processors.

  3. Error Pattern Analysis
     Frequency table of (tool, status) for non-success rows, ordered by
     count. Surfaces sudden spikes in RATE_LIMITED or CONN_ERROR that
     warrant impersonate-target rotation or backoff tuning.

Run:
    python evals/analyze_telemetry.py
    python evals/analyze_telemetry.py --json
    DEEPSEARCH_TELEMETRY_DIR=/tmp/sample python evals/analyze_telemetry.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Statuses that signal an extraction failure (excluding success)
_FAILURE_STATUSES = ("BLOCKED_403", "EMPTY_CONTENT", "UNSUPPORTED_FORMAT", "TIMEOUT")

# Thresholds — exceeding any of these flags the row as an action item
FAILURE_RATE_ALERT = 15.0          # % — domain failure rate that triggers adapter work
TOKEN_INEFFICIENCY_ALERT = 3000    # avg tokens per article — above = likely noise
MIN_SAMPLES = 3                    # min observations per group for statistical meaning

# Cold-start guard: below this many total rows the analyzer must NOT present
# its verdicts as actionable. With thin data, a "✅ no alerts" is just
# "not enough data to see one yet" — and an alert from 3 samples is a
# coin-flip, not a trend. The real 9-row activation run on 2026-05-30
# proved the old behavior over-claimed (it said "add a domain adapter" off
# 3 samples). Below the floor, alerts are shown but labelled PROVISIONAL.
MIN_ROWS_FOR_CONFIDENCE = 50

# Representativeness guard: row COUNT alone is not trust. 50 rows of a contrived
# battery (or of a dead backend echoing one error) is still unrepresentative.
# If a tool is overwhelmingly one non-success status, the telemetry picture is
# skewed by a systemic failure — verdicts stay PROVISIONAL regardless of volume.
# Discovered 2026-05-30: the only data collectable in a restricted env was
# search_web = 100% CONN_ERROR (blocked backend); crossing the row floor by
# re-running the collector would have manufactured false confidence.
SKEW_DOMINANCE = 0.90              # one non-success status ≥ this share of a tool
SKEW_MIN_CALLS = 3                 # only judge a tool with at least this many calls


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DomainFailure:
    domain: str
    total_calls: int
    failures: int
    failure_rate_pct: float
    top_failure_code: str
    alert: bool


@dataclass
class TokenInefficiency:
    domain: str
    avg_tokens: float
    max_tokens: int
    samples: int
    alert: bool


@dataclass
class ErrorPattern:
    tool_name: str
    status: str
    occurrences: int
    pct_of_tool_errors: float


@dataclass
class Report:
    db_path: str
    total_rows: int
    failure_hotspots: list[DomainFailure]
    token_inefficiency: list[TokenInefficiency]
    error_patterns: list[ErrorPattern]
    skew_warnings: list[str]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _resolve_db_path(override: str | None = None) -> Path:
    if override:
        return Path(override)
    base = os.getenv("DEEPSEARCH_TELEMETRY_DIR", "./.cache")
    return Path(base) / "telemetry.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"ERROR: telemetry DB not found at {db_path}", file=sys.stderr)
        print("  Set DEEPSEARCH_TELEMETRY_DIR or pass --db PATH.", file=sys.stderr)
        sys.exit(1)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def failure_hotspots(con: sqlite3.Connection, top_n: int = 5) -> list[DomainFailure]:
    """Domains where read_article fails most."""
    failure_clause = ",".join(f"'{s}'" for s in _FAILURE_STATUSES)
    rows = con.execute(
        f"""
        SELECT
            domain,
            COUNT(*) AS total,
            SUM(CASE WHEN status IN ({failure_clause}) THEN 1 ELSE 0 END) AS failures,
            ROUND(100.0 * SUM(CASE WHEN status IN ({failure_clause}) THEN 1 ELSE 0 END)
                  / COUNT(*), 1) AS failure_rate
        FROM telemetry
        WHERE tool_name = 'read_article' AND domain IS NOT NULL
        GROUP BY domain
        HAVING COUNT(*) >= ?
        ORDER BY failure_rate DESC, total DESC
        LIMIT ?
        """,
        (MIN_SAMPLES, top_n),
    ).fetchall()

    results: list[DomainFailure] = []
    for r in rows:
        # Find the top failure code for this domain
        top_failure = con.execute(
            f"""
            SELECT status, COUNT(*) c FROM telemetry
            WHERE tool_name='read_article' AND domain=?
              AND status IN ({failure_clause})
            GROUP BY status ORDER BY c DESC LIMIT 1
            """,
            (r["domain"],),
        ).fetchone()
        top_code = top_failure["status"] if top_failure else "—"
        results.append(
            DomainFailure(
                domain=r["domain"],
                total_calls=r["total"],
                failures=r["failures"],
                failure_rate_pct=r["failure_rate"],
                top_failure_code=top_code,
                alert=r["failure_rate"] >= FAILURE_RATE_ALERT,
            )
        )
    return results


def token_inefficiency(con: sqlite3.Connection, top_n: int = 5) -> list[TokenInefficiency]:
    """Domains with abnormally high tokens-per-article (potential residual noise)."""
    rows = con.execute(
        """
        SELECT
            domain,
            ROUND(AVG(tokens_approx), 0) AS avg_tokens,
            MAX(tokens_approx) AS max_tokens,
            COUNT(*) AS samples
        FROM telemetry
        WHERE tool_name = 'read_article' AND status = 'success' AND domain IS NOT NULL
        GROUP BY domain
        HAVING COUNT(*) >= ?
        ORDER BY avg_tokens DESC
        LIMIT ?
        """,
        (MIN_SAMPLES, top_n),
    ).fetchall()

    return [
        TokenInefficiency(
            domain=r["domain"],
            avg_tokens=r["avg_tokens"],
            max_tokens=r["max_tokens"],
            samples=r["samples"],
            alert=r["avg_tokens"] >= TOKEN_INEFFICIENCY_ALERT,
        )
        for r in rows
    ]


def error_patterns(con: sqlite3.Connection) -> list[ErrorPattern]:
    """Per-(tool, status) error counts for non-success rows."""
    rows = con.execute(
        """
        SELECT tool_name, status, COUNT(*) AS occurrences
        FROM telemetry
        WHERE status != 'success'
        GROUP BY tool_name, status
        ORDER BY occurrences DESC
        """
    ).fetchall()

    # Per-tool denominators for percentage
    tool_totals = dict(
        con.execute(
            "SELECT tool_name, COUNT(*) FROM telemetry "
            "WHERE status != 'success' GROUP BY tool_name"
        ).fetchall()
    )
    return [
        ErrorPattern(
            tool_name=r["tool_name"],
            status=r["status"],
            occurrences=r["occurrences"],
            pct_of_tool_errors=round(
                100.0 * r["occurrences"] / tool_totals[r["tool_name"]], 1
            ),
        )
        for r in rows
    ]


def tool_skew(con: sqlite3.Connection) -> list[str]:
    """Flag tools whose telemetry is dominated by a single non-success status.

    A tool that is ~100% one error code signals a systemic failure (dead
    backend, blocked host) — its rows inflate the DB count without adding
    representative health signal. Returns human-readable warnings.
    """
    warnings: list[str] = []
    tools = con.execute(
        "SELECT tool_name, COUNT(*) AS n FROM telemetry GROUP BY tool_name"
    ).fetchall()
    for t in tools:
        total = t["n"]
        if total < SKEW_MIN_CALLS:
            continue
        top = con.execute(
            "SELECT status, COUNT(*) AS c FROM telemetry WHERE tool_name = ? "
            "GROUP BY status ORDER BY c DESC LIMIT 1",
            (t["tool_name"],),
        ).fetchone()
        share = top["c"] / total
        if top["status"] != "success" and share >= SKEW_DOMINANCE:
            warnings.append(
                f"{t['tool_name']}: {share:.0%} {top['status']} "
                f"({top['c']}/{total}) — systemic failure, not a health signal"
            )
    return warnings


def build_report(db_path: Path) -> Report:
    con = _connect(db_path)
    total = con.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
    report = Report(
        db_path=str(db_path),
        total_rows=total,
        failure_hotspots=failure_hotspots(con),
        token_inefficiency=token_inefficiency(con),
        error_patterns=error_patterns(con),
        skew_warnings=tool_skew(con),
    )
    con.close()
    return report


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def _print_report_text(report: Report) -> None:
    too_few = report.total_rows < MIN_ROWS_FOR_CONFIDENCE
    skewed = bool(report.skew_warnings)
    thin = too_few or skewed  # either makes verdicts non-actionable
    print("=" * 70)
    print("  DeepSearch-MCP — Telemetry Analysis Report")
    print(f"  DB:   {report.db_path}")
    print(f"  Rows: {report.total_rows:,}")
    if thin:
        print("  ⏳ LOW CONFIDENCE — verdicts below are PROVISIONAL:")
        if too_few:
            print(f"     • only {report.total_rows} rows (< {MIN_ROWS_FOR_CONFIDENCE}); "
                  f"a few-sample alert is a coin-flip, and 'no alerts' ≠ healthy.")
        for w in report.skew_warnings:
            print(f"     • skewed data — {w}")
        if skewed:
            print("     (more rows will NOT fix skew — fix the systemic failure first.)")
    print("=" * 70)

    # 1. Failure hotspots
    print("\n📍 1. EXTRACTION FAILURE HOTSPOTS")
    print(f"   (alert ≥ {FAILURE_RATE_ALERT}% failure rate, ≥ {MIN_SAMPLES} samples)\n")
    if not report.failure_hotspots:
        print("   (no domains with enough samples)\n")
    else:
        print(f"   {'Domain':<35} {'Total':>6} {'Fails':>6} {'Rate':>7}  Top Code")
        print(f"   {'-' * 35} {'-' * 6} {'-' * 6} {'-' * 7}  {'-' * 18}")
        for d in report.failure_hotspots:
            tag = "⚠️ " if d.alert else "  "
            print(f"   {tag}{d.domain:<33} {d.total_calls:>6} "
                  f"{d.failures:>6} {d.failure_rate_pct:>6}% {d.top_failure_code}")

    # 2. Token inefficiency
    print("\n🪙 2. TOKEN INEFFICIENCY (potential noise)")
    print(f"   (alert ≥ {TOKEN_INEFFICIENCY_ALERT} avg tokens per article)\n")
    if not report.token_inefficiency:
        print("   (no domains with enough successful samples)\n")
    else:
        print(f"   {'Domain':<35} {'Avg':>6} {'Max':>6} {'Smpl':>5}")
        print(f"   {'-' * 35} {'-' * 6} {'-' * 6} {'-' * 5}")
        for t in report.token_inefficiency:
            tag = "⚠️ " if t.alert else "  "
            print(f"   {tag}{t.domain:<33} {int(t.avg_tokens):>6} "
                  f"{t.max_tokens:>6} {t.samples:>5}")

    # 3. Error patterns
    print("\n🔥 3. ERROR PATTERN ANALYSIS (by tool, status)\n")
    if not report.error_patterns:
        print("   (no errors recorded)\n")
    else:
        print(f"   {'Tool':<20} {'Status':<22} {'Count':>6} {'% of tool errs':>15}")
        print(f"   {'-' * 20} {'-' * 22} {'-' * 6} {'-' * 15}")
        for e in report.error_patterns:
            print(f"   {e.tool_name:<20} {e.status:<22} {e.occurrences:>6}"
                  f" {e.pct_of_tool_errors:>14}%")

    # 4. Suggested actions
    print("\n🛠  SUGGESTED ACTIONS")
    actions = _suggest_actions(report)
    if not actions:
        if thin:
            print(f"   ⏳ No alerts — but only {report.total_rows} rows. "
                  f"This is 'not enough data', NOT 'healthy'.\n")
        else:
            print("   ✅ No alerts. System is healthy.\n")
    else:
        prefix = "PROVISIONAL — confirm with more data: " if thin else ""
        for a in actions:
            print(f"   • {prefix}{a}")
        print()
    print("=" * 70)


def _suggest_actions(report: Report) -> list[str]:
    """Generate human-readable action items from alert flags."""
    actions: list[str] = []
    for d in report.failure_hotspots:
        if d.alert:
            actions.append(
                f"Add a domain adapter for `{d.domain}` "
                f"(top failure: {d.top_failure_code}, "
                f"{d.failure_rate_pct}% rate over {d.total_calls} calls)"
            )
    for t in report.token_inefficiency:
        if t.alert:
            actions.append(
                f"Investigate noise on `{t.domain}` "
                f"(avg {int(t.avg_tokens)} tokens × {t.samples} samples)"
            )
    # Spike heuristic: a single (tool, status) > 30% of that tool's errors
    for e in report.error_patterns:
        if e.pct_of_tool_errors >= 30 and e.status in ("RATE_LIMITED",):
            actions.append(
                f"`{e.tool_name}` is rate-limited heavily "
                f"({e.pct_of_tool_errors}% of errors). "
                f"Consider raising cache TTL or tightening jitter."
            )
        if e.pct_of_tool_errors >= 50 and e.status == "BLOCKED_403":
            actions.append(
                f"403 wall on `{e.tool_name}` ({e.pct_of_tool_errors}%). "
                f"Rotate `impersonate` target in core/http.py."
            )
    return actions


def _print_report_json(report: Report) -> None:
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument("--db", help="Override path to telemetry.db")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.db)
    report = build_report(db_path)
    if args.json:
        _print_report_json(report)
    else:
        _print_report_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
