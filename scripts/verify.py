#!/usr/bin/env python3
"""
verify.py — the single merge gate, in one call.

**Why this exists.** `MAINTENANCE.md` lists three commands that must all pass
before any merge (pytest, ruff, dogfood_regression). Running them as three
separate invocations means an agent can forget one — and during the
2026-05-29 session, one nearly reported "green" before running
dogfood_regression. One command, one exit code, no forgetting.

Environment-robust: it locates the project venv's interpreter and ruff binary
rather than assuming `uv` is on PATH (the agent tool-shell often has neither
`uv` nor `~/.local/bin` on PATH, even when the login shell does).

Exit code is 0 only if ALL gates pass — safe for CI / pre-commit / cron.

Run:
    python scripts/verify.py
    .venv/bin/python scripts/verify.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _venv_bin(name: str) -> str:
    cand = ROOT / ".venv" / "bin" / name
    return str(cand) if cand.exists() else name


GATES: list[tuple[str, list[str]]] = [
    ("pytest", [sys.executable, "-m", "pytest", "tests/", "-q"]),
    ("ruff", [_venv_bin("ruff"), "check", "src/", "tests/", "evals/", "scripts/"]),
    ("dogfood_regression", [sys.executable, "evals/dogfood_regression.py"]),
    ("docs_links", [sys.executable, "scripts/docs_map.py", "--check"]),
]


def run_gate(name: str, cmd: list[str]) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    try:
        cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        ok = cp.returncode == 0
        tail = (cp.stdout + cp.stderr).strip().splitlines()
        summary = tail[-1] if tail else ""
        return ok, time.perf_counter() - t0, summary
    except Exception as exc:  # noqa: BLE001 — gate must never crash the runner
        return False, time.perf_counter() - t0, f"runner error: {exc}"


def main() -> int:
    print("=" * 68)
    print("  DeepSearch-MCP — VERIFY (single merge gate)")
    print("=" * 68)
    results: list[tuple[str, bool]] = []
    for name, cmd in GATES:
        ok, secs, summary = run_gate(name, cmd)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:<20} {secs:5.1f}s   {summary[:60]}")
        results.append((name, ok))

    print("-" * 68)
    failed = [n for n, ok in results if not ok]
    if failed:
        print(f"  ❌ FAIL — {len(failed)} gate(s): {', '.join(failed)}")
        print("     Fix before merge (METHODOLOGY.md §1, Trigger 1/2).")
        return 1
    print("  ✅ ALL GATES PASS — safe to merge.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
