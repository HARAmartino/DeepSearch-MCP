# Baseline Measurement — DeepSearch-MCP
**Date:** 2026-05-28
**Evaluator:** `evals/eval_judge.py` v0.1 (Phase 0)
**Scorer:** 3-axis rubric (Noise 0-4 + Structure 0-3 + Density 0-3 = 10 pts)

---

## Baseline Scenarios

### Scenario 1: Raw Scrape with Navigation/Footer Mixed In
**Description:** Simulates a naive HTML-to-text scrape where nav, cookie banners, share buttons, and footer are present alongside real article content.

| Axis | Score | Notes |
|---|---|---|
| Noise | 0.0 / 4 | 35% of lines are noise (12 patterns detected) |
| Structure | 0.0 / 3 | No Markdown headers/lists/code blocks |
| Density | 2.0 / 3 | Avg line ~49 chars |
| **Total** | **2.0 / 10** | **FAIL** |

### Scenario 2: Naive Full-Text Scrape (No Structure)
**Description:** Clean text content but no Markdown formatting — simulates `requests` + BeautifulSoup `get_text()` without any structure preservation.

| Axis | Score | Notes |
|---|---|---|
| Noise | 4.0 / 4 | No noise detected |
| Structure | 0.0 / 3 | No headers, lists, or code blocks |
| Density | 3.0 / 3 | Dense prose |
| **Total** | **7.0 / 10** | Below gate |

---

## Gate Condition (Phase 1)

> `eval_judge.py` average score on the Phase 1 test set must be **> 8.5 / 10**.

The baseline shows that:
- Raw scrapes with noise average **2.0/10** → Phase 1 must eliminate this
- Structure-free plain text averages **7.0/10** → Markdown formatting adds the final 1.5+ pts needed to pass

Phase 1 target output must achieve all three axes simultaneously:
- Noise: ≥ 3.5 (< 5% noise line ratio)
- Structure: ≥ 2.5 (headers + at least one of list/code)
- Density: ≥ 2.5 (real prose, > 60 avg chars/line or sufficient length)
