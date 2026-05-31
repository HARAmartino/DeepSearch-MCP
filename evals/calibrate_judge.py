"""
calibrate_judge.py — does the cheap eval_judge heuristic track real usability?

**Why this exists (B1).** `eval_judge.score_markdown` reduces an extraction to a
0–10 score on three mechanical axes (noise / structure / density), and the
Gauntlet **gate** trusts an average ≥ 8.5 to mean "good". B1 asked: does that
number actually correlate with *quality*, or only with "good on these 3 axes"?

The original backlog framing was "calibrate against **human** ratings (blocker:
human availability)". That target is wrong for this project: the consumer of
`read_article` output is the **LLM agent**, not a human. So the right ground
truth is the *agent-as-consumer's* holistic judgment — "how usable is this as
clean context?" — which removes the human-availability blocker entirely.

This module pins a small **labeled set** spanning the quality range (real golden
fixtures as high anchors + crafted real-world failure modes: nav-noise,
footer-tail, clean-but-short, flat-no-headings, code-heavy, thin fragment) and
measures the **Pearson correlation** between the heuristic total and the
consumer rating. The ratings were assigned on the rubric below *before* reading
heuristic scores, so a large per-sample delta is a genuine miscalibration signal
— not a number massaged to look good.

Consumer rubric (0–10), "as an agent, how usable is this as context?":
  9–10  clean prose, well-structured, zero noise, substantial — ideal
  7–8   clean and usable; may be flat/short, but no noise distraction
  5–6   usable signal but diluted by noise lines or a paywall/ad CTA
  3–4   signal buried in chrome; agent wastes most of its read
  0–2   mostly noise / empty / extraction failed — unusable

This is an **analysis + regression** tool, not a CI quality gate: the gate stays
`eval_judge`. Here we verify the gate's proxy is trustworthy and surface the
axes where it diverges from the consumer.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evals.eval_judge import score_markdown  # noqa: E402

_BASELINE_DIR = os.path.join(ROOT, "evals", "dogfood_baseline")


@dataclass(frozen=True)
class Sample:
    id: str
    text: str
    rating: float       # consumer holistic rating, 0–10 (ground truth)
    rationale: str


# --- crafted samples spanning the range (real extraction failure modes) -----

_NAV_NOISE = """\
Skip to main content
Home About Contact Search Menu
Cookie Settings. Accept All Cookies. Privacy Policy. Terms of Use.
Subscribe to our newsletter for updates.
Follow us on Twitter Facebook LinkedIn.
The quarterly report showed modest revenue growth in the third quarter.
Related posts. You might also like.
All rights reserved © 2026
Back to top
"""

_FOOTER_TAIL = """\
---
title: "Coastal Wetland Restoration Hits a Milestone"
---

The restoration project along the eastern estuary has reached its halfway mark,
with native marsh grasses now covering more than four hundred hectares that were
open mudflat just three years ago. Ecologists report measurable rebounds in fish
and wading-bird populations across the replanted zones.

Funding for the next phase was approved this month, extending the effort north
toward the river delta where salinity gradients make replanting harder. The team
expects the full corridor to close within five years if winter storms cooperate.

Subscribe to our newsletter for weekly updates.
Related posts. You might also like.
Share on Twitter Facebook LinkedIn.
All rights reserved © 2026
"""

_CLEAN_SHORT = """\
The Eiffel Tower was completed in 1889 for the World's Fair in Paris. It stands
330 metres tall and was the tallest man-made structure in the world until the
Chrysler Building was finished in 1930.
"""

_CLEAN_FLAT = """\
Photosynthesis is the process by which green plants, algae, and some bacteria
convert light energy into chemical energy stored in glucose. It is the primary
route through which energy enters most ecosystems on Earth.

The light-dependent reactions take place in the thylakoid membranes, where
chlorophyll absorbs photons and drives the splitting of water molecules. This
releases oxygen as a by-product and produces the energy carriers ATP and NADPH.

In the subsequent light-independent reactions, often called the Calvin cycle,
that chemical energy is used to fix carbon dioxide into three-carbon sugars.
These are assembled into glucose and other carbohydrates the organism needs.

Because it both removes carbon dioxide and releases oxygen, photosynthesis is
central to regulating the composition of the planet's atmosphere over time.
"""

_CODE_HEAVY = """\
---
title: "Quickstart: the foo client"
---

## Install

Install the package from PyPI:

```bash
pip install foo-client
```

## Usage

Create a client and issue a request:

```python
from foo import Client

client = Client(api_key="...")
result = client.query("hello")
print(result.text)
```

That is all that is required to make your first call.
"""

_MODERATE_MIXED = """\
The city council voted on Tuesday to expand the downtown bike-lane network by
twelve kilometres over the next two years, citing a sharp rise in commuter
cycling since the pilot corridor opened last spring.

Sign up to continue reading.
Advertisement

