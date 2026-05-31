#!/usr/bin/env python3
"""
status.py — one-call orientation for the maintaining agent.

**Why this exists.** This project is a tool *for LLMs*, maintained *by LLMs*.
An agent's single biggest tax is re-grounding its mental model after a context
compaction: "how many tests are there now? are the gates green? what's the
next thing to do?" Answering that used to cost ~5 tool calls across 3 files.

This prints the live ground truth in one call. It is deliberately
**computed, never stored** — a committed STATUS.md would itself drift and
become the very stale-artifact problem it was meant to solve. Run it; don't
cache it.

Cheap and read-mostly (it does NOT run the full test suite — that's
`scripts/verify.py`). Every section degrades gracefully; this script never
crashes the way a real gate would.

Run:
    python scripts/status.py
    .venv/bin/python scripts/status.py
"""

from __future__ import annotations

import re
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _venv_bin(name: str) -> str:
    """Prefer the project venv's binary; fall back to bare name on PATH."""
    cand = ROOT / ".venv" / "bin" / name
    return str(cand) if cand.exists() else name


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )


def test_count() -> str:
    """Collect-only test count (fast; does not execute tests)."""
    try:
        cp = _run([sys.executable, "-m", "pytest", "tests/", "--co", "-q"])
        m = re.search(r"(\d+)\s+tests?\s+collected", cp.stdout + cp.stderr)
        if m:
            return f"{m.group(1)} collected"
        # Newer pytest prints "N/M tests collected" or just lines; fall back.
        m = re.search(r"(\d+)\s+tests?", cp.stdout + cp.stderr)
        return f"{m.group(1)} (approx)" if m else "unknown"
    except Exception as exc:
        return f"error: {exc}"


def ruff_clean() -> str:
    try:
        cp = _run([_venv_bin("ruff"), "check", "src/", "tests/", "evals/", "scripts/"])
        return "clean ✅" if cp.returncode == 0 else f"{cp.returncode} issue(s) ⚠️"
    except Exception as exc:
        return f"error: {exc}"


def dogfood_baselines() -> str:
    d = ROOT / "evals" / "dogfood_baseline"
    try:
        n = len(list(d.glob("*.expected.md")))
        return f"{n} fixture(s)"
    except Exception as exc:
        return f"error: {exc}"


def last_audit() -> str:
    f = ROOT / "docs" / "LESSONS.md"
    try:
        m = re.search(r"\*\*Last audit:\*\*\s*([0-9-]+)", f.read_text(encoding="utf-8"))
        return m.group(1) if m else "not recorded"
    except Exception as exc:
        return f"error: {exc}"


def lesson_tags() -> str:
    f = ROOT / "docs" / "LESSONS.md"
    try:
        body = f.read_text(encoding="utf-8")
        # Count tags on entry headers only (### lines), not the legend.
        active = len(re.findall(r"^###.*\[ACTIVE\]", body, re.MULTILINE))
        hist = len(re.findall(r"^###.*\[HISTORICAL\]", body, re.MULTILINE))
        stale = len(re.findall(r"^###.*\[STALE\]", body, re.MULTILINE))
        return f"{active} active / {hist} historical / {stale} stale"
    except Exception as exc:
        return f"error: {exc}"


def next_backlog(text: str | None = None) -> list[str]:
    """Open backlog rows in METHODOLOGY.md §5 — excludes resolved ones.

    A row is resolved (and skipped) if it is struck (`~~`), marked `DONE`, or
    marked `Declined` (a recorded won't-do decision is not actionable work — the
    B27 fix; previously a declined row surfaced as the "next" item)."""
    if text is None:
        try:
            text = (ROOT / "docs" / "METHODOLOGY.md").read_text(encoding="utf-8")
        except OSError:
            return []
    out: list[str] = []
    for line in text.splitlines():
        # rows look like: | **B3** | ... |   — struck rows won't match the regex.
        m = re.match(r"\|\s*\*\*(B\d+)\*\*\s*\|\s*([^|]+)\|", line)
        if not m:
            continue
        if "~~" in line or "DONE" in line or "Declined" in line:
            continue
        bid, desc = m.group(1), m.group(2).strip()
        short = (desc[:60] + "…") if len(desc) > 60 else desc
        out.append(f"{bid}: {short}")
    return out[:3]


