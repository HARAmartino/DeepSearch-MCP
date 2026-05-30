"""
Dogfooding regression harness — converts ad-hoc inspection into automated verification.

**Why this exists.**
The first dogfooding session (2026-05-29) found 4 noise leaks by manual
inspection of extraction output. That inspection was anecdotal: a future
contributor changing `utils/cleaner.py` would have no way to know that
their patch silently re-introduced one of those leaks. This harness fixes
that by treating every previously-validated extraction as a *golden
baseline* and failing CI whenever the live output drifts from it.

**How it works.**
For each fixture in `evals/dogfood_research.py`:

  1. Run the fixture HTML through the real `extract()` pipeline.
  2. Compare the result to `evals/dogfood_baseline/<name>.expected.md`.
  3. If they differ, print a unified diff and exit non-zero.

When you intentionally change extraction behavior, run with `--update` to
refresh the goldens. Review the diff manually before committing the new
baseline.

**Why not pytest snapshot plugins?**
Three reasons: zero new dependencies, the goldens are plain `.md` files
that humans can read and review in PRs, and the runner doubles as a CLI
SREs can invoke manually outside CI.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

# Disable telemetry — this is a pure extraction check, no live network
os.environ["DEEPSEARCH_TELEMETRY"] = "0"
sys.path.insert(0, ".")

from src.deepsearch_mcp.core.extractor import build_frontmatter, extract  # noqa: E402

# Reuse the same fixtures the agent uses in real dogfooding
sys.path.insert(0, "evals")
from dogfood_research import (  # noqa: E402
    DEVTO_HTML,
    LANGCHAIN_HTML,
    TECHCRUNCH_HTML,
    ZDNET_HTML,
)

BASELINE_DIR = Path(__file__).parent / "dogfood_baseline"


# (name, html, url) — name doubles as the golden filename
FIXTURES: list[tuple[str, str, str]] = [
    ("techcrunch", TECHCRUNCH_HTML, "https://techcrunch.com/2026/04/12/ai-agent-framework-wars/"),
    ("langchain_blog", LANGCHAIN_HTML, "https://blog.langchain.dev/why-langgraph-wins-2026/"),
    ("devto", DEVTO_HTML, "https://dev.to/sample/autogen-vs-langgraph-benchmarks"),
    ("zdnet", ZDNET_HTML, "https://www.zdnet.com/article/langgraph-crewai-autogen-30-day-test/"),
]


def render_extraction(html: str, url: str) -> str:
    """Run the full extraction pipeline; return the same string an agent would see."""
    body, meta = extract(html, url=url)
    fm = build_frontmatter(meta)
    return f"{fm}\n\n{body}\n"


def golden_path(name: str) -> Path:
    return BASELINE_DIR / f"{name}.expected.md"


def _diff(name: str, expected: str, actual: str) -> str:
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile=f"baseline/{name}.expected.md",
        tofile=f"current/{name}.actual.md",
        n=2,
    )
    return "".join(diff)


def update_all() -> int:
    """Rewrite every golden file from current extraction. Returns 0."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    for name, html, url in FIXTURES:
        actual = render_extraction(html, url)
        golden_path(name).write_text(actual, encoding="utf-8")
        print(f"  ✓ Updated baseline: {name} ({len(actual)} chars)")
    print(f"\n  Wrote {len(FIXTURES)} baselines to {BASELINE_DIR.resolve().relative_to(Path.cwd())}/")
    return 0


def check_all(verbose: bool = True) -> int:
    """Compare each fixture to its golden; return 1 if any drifted."""
    if not BASELINE_DIR.exists():
        print(f"❌ No baseline directory at {BASELINE_DIR}.", file=sys.stderr)
        print("   Run with --update to create initial baselines.", file=sys.stderr)
        return 2

    drifted: list[str] = []
    missing: list[str] = []
    for name, html, url in FIXTURES:
        g = golden_path(name)
        if not g.exists():
            missing.append(name)
            continue

        expected = g.read_text(encoding="utf-8")
        actual = render_extraction(html, url)
        if expected == actual:
            if verbose:
                print(f"  ✅ {name}  ({len(actual)} chars)")
        else:
            drifted.append(name)
            if verbose:
                print(f"  ❌ {name}  DRIFT DETECTED")
                print(_diff(name, expected, actual))

    print()
    if missing:
        print(f"⚠  {len(missing)} fixture(s) missing baselines: {missing}")
        print("   Run with --update to create them.")
    if drifted:
        print(f"❌ {len(drifted)} of {len(FIXTURES)} fixtures drifted from baseline.")
        print("   Either the change is a bug (fix the code) or intentional")
        print("   (re-run with --update and commit the new baseline).")
        return 1
    if not missing:
        print(f"✅ All {len(FIXTURES)} fixtures match their baselines.")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument(
        "--update", action="store_true",
        help="Rewrite golden baselines from current extraction (do this only "
             "after reviewing the diff and confirming the change is intentional).",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress per-fixture status lines (only summary + diffs).",
    )
    args = parser.parse_args(argv)

    if args.update:
        return update_all()
    return check_all(verbose=not args.quiet)


if __name__ == "__main__":
    sys.exit(main())
