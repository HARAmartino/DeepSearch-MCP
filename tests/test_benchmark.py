"""Tests for evals/benchmark.py — the DeepSearch Quality Score (DQS)."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals import benchmark as bm

# DQS is deterministic (fixed offline battery); compute once for the module.
DQS_REGRESSION_FLOOR = 80.0


@pytest.fixture(scope="module")
def result():
    return bm.run_benchmark()


class TestComposition:
    def test_weights_sum_to_one(self):
        assert abs(sum(bm.WEIGHTS.values()) - 1.0) < 1e-9

    def test_subscores_present_and_in_range(self, result):
        assert set(result["subscores"]) == set(bm.WEIGHTS)
        for sub in result["subscores"].values():
            assert 0.0 <= sub["score"] <= 100.0

    def test_composite_in_range(self, result):
        assert 0.0 <= result["dqs"] <= 100.0

    def test_composite_equals_weighted_sum(self, result):
        expected = sum(bm.WEIGHTS[k] * result["subscores"][k]["score"] for k in bm.WEIGHTS)
        assert abs(result["dqs"] - round(expected, 1)) < 0.1


class TestDeterminism:
    def test_two_runs_match(self):
        # A benchmark must be reproducible release-over-release.
        assert bm.run_benchmark()["dqs"] == bm.run_benchmark()["dqs"]


class TestRegressionFloor:
    def test_dqs_above_floor(self, result):
        # Broad guard: a change that tanks quality fails CI. Not brittle —
        # current DQS is ~93, floor is well below.
        assert result["dqs"] >= DQS_REGRESSION_FLOOR, (
            f"DQS {result['dqs']} fell below floor {DQS_REGRESSION_FLOOR}: "
            f"{result['subscores']}"
        )

    def test_robustness_is_perfect(self, result):
        # Prime Directive 2: every error path must be contract-compliant.
        assert result["subscores"]["robustness"]["score"] == 100.0


class TestSubScores:
    def test_extraction_matches_gauntlet_gate(self, result):
        # Extraction sub-score is the gauntlet avg ×10; must clear the 8.5 gate.
        assert result["subscores"]["extraction"]["score"] >= 85.0

    def test_diversity_battery_nonempty(self):
        assert len(bm._DIVERSITY_TOPICS) >= 3


class TestCli:
    def test_main_text_and_json(self, capsys):
        assert bm.main([]) == 0
        capsys.readouterr()
        assert bm.main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert "dqs" in payload and "subscores" in payload
