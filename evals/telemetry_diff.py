"""
telemetry_diff.py — compare two telemetry.db snapshots (B4).

Day-2 operations measures a single snapshot (`analyze_telemetry.py`). But the
question that actually drives releases is *did this release make things better
or worse?* — which only a **before/after diff** answers. This reads two
`telemetry.db` files (e.g. one captured before a release, one after) and reports
the deltas that matter: success rate, tokens-per-call, latency, and the error-
code mix, per tool and overall.

    python evals/telemetry_diff.py --before old/telemetry.db --after new/telemetry.db
    python evals/telemetry_diff.py --before a.db --after b.db --json

It is purely descriptive + flags a few obvious regressions (success rate drop,
brand-new error codes). The extraction-length drift *alert* (Operations Rule 6)
is layered on top in B6 via `extraction_length_drift()`.

Note (cold-start guard, mirrors analyze_telemetry): a diff over thin data is
noise. If either snapshot is below the confidence floor, deltas are shown but
labelled PROVISIONAL — don't act on a 5-row swing.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# A success-rate drop of at least this many points is called out as a regression.
SUCCESS_DROP_ALERT_PTS = 5.0
# Below this many rows in either snapshot, the diff is labelled PROVISIONAL.
MIN_ROWS_FOR_CONFIDENCE = 50


def _connect(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.exists():
        print(f"ERROR: telemetry DB not found at {p}", file=sys.stderr)
        sys.exit(1)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    return con


def snapshot_metrics(con: sqlite3.Connection) -> dict:
    """Aggregate one telemetry snapshot into release-comparable metrics."""
    total = con.execute("SELECT COUNT(*) c FROM telemetry").fetchone()["c"]
    succ = con.execute(
        "SELECT COUNT(*) c FROM telemetry WHERE status='success'"
    ).fetchone()["c"]

    tools: dict[str, dict] = {}
    for r in con.execute(
        """
        SELECT tool_name,
               COUNT(*) AS calls,
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS successes,
               AVG(latency_ms) AS avg_latency,
               AVG(CASE WHEN status='success' THEN tokens_approx END) AS avg_tokens_success
        FROM telemetry GROUP BY tool_name
        """
    ).fetchall():
        calls = r["calls"]
        tools[r["tool_name"]] = {
            "calls": calls,
            "successes": r["successes"],
            "success_rate": round(100.0 * r["successes"] / calls, 1) if calls else 0.0,
            "avg_latency_ms": round(r["avg_latency"], 0) if r["avg_latency"] is not None else None,
            "avg_tokens_success": round(r["avg_tokens_success"], 0)
            if r["avg_tokens_success"] is not None else None,
        }

    error_codes: dict[str, int] = {
        r["status"]: r["c"]
        for r in con.execute(
            "SELECT status, COUNT(*) c FROM telemetry "
            "WHERE status != 'success' GROUP BY status"
        ).fetchall()
    }

    return {
        "total_rows": total,
        "overall_success_rate": round(100.0 * succ / total, 1) if total else 0.0,
        "tools": tools,
        "error_codes": error_codes,
    }


def _pct_change(before: float | None, after: float | None) -> float | None:
    """Percent change after vs before; None if undefined (no before baseline)."""
    if before is None or after is None or before == 0:
        return None
    return round(100.0 * (after - before) / before, 1)


def diff_snapshots(before: dict, after: dict) -> dict:
    """Pure diff of two `snapshot_metrics` dicts → deltas + regression notes."""
    notes: list[str] = []
    provisional = (
        before["total_rows"] < MIN_ROWS_FOR_CONFIDENCE
        or after["total_rows"] < MIN_ROWS_FOR_CONFIDENCE
    )

    # Overall success rate
    osr_b, osr_a = before["overall_success_rate"], after["overall_success_rate"]
    if osr_b - osr_a >= SUCCESS_DROP_ALERT_PTS:
        notes.append(
            f"⚠ overall success rate dropped {osr_b - osr_a:.1f} pts "
            f"({osr_b}% → {osr_a}%)"
        )

    # Per-tool deltas
    tools: dict[str, dict] = {}
    for name in sorted(set(before["tools"]) | set(after["tools"])):
        tb = before["tools"].get(name, {})
        ta = after["tools"].get(name, {})
        srb, sra = tb.get("success_rate"), ta.get("success_rate")
        tools[name] = {
            "calls": {"before": tb.get("calls", 0), "after": ta.get("calls", 0)},
            "success_rate": {"before": srb, "after": sra},
            "avg_tokens_success": {
                "before": tb.get("avg_tokens_success"),
                "after": ta.get("avg_tokens_success"),
                "pct_change": _pct_change(tb.get("avg_tokens_success"),
                                          ta.get("avg_tokens_success")),
            },
            "avg_latency_ms": {
                "before": tb.get("avg_latency_ms"),
                "after": ta.get("avg_latency_ms"),
                "pct_change": _pct_change(tb.get("avg_latency_ms"),
                                          ta.get("avg_latency_ms")),
            },
        }
        if srb is not None and sra is not None and srb - sra >= SUCCESS_DROP_ALERT_PTS:
            notes.append(f"⚠ {name}: success rate {srb}% → {sra}%")

    # Error-code churn
    eb, ea = before["error_codes"], after["error_codes"]
    new_codes = sorted(set(ea) - set(eb))
    gone_codes = sorted(set(eb) - set(ea))
    for c in new_codes:
        notes.append(f"⚠ new error code appeared: {c} ({ea[c]}×)")

    return {
        "provisional": provisional,
        "rows": {"before": before["total_rows"], "after": after["total_rows"]},
        "overall_success_rate": {"before": osr_b, "after": osr_a,
                                 "delta_pts": round(osr_a - osr_b, 1)},
        "tools": tools,
        "error_codes": {"new": new_codes, "gone": gone_codes,
                        "before": eb, "after": ea},
        "notes": notes,
    }


def build_diff(before_db: str, after_db: str) -> dict:
    with _connect(before_db) as cb, _connect(after_db) as ca:
        return diff_snapshots(snapshot_metrics(cb), snapshot_metrics(ca))


def _print_diff(d: dict) -> None:
    print("=" * 70)
    print("  TELEMETRY DIFF — before → after")
    print("=" * 70)
    if d["provisional"]:
        print("  ⚠ PROVISIONAL — one snapshot is below the confidence floor "
              f"({MIN_ROWS_FOR_CONFIDENCE} rows). Treat deltas as directional.")
    r = d["rows"]
    osr = d["overall_success_rate"]
    print(f"  rows: {r['before']} → {r['after']}")
    print(f"  overall success: {osr['before']}% → {osr['after']}% "
          f"({osr['delta_pts']:+.1f} pts)")
    print("  " + "-" * 60)
    for name, t in d["tools"].items():
        sr = t["success_rate"]
        tok = t["avg_tokens_success"]
        tokpc = f"{tok['pct_change']:+.1f}%" if tok["pct_change"] is not None else "—"
        print(f"  {name:<16} calls {t['calls']['before']}→{t['calls']['after']} | "
              f"success {sr['before']}%→{sr['after']}% | "
              f"tokens {tok['before']}→{tok['after']} ({tokpc})")
    if d["error_codes"]["new"] or d["error_codes"]["gone"]:
        print("  " + "-" * 60)
        print(f"  error codes: +{d['error_codes']['new']}  -{d['error_codes']['gone']}")
    print("  " + "-" * 60)
    if d["notes"]:
        print("  FINDINGS:")
        for n in d["notes"]:
            print(f"    {n}")
    else:
        print("  ✅ No regressions detected in the diff.")
    print("=" * 70)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diff two telemetry.db snapshots.")
    p.add_argument("--before", required=True, help="Path to the earlier telemetry.db")
    p.add_argument("--after", required=True, help="Path to the later telemetry.db")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = p.parse_args(argv)
    d = build_diff(args.before, args.after)
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        _print_diff(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
