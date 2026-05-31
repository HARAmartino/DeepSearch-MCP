"""
benchmark.py — DeepSearch Quality Score (DQS): one tracked number for "how good
is DeepSearch-MCP right now?".

Like an LLM benchmark, this is a **fixed, offline, deterministic** battery that
produces a single composite 0–100 score with per-capability sub-scores,
reproducible release-over-release. It deliberately **composes the project's
already-validated measures** instead of inventing new metrics:

  Extraction  (40%)  eval_judge gauntlet avg over 10 site categories (B0/B1)
  Cleanliness (20%)  residual-noise auditor on those extractions (semantic probe)
  Robustness  (25%)  structured-error contract compliance (Prime Directive 2)
  Diversity   (15%)  suggest_queries reserved-angle coverage, AC offline (B11)

Run:
    python evals/benchmark.py
    python evals/benchmark.py --json

**HONESTY — read before trusting the number.** DQS is a PROXY measured over
hand-built fixtures, exactly the thing anti-pattern #4 / the "fixtures aren't
real usage" lesson warn about. A high DQS is *necessary, not sufficient*: it
cannot see what only live `scripts/research.py` / `scripts/live_check.py`
dogfooding sees. Use it as a release-over-release **regression north-star** and a
trend, never as proof of field quality. Don't optimize the number at the expense
of real extractions (Goodhart).

The composite weights are an explicit judgment call (mission priority:
extraction is the core, robustness is a Prime Directive). They are documented
here so a change to them is a visible, reviewable decision — not a silent tweak.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evals.dogfood_audit import audit_markdown  # noqa: E402
from evals.eval_judge import score_markdown  # noqa: E402
from src.deepsearch_mcp.core import errors  # noqa: E402
from src.deepsearch_mcp.core.extractor import build_frontmatter, extract  # noqa: E402
from src.deepsearch_mcp.tools.search import _map_ddgs_exception  # noqa: E402
from src.deepsearch_mcp.tools.suggest import suggest_queries  # noqa: E402
from tests.test_extractor import GAUNTLET_FIXTURES  # noqa: E402  (canonical extraction battery)

# Composite weights (sum to 1.0). Explicit by design — see module docstring.
WEIGHTS = {
    "extraction": 0.40,
    "cleanliness": 0.20,
    "robustness": 0.25,
    "diversity": 0.15,
}

# Fixed topic battery for the query-diversity sub-benchmark.
_DIVERSITY_TOPICS = [
    "CRISPR base editing",
    "React Server Components",
    "intermittent fasting",
    "quantum error correction",
    "EU AI Act",
]


def _gauntlet_extractions() -> list[tuple[str, str]]:
    """(name, extracted-markdown) for each gauntlet fixture — the shared input
    to the extraction + cleanliness sub-benchmarks. Fully offline."""
    out = []
    for name, html, url in GAUNTLET_FIXTURES:
        body, meta = extract(html, url=url)
        out.append((name, f"{build_frontmatter(meta)}\n\n{body}"))
    return out


def score_extraction(extractions: list[tuple[str, str]]) -> tuple[float, dict]:
    """eval_judge gauntlet average, normalized to 0–100."""
    totals = [score_markdown(md).total for _, md in extractions]
    avg = sum(totals) / len(totals)
    return round(avg * 10, 1), {"judge_avg_/10": round(avg, 2), "n": len(totals)}


def score_cleanliness(extractions: list[tuple[str, str]]) -> tuple[float, dict]:
    """Share of gauntlet extractions with ZERO residual-noise lines (semantic
    probe — the noise eval_judge's line-ratio axis can miss)."""
    clean = sum(1 for _, md in extractions if not audit_markdown(md))
    noise_lines = sum(len(audit_markdown(md)) for _, md in extractions)
    n = len(extractions)
    return round(100 * clean / n, 1), {"clean_fixtures": clean, "n": n,
                                       "residual_noise_lines": noise_lines}


def score_robustness() -> tuple[float, dict]:
    """Structured-error contract compliance: every error path must return a
    valid {status,code,message,hint,retryable} with an actionable hint and no
    raw traceback (Prime Directive 2). Offline — pure error builders."""
    raws: list[str] = [
        errors.structured_error(code, f"sample message for {code}")
        for code in errors._HINTS
    ]
    try:
        from duckduckgo_search.exceptions import (
            DuckDuckGoSearchException,
            RatelimitException,
            TimeoutException,
        )
        raws += [_map_ddgs_exception(e) for e in (
            RatelimitException("r"), TimeoutException("t"),
            DuckDuckGoSearchException("d"), ConnectionError("DNS failure"),
            ValueError("unexpected"),
        )]
    except ImportError:
        pass

    compliant = 0
    for raw in raws:
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        ok = (
            d.get("status") == "error"
            and bool(d.get("code"))
            and bool(d.get("message"))
            and isinstance(d.get("hint"), str) and len(d["hint"]) >= 15
            and isinstance(d.get("retryable"), bool)
            and "Traceback" not in raw and 'File "' not in raw
        )
        compliant += bool(ok)
    return round(100 * compliant / len(raws), 1), {"compliant": compliant, "n": len(raws)}


def score_diversity() -> tuple[float, dict]:
    """Share of topics where suggest_queries delivers its echo-chamber mission:
    3–8 unique queries including ≥1 criticism AND ≥1 primary-source angle (B11).
    Autocomplete is mocked offline so the score is deterministic."""
    async def _run() -> int:
        good = 0
        with patch("src.deepsearch_mcp.tools.suggest._fetch_autocomplete",
                   new_callable=AsyncMock) as m:
            m.return_value = []  # offline + deterministic → templates only
            for topic in _DIVERSITY_TOPICS:
                qs = json.loads(await suggest_queries(topic=topic))
                low = " ".join(qs).lower()
                ok = (
                    3 <= len(qs) <= 8
                    and len(qs) == len({q.lower() for q in qs})  # no dups
                    and any(k in low for k in ("criticism", "problems", "limitations"))
                    and any(k in low for k in ("site:", "github", "arxiv"))
                )
                good += bool(ok)
        return good

    good = asyncio.run(_run())
    n = len(_DIVERSITY_TOPICS)
    return round(100 * good / n, 1), {"topics_pass": good, "n": n}


def run_benchmark() -> dict:
    extractions = _gauntlet_extractions()
    subs = {
        "extraction": score_extraction(extractions),
        "cleanliness": score_cleanliness(extractions),
        "robustness": score_robustness(),
        "diversity": score_diversity(),
    }
    dqs = sum(WEIGHTS[k] * subs[k][0] for k in WEIGHTS)
    return {
        "dqs": round(dqs, 1),
        "weights": WEIGHTS,
        "subscores": {k: {"score": subs[k][0], **subs[k][1]} for k in subs},
    }


def _print(result: dict) -> None:
    print("=" * 66)
    print(f"  DeepSearch Quality Score (DQS): {result['dqs']}/100")
    print("=" * 66)
    for k, w in WEIGHTS.items():
        s = result["subscores"][k]
        extra = " ".join(f"{kk}={vv}" for kk, vv in s.items() if kk != "score")
        print(f"  {k:<12} {s['score']:>5}/100  (weight {int(w*100)}%)  {extra}")
    print("-" * 66)
    print("  PROXY over fixtures — necessary, not sufficient. Still dogfood live")
    print("  (scripts/research.py, scripts/live_check.py). Don't optimize the number.")
    print("=" * 66)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(description="DeepSearch Quality Score (DQS).")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    args = p.parse_args(argv)
    result = run_benchmark()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
