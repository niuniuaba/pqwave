"""Tests for multi-run analysis engine."""
import numpy as np
import pytest
from pqwave.analysis.multi_run import (
    compute_cross_run_stats,
    compute_run_measurements,
    compute_yield,
    compute_worst_cases,
    compute_sensitivity,
)


class TestCrossRunStats:
    def test_basic_stats_three_runs(self):
        data = np.array([
            [1.0, 2.0, 3.0, 4.0, 5.0],  # run 0
            [2.0, 3.0, 4.0, 5.0, 6.0],  # run 1
            [3.0, 4.0, 5.0, 6.0, 7.0],  # run 2
        ])
        result = compute_cross_run_stats(data)
        assert np.allclose(result["mean"], [2.0, 3.0, 4.0, 5.0, 6.0])
        assert np.allclose(result["min"], [1.0, 2.0, 3.0, 4.0, 5.0])
        assert np.allclose(result["max"], [3.0, 4.0, 5.0, 6.0, 7.0])

    def test_single_run_std_is_zero(self):
        data = np.array([[1.0, 2.0, 3.0]])
        result = compute_cross_run_stats(data)
        assert np.allclose(result["std"], [0.0, 0.0, 0.0])

    def test_stats_with_mask(self):
        data = np.array([
            [1.0, 2.0],
            [3.0, 4.0],
            [5.0, 6.0],
            [7.0, 8.0],
        ])
        mask = np.array([True, False, True, False])
        result = compute_cross_run_stats(data, run_mask=mask)
        assert np.allclose(result["mean"], [3.0, 4.0])


class TestRunMeasurements:
    def test_max_per_run(self):
        data = np.array([
            [1.0, 5.0, 3.0],
            [2.0, 1.0, 8.0],
            [4.0, 4.0, 4.0],
        ])
        result = compute_run_measurements(data, "max")
        assert np.allclose(result, [5.0, 8.0, 4.0])

    def test_min_per_run(self):
        data = np.array([
            [1.0, 5.0, 3.0],
            [2.0, 1.0, 8.0],
        ])
        result = compute_run_measurements(data, "min")
        assert np.allclose(result, [1.0, 1.0])


class TestYield:
    def test_all_pass(self):
        data = np.array([
            [1.0, 2.0, 3.0],
            [1.5, 2.5, 3.5],
        ])
        result = compute_yield(data, low=0.0, high=5.0)
        assert np.allclose(result, [100.0, 100.0, 100.0])

    def test_half_pass(self):
        data = np.array([
            [0.0, 2.0],
            [2.0, 2.0],
        ])
        result = compute_yield(data, low=1.0, high=3.0)
        assert np.allclose(result, [50.0, 100.0])

    def test_yield_scalar_with_measurement(self):
        data = np.array([
            [1.0, 5.0, 3.0],
            [2.0, 1.0, 8.0],
            [4.0, 4.0, 4.0],
        ])
        result = compute_yield(data, low=2.0, high=6.0, measure="max")
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0


class TestWorstCases:
    def test_top_two_by_max_abs_diff(self):
        data = np.array([
            [1.0, 2.0, 3.0],  # nominal (run 0)
            [1.1, 2.1, 3.1],  # run 1 — small diff
            [5.0, 6.0, 7.0],  # run 2 — big diff
            [1.2, 2.2, 3.2],  # run 3 — small diff
        ])
        worst = compute_worst_cases(data, nominal_index=0, n=2)
        assert len(worst) == 2
        assert worst[0]["run_index"] == 2  # biggest deviation
        assert "deviation" in worst[0]


class TestSensitivity:
    def test_perfect_positive_correlation(self):
        measurements = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        params = {"C1": np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
                   "L1": np.array([5.0, 4.0, 3.0, 2.0, 1.0])}
        result = compute_sensitivity(measurements, params)
        assert result[0]["param"] == "C1"
        assert result[0]["r"] > 0.99
        assert result[1]["param"] == "L1"
        assert result[1]["r"] < -0.99

    def test_no_params_returns_empty(self):
        result = compute_sensitivity(np.array([1.0, 2.0]), {})
        assert result == []
