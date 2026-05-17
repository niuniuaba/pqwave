#!/usr/bin/env python3
"""Tests for the histogram computation engine."""

import numpy as np
import pytest
from pqwave.analysis.histogram import compute_histogram


def test_histogram_basic():
    rng = np.random.default_rng(42)
    data = rng.normal(0, 1, 10000)
    result = compute_histogram(data, bins=20)
    assert "counts" in result
    assert "edges" in result
    assert "centers" in result
    assert len(result["counts"]) == 20
    assert len(result["edges"]) == 21
    assert len(result["centers"]) == 20
    result_density = compute_histogram(data, bins=20, norm="density")
    area = np.sum(result_density["counts"] * np.diff(result_density["edges"]))
    assert 0.9 < area < 1.1


def test_histogram_auto_bins():
    data = np.random.default_rng(42).normal(0, 1, 1000)
    result = compute_histogram(data)
    assert len(result["counts"]) > 0


def test_histogram_range():
    data = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    result = compute_histogram(data, bins=5, range=(0, 10))
    np.testing.assert_array_equal(result["edges"], np.array([0, 2, 4, 6, 8, 10], dtype=float))


def test_histogram_normalization_modes():
    rng = np.random.default_rng(42)
    data = rng.uniform(0, 10, 5000)
    r_count = compute_histogram(data, bins=10, norm="count")
    r_density = compute_histogram(data, bins=10, norm="density")
    r_prob = compute_histogram(data, bins=10, norm="probability")
    assert abs(np.sum(r_count["counts"]) - 5000) < 1
    assert abs(np.sum(r_density["counts"] * np.diff(r_density["edges"])) - 1.0) < 0.01
    assert abs(np.sum(r_prob["counts"]) - 1.0) < 0.01


def test_histogram_config_defaults():
    from pqwave.models.state import HistogramConfig
    cfg = HistogramConfig()
    assert cfg.bins is None
    assert cfg.norm == "count"
    assert cfg.range is None


def test_histogram_config_to_from_dict():
    from pqwave.models.state import HistogramConfig
    cfg = HistogramConfig(bins=50, norm="density", range=(0, 5))
    d = cfg.to_dict()
    assert d["bins"] == 50
    assert d["norm"] == "density"
    restored = HistogramConfig.from_dict(d)
    assert restored.bins == 50
    assert restored.norm == "density"
    assert restored.range == (0, 5)
