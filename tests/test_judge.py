"""
Tests for evals/eval_judge.py

Gate condition (ROADMAP Phase 0):
  - Noisy HTML-derived text  → score < 3.0
  - Clean Markdown article   → score > 8.0
  - Mixed content            → 4.0 ≤ score < 8.0
  - Empty input              → score == 0.0
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.eval_judge import JudgeScore, score_markdown

# ---------------------------------------------------------------------------
# Fixtures — dummy content samples
# ---------------------------------------------------------------------------

PURE_NAV_HTML_DERIVED = """\
Home About Contact Search Menu Navigation
Skip to main content
Cookie Settings Accept All Cookies Privacy Policy Terms of Use
Follow us on Twitter Facebook LinkedIn
All rights reserved © 2024
Back to top
Subscribe to our newsletter
Related posts
You might also like
"""

CLEAN_MARKDOWN_ARTICLE = """\
---
title: "How Neural Networks Learn"
author: Jane Doe
published_date: "2024-03-15"
url: https://example.com/article
---

# How Neural Networks Learn

Neural networks are computational models inspired by the human brain.
They consist of layers of interconnected nodes that transform input data
into useful predictions through a process called forward propagation.

## Backpropagation: The Learning Algorithm

The key to learning is backpropagation — an algorithm that computes
gradients of the loss function with respect to each weight by applying
the chain rule of calculus. This allows the network to adjust weights
in the direction that minimizes prediction error.

### Gradient Descent Variants

- **SGD (Stochastic Gradient Descent):** Updates after each sample.
- **Mini-batch GD:** Updates after small batches — best of both worlds.
- **Adam:** Adaptive learning rates per parameter; widely used in practice.

## Code Example

```python
import torch
import torch.nn as nn

model = nn.Sequential(
    nn.Linear(784, 256),
    nn.ReLU(),
    nn.Linear(256, 10),
)
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
```

## Conclusion

Understanding backpropagation is essential for anyone working with deep
learning. The combination of gradient descent and automatic differentiation
has made training large-scale neural networks practical.
"""

MIXED_CONTENT = """\
---
title: "Python Tricks for 2024"
url: https://blog.example.com/python
---

# Python Tricks for 2024

Python continues to evolve rapidly, and keeping up with its latest features
can make a significant difference in day-to-day productivity. This article
covers several practical tips that experienced developers can apply immediately.

## F-strings are faster than .format()

Use f-strings instead of `.format()` for better performance and readability.
The Python interpreter optimizes f-strings at compile time, making them
significantly faster for string interpolation in hot code paths.

```python
name = "world"
greeting = f"Hello, {name}!"
# Roughly 40% faster than "Hello, {}!".format(name)
```

## Walrus Operator for Cleaner Loops

The walrus operator (`:=`) introduced in Python 3.8 allows assignment
inside expressions, which is useful for avoiding repeated function calls:

```python
while chunk := file.read(8192):
    process(chunk)
```

## Structural Pattern Matching

Python 3.10 introduced `match`/`case` statements that enable clean
dispatching on data shapes without deeply nested if-elif chains.
This is particularly useful for parsing command-line arguments or
handling API responses with varying structures.

Share on Twitter  Share on Facebook  Follow us on LinkedIn
Related posts: Top 10 Python Libraries, How to Learn Python Fast
Subscribe to our newsletter to get more tips!
Cookie Settings  All rights reserved © 2024
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_string_scores_zero(self):
        result = score_markdown("")
        assert result.total == 0.0

    def test_whitespace_only_scores_zero(self):
        result = score_markdown("   \n\n  ")
        assert result.total == 0.0


class TestNoisyContent:
    def test_pure_nav_scores_below_threshold(self):
        result = score_markdown(PURE_NAV_HTML_DERIVED)
        assert result.total < 3.0, (
            f"Expected score < 3.0 for pure nav content, got {result.total}\n{result.details}"
        )

    def test_noisy_content_has_noise_hits(self):
        result = score_markdown(PURE_NAV_HTML_DERIVED)
        assert len(result.noise_hits) >= 3, (
            f"Expected ≥3 noise patterns detected, got {result.noise_hits}"
        )

    def test_noisy_content_low_noise_score(self):
        result = score_markdown(PURE_NAV_HTML_DERIVED)
        assert result.noise_score <= 2.0


class TestCleanMarkdown:
    def test_clean_article_scores_above_threshold(self):
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        assert result.total > 8.0, (
            f"Expected score > 8.0 for clean article, got {result.total}\n{result.details}"
        )

    def test_clean_article_passes_gate(self):
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        assert result.passed(threshold=8.0)

    def test_clean_article_high_noise_score(self):
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        assert result.noise_score >= 3.5, (
            f"Expected noise_score ≥ 3.5, got {result.noise_score}"
        )

    def test_clean_article_high_structure_score(self):
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        assert result.structure_score >= 2.5, (
            f"Expected structure_score ≥ 2.5, got {result.structure_score}"
        )

    def test_clean_article_zero_noise_hits(self):
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        assert len(result.noise_hits) == 0, (
            f"Expected no noise hits, got: {result.noise_hits}"
        )