Opponents argued the plan removes too much on-street parking, while supporters
pointed to traffic-calming data from comparable mid-sized cities. A final budget
vote is scheduled for next month.
"""

_THIN_FRAGMENT = """\
# Page Title

Loading…
"""


_CRAFTED: list[Sample] = [
    Sample("nav_noise", _NAV_NOISE, 2.0,
           "Almost entirely chrome; the one real sentence is buried — agent "
           "wastes its whole read."),
    Sample("footer_tail", _FOOTER_TAIL, 6.0,
           "Body is clean and usable, but a noisy subscribe/related/share/© "
           "footer dilutes ~25% of the lines."),
    Sample("clean_short", _CLEAN_SHORT, 7.0,
           "For a factual query this is exactly what an agent wants: accurate, "
           "zero noise. Short, but completeness != length."),
    Sample("clean_flat", _CLEAN_FLAT, 8.0,
           "Highly usable multi-paragraph prose; absence of headings is "
           "cosmetic — an agent reads it fine."),
    Sample("code_heavy", _CODE_HEAVY, 8.5,
           "Excellent for a dev agent: clear sections, runnable code blocks, "
           "no noise."),
    Sample("moderate_mixed", _MODERATE_MIXED, 5.5,
           "Real signal but interrupted by a paywall CTA and an ad line; agent "
           "gets partial value."),
    Sample("thin_fragment", _THIN_FRAGMENT, 1.0,
           "No usable content — extraction essentially failed."),
]

# Real golden fixtures = high-quality anchors (clean, sectioned, substantial).
_FIXTURE_RATINGS = {
    "techcrunch": (9.0, "Clean, five sections, substantial prose, zero noise."),
    "langchain_blog": (9.0, "Clean, sectioned, includes a real checklist; zero noise."),
    "devto": (9.0, "Clean benchmark write-up, well sectioned; zero noise."),
    "zdnet": (8.5, "Clean and sectioned; slightly shorter body."),
}


def load_samples() -> list[Sample]:
    """Crafted spread + real golden fixtures (if present on disk)."""
    samples = list(_CRAFTED)
    for name, (rating, why) in _FIXTURE_RATINGS.items():
        path = os.path.join(_BASELINE_DIR, f"{name}.expected.md")
        try:
            with open(path, encoding="utf-8") as f:
                samples.append(Sample(f"fixture:{name}", f.read(), rating, why))
        except OSError:
            continue  # fixture missing → skip (don't fabricate)
    return samples


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson r via stdlib; 0.0 if either series is constant (undefined r)."""
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return 0.0
    return statistics.correlation(xs, ys)


def calibrate(samples: list[Sample] | None = None) -> dict:
    """Score every sample, compare to the consumer rating, summarize."""
    samples = samples if samples is not None else load_samples()
    rows = []
    for s in samples:
        total = score_markdown(s.text).total
        rows.append({
            "id": s.id,
            "heuristic": total,
            "rating": s.rating,
            "delta": round(total - s.rating, 2),
            "rationale": s.rationale,
        })
    heur = [r["heuristic"] for r in rows]
    rate = [r["rating"] for r in rows]
    r = pearson(heur, rate)
    mae = sum(abs(r_["delta"]) for r_ in rows) / len(rows)
    worst = max(rows, key=lambda r_: abs(r_["delta"]))
    return {
        "n": len(rows),
        "pearson_r": round(r, 3),
        "mae": round(mae, 2),
        "worst_divergence": worst,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = calibrate()
    if "--json" in argv:
        print(json.dumps(result, indent=2))
        return 0

    print("=" * 70)
    print("  eval_judge calibration — heuristic vs. consumer (LLM) rating")
    print("=" * 70)
    print(f"  {'sample':<20} {'heuristic':>9} {'rating':>7} {'delta':>7}")
    print("  " + "-" * 46)
    for row in sorted(result["rows"], key=lambda r: r["rating"]):
        print(f"  {row['id']:<20} {row['heuristic']:>9.2f} "
              f"{row['rating']:>7.1f} {row['delta']:>+7.2f}")
    print("  " + "-" * 46)
    print(f"  n = {result['n']}   Pearson r = {result['pearson_r']}   "
          f"MAE = {result['mae']}")
    w = result["worst_divergence"]
    print(f"\n  largest divergence: {w['id']} "
          f"(heuristic {w['heuristic']:.2f} vs rating {w['rating']:.1f}, "
          f"Δ {w['delta']:+.2f})")
    print(f"    → {w['rationale']}")
    r = result["pearson_r"]
    verdict = ("STRONG — heuristic tracks consumer judgment; the 8.5 gate is "
               "a trustworthy proxy" if r >= 0.8 else
               "MODERATE — heuristic mostly tracks; watch the divergent axis"
               if r >= 0.6 else
               "WEAK — heuristic does not track consumer judgment; revisit axes")
    print(f"\n  verdict: r={r} → {verdict}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
