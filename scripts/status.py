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
import subprocess
import sys
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


def next_backlog() -> list[str]:
    """Best-effort: open backlog rows in METHODOLOGY.md §5 (not DONE/struck)."""
    f = ROOT / "docs" / "METHODOLOGY.md"
    out: list[str] = []
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            # rows look like: | **B3** | ... |   — skip struck (~~) or DONE
            m = re.match(r"\|\s*\*\*(B\d+)\*\*\s*\|\s*([^|]+)\|", line)
            if not m:
                continue
            bid, desc = m.group(1), m.group(2).strip()
            if "DONE" in desc or "~~" in line:
                continue
            short = (desc[:60] + "…") if len(desc) > 60 else desc
            out.append(f"{bid}: {short}")
    except Exception:
        pass
    return out[:3]


def main() -> int:
    print("=" * 68)
    print("  DeepSearch-MCP — STATUS (live; computed, not stored)")
    print("=" * 68)
    print(f"  Tests          : {test_count()}")
    print(f"  Lint (ruff)    : {ruff_clean()}")
    print(f"  Dogfood golden : {dogfood_baselines()}")
    print(f"  Lessons        : {lesson_tags()}")
    print(f"  Last audit     : {last_audit()}")
    backlog = next_backlog()
    print("  Next backlog   :", backlog[0] if backlog else "(none parsed — see METHODOLOGY.md §5)")
    for item in backlog[1:]:
        print(f"                   {item}")
    print("-" * 68)
    print("  Full gate : python scripts/verify.py")
    print("  Methodology: docs/METHODOLOGY.md §1 (Trigger Hierarchy)")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