def _backlog_text() -> str:
    try:
        return (ROOT / "docs" / "METHODOLOGY.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def parse_backlog_dates(text: str) -> list[dict]:
    """Parse §5 rows into reactive records carrying a `disc:` date.

    The backlog is the project's alert→patch ledger (B2). A *reactive* row has
    `disc:YYYY-MM-DD` (when first flagged); a closed row also has
    `DONE YYYY-MM-DD` (when the patch landed). Rows without `disc:` are
    proactive/process items and are intentionally skipped.
    """
    records: list[dict] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        m = re.search(r"\*\*(B\d+)\*\*", line)
        if not m:
            continue
        disc = re.search(r"disc:(\d{4}-\d{2}-\d{2})", line)
        if not disc:  # proactive / process item — not an alert
            continue
        done = re.search(r"DONE\s+(\d{4}-\d{2}-\d{2})", line)
        records.append({
            "id": m.group(1),
            "disc": disc.group(1),
            "done": done.group(1) if done else None,
        })
    return records


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def mtti(text: str | None = None, today: str | None = None) -> dict:
    """MTTI from the backlog: closed lead-time stats + oldest open flag age."""
    recs = parse_backlog_dates(text if text is not None else _backlog_text())
    today = today or date.today().isoformat()
    closed = [_days(r["disc"], r["done"]) for r in recs if r["done"]]
    open_rows = [r for r in recs if not r["done"]]
    open_ages = [(_days(r["disc"], today), r["id"]) for r in open_rows]
    oldest = max(open_ages) if open_ages else None
    return {
        "closed_n": len(closed),
        "mtti_mean": round(statistics.mean(closed), 1) if closed else None,
        "mtti_median": round(statistics.median(closed), 1) if closed else None,
        "open_n": len(open_rows),
        "oldest_open": oldest,  # (age_days, id) or None
    }


def mtti_line() -> str:
    """One-line MTTI summary for the status board (never raises)."""
    try:
        m = mtti()
        if not m["closed_n"] and not m["open_n"]:
            return "no dated backlog rows"
        closed = (f"{m['mtti_median']}d median / {m['mtti_mean']}d mean "
                  f"over {m['closed_n']} closed" if m["closed_n"]
                  else "no closed reactive rows")
        if m["oldest_open"]:
            age, bid = m["oldest_open"]
            openpart = f"; {m['open_n']} open, oldest {age}d ({bid})"
        else:
            openpart = f"; {m['open_n']} open"
        return closed + openpart
    except Exception as exc:
        return f"error: {exc}"


def main() -> int:
    print("=" * 68)
    print("  DeepSearch-MCP — STATUS (live; computed, not stored)")
    print("=" * 68)
    print(f"  Tests          : {test_count()}")
    print(f"  Lint (ruff)    : {ruff_clean()}")
    print(f"  Dogfood golden : {dogfood_baselines()}")
    print(f"  Lessons        : {lesson_tags()}")
    print(f"  Last audit     : {last_audit()}")
    print(f"  MTTI (backlog) : {mtti_line()}")
    backlog = next_backlog()
    print("  Next backlog   :", backlog[0] if backlog
          else "(no open items — backlog clear; see METHODOLOGY.md §5)")
    for item in backlog[1:]:
        print(f"                   {item}")
    print("-" * 68)
    print("  Full gate : python scripts/verify.py")
    print("  Methodology: docs/METHODOLOGY.md §1 (Trigger Hierarchy)")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