class TestThinContentGate:
    """B26: 'no noise' is vacuous when there's no content — a thin/failed
    extraction must not earn the full noise reward. The content-sufficiency
    gate must touch ONLY near-empty bodies, never real articles (gate region)."""

    THIN_FRAGMENT = "# Page Title\n\nLoading…"
    SHORT_BUT_REAL = (
        "The Eiffel Tower was completed in 1889 for the World's Fair in Paris. "
        "It stands 330 metres tall and was the tallest man-made structure in "
        "the world until the Chrysler Building was finished in 1930."
    )

    def test_thin_fragment_does_not_score_clean(self):
        result = score_markdown(self.THIN_FRAGMENT)
        # Was 5.0 before B26 (4/4 noise + 1.0 title). Must now read as unusable.
        assert result.total < 3.0, f"thin fragment scored {result.total}\n{result.details}"

    def test_thin_fragment_noise_reward_is_damped(self):
        result = score_markdown(self.THIN_FRAGMENT)
        assert result.noise_score < 2.0, (
            f"near-empty body must not earn full noise reward, got "
            f"{result.noise_score}"
        )

    def test_short_but_real_prose_keeps_noise_reward(self):
        # The discriminator is content VOLUME, not heading/length: real prose
        # (~200 chars) is substantive and must keep near-full noise credit.
        result = score_markdown(self.SHORT_BUT_REAL)
        assert result.noise_score >= 3.5, (
            f"short-but-substantive prose must keep its noise reward, got "
            f"{result.noise_score}"
        )

    def test_substantial_clean_article_unaffected(self):
        # The gate region must not move: a real clean article keeps full noise.
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        assert result.noise_score >= 3.5
        assert result.passed(threshold=8.0)


class TestMixedContent:
    def test_mixed_content_in_middle_range(self):
        result = score_markdown(MIXED_CONTENT)
        assert 4.0 <= result.total < 8.0, (
            f"Expected 4.0 ≤ score < 8.0 for mixed content, got {result.total}\n{result.details}"
        )

    def test_mixed_content_detects_some_noise(self):
        result = score_markdown(MIXED_CONTENT)
        assert len(result.noise_hits) >= 1


class TestScoreDataclass:
    def test_returns_judge_score_instance(self):
        result = score_markdown("# Hello\n\nSome content here.")
        assert isinstance(result, JudgeScore)

    def test_all_scores_within_bounds(self):
        for sample in [PURE_NAV_HTML_DERIVED, CLEAN_MARKDOWN_ARTICLE, MIXED_CONTENT]:
            result = score_markdown(sample)
            assert 0.0 <= result.noise_score <= 4.0
            assert 0.0 <= result.structure_score <= 3.0
            assert 0.0 <= result.density_score <= 3.0
            assert 0.0 <= result.total <= 10.0

    def test_total_equals_sum_of_axes(self):
        result = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        expected = round(result.noise_score + result.structure_score + result.density_score, 2)
        assert abs(result.total - expected) < 0.01

    def test_passed_gate_at_default_threshold(self):
        clean = score_markdown(CLEAN_MARKDOWN_ARTICLE)
        noisy = score_markdown(PURE_NAV_HTML_DERIVED)
        assert clean.passed() is True
        assert noisy.passed() is False


# ---------------------------------------------------------------------------
# B1 — calibration of the heuristic against the consumer (LLM) judgment.
# These pin the *finding*: the heuristic correlates moderately-to-strongly
# with consumer ratings, AND is trustworthy in the gate region (≥8.5), while
# its known weakness is the low range (over-rates thin/empty extractions).
# ---------------------------------------------------------------------------

from evals.calibrate_judge import (  # noqa: E402
    calibrate,
    load_samples,
    pearson,
)


class TestPearson:
    def test_perfect_positive(self):
        assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0

    def test_perfect_negative(self):
        assert pearson([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0

    def test_constant_series_is_zero_not_error(self):
        # statistics.correlation raises on a constant series; we guard to 0.0.
        assert pearson([5, 5, 5], [1, 2, 3]) == 0.0

    def test_too_few_points_is_zero(self):
        assert pearson([1], [2]) == 0.0


class TestCalibrationSet:
    def test_set_spans_the_quality_range(self):
        ratings = [s.rating for s in load_samples()]
        # Meaningful correlation needs spread, not all-clean anchors.
        assert min(ratings) <= 2.0, "need a near-unusable low anchor"
        assert max(ratings) >= 9.0, "need an ideal high anchor"

    def test_crafted_samples_present_without_fixtures(self):
        # load_samples must still work if golden fixtures are absent.
        assert len(load_samples()) >= 7


class TestCalibrationResult:
    def test_rows_carry_required_keys(self):
        result = calibrate()
        assert result["n"] == len(result["rows"])
        for row in result["rows"]:
            assert {"id", "heuristic", "rating", "delta"} <= set(row)
            assert abs(row["delta"] - round(row["heuristic"] - row["rating"], 2)) < 0.01

    def test_correlation_is_moderate_or_better(self):
        # The verified B1 finding: heuristic tracks consumer judgment (r≈0.79).
        # Guard against a future change that decorrelates the score.
        assert calibrate()["pearson_r"] >= 0.6

    def test_gate_region_is_well_calibrated(self):
        # The point of B1: in the region the 8.5 gate cares about, the heuristic
        # agrees with the consumer. Every high-anchor (rating ≥ 8.5) must score
        # ≥ 8.0 — i.e. "good" really means good where the gate lives.
        rows = calibrate()["rows"]
        high = [r for r in rows if r["rating"] >= 8.5]
        assert high, "expected high-quality anchors in the set"
        assert all(r["heuristic"] >= 8.0 for r in high)

    def test_main_runs_clean(self):
        from evals import calibrate_judge
        assert calibrate_judge.main([]) == 0
        assert calibrate_judge.main(["--json"]) == 0
