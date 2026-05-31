"""
Dogfooding regression — wires `evals/dogfood_regression.py` into pytest so CI
fails the moment extraction output drifts from the saved baseline.

If you intentionally changed extraction behavior, regenerate baselines with:

    python evals/dogfood_regression.py --update

…then review the diff in the `evals/dogfood_baseline/` files and commit them.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evals"))

import pytest

from evals.dogfood_regression import FIXTURES, golden_path, render_extraction


@pytest.mark.parametrize("name,html,url", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_dogfood_baseline_matches(name, html, url):
    """Each fixture's current extraction must equal its saved golden baseline."""
    g = golden_path(name)
    assert g.exists(), (
        f"Missing baseline for fixture '{name}'. "
        f"Run `python evals/dogfood_regression.py --update` to create it."
    )

    expected = g.read_text(encoding="utf-8")
    actual = render_extraction(html, url)

    if expected != actual:
        import difflib
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"baseline/{name}.expected.md",
                tofile=f"current/{name}.actual.md",
                n=2,
            )
        )
        pytest.fail(
            f"Dogfooding baseline drift for {name}:\n\n{diff}\n"
            f"If this change is intentional, run\n"
            f"    python evals/dogfood_regression.py --update\n"
            f"and commit the updated baseline."
        )
