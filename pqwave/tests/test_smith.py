#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Smith chart analysis module."""

import numpy as np
import pytest


class TestReflectionCoefficient:
    """Test Gamma = (Z - Z0) / (Z + Z0)."""

    def test_matched_load_to_center(self):
        from pqwave.analysis.smith import compute_reflection_coefficient

        z = np.array([50.0 + 0.0j])
        gamma = compute_reflection_coefficient(z, z0=50.0)
        assert np.allclose(gamma, 0.0 + 0.0j)

    def test_open_circuit_to_edge(self):
        from pqwave.analysis.smith import compute_reflection_coefficient

        z = np.array([np.inf + 0.0j])
        gamma = compute_reflection_coefficient(z, z0=50.0)
        assert np.allclose(gamma, 1.0 + 0.0j)

    def test_short_circuit_to_neg_edge(self):
        from pqwave.analysis.smith import compute_reflection_coefficient

        z = np.array([0.0 + 0.0j])
        gamma = compute_reflection_coefficient(z, z0=50.0)
        assert np.allclose(gamma, -1.0 + 0.0j)

    def test_inductive_50ohms(self):
        from pqwave.analysis.smith import compute_reflection_coefficient

        z = np.array([50.0 + 50.0j])
        gamma = compute_reflection_coefficient(z, z0=50.0)
        # Gamma = j50 / (100 + j50) = j50*(100-j50)/(10000+2500) = (2500 + j5000)/12500
        # = 0.2 + j0.4
        assert np.allclose(gamma, 0.2 + 0.4j)

    def test_custom_z0(self):
        from pqwave.analysis.smith import compute_reflection_coefficient

        z = np.array([75.0 + 0.0j])
        gamma = compute_reflection_coefficient(z, z0=75.0)
        assert np.allclose(gamma, 0.0 + 0.0j)

    def test_scalar_z(self):
        """Test that a Python float (non-array) input works."""
        from pqwave.analysis.smith import compute_reflection_coefficient

        gamma = compute_reflection_coefficient(50.0 + 0.0j, z0=50.0)
        assert np.allclose(gamma, 0.0 + 0.0j)

    def test_array_input(self):
        """Test multiple impedances at once."""
        from pqwave.analysis.smith import compute_reflection_coefficient

        z = np.array([50.0 + 0.0j, np.inf + 0.0j, 0.0 + 0.0j])
        gamma = compute_reflection_coefficient(z, z0=50.0)
        assert len(gamma) == 3
        assert np.allclose(gamma[0], 0.0 + 0.0j)
        assert np.allclose(gamma[1], 1.0 + 0.0j)
        assert np.allclose(gamma[2], -1.0 + 0.0j)


class TestSmithGrid:
    """Test Smith chart grid circle computation."""

    def test_constant_r_circles(self):
        from pqwave.analysis.smith import smith_grid_circles

        grid = smith_grid_circles()
        r_circles = grid["r_circles"]
        # R=0 circle (outer boundary): center (0,0), radius 1
        assert "0" in r_circles or 0 in r_circles
        # R=1 circle: center (0.5, 0), radius 0.5
        r1 = r_circles.get("1") or r_circles.get(1)
        if r1 is not None:
            cx, cy, radius = r1
            assert abs(cx - 0.5) < 1e-10
            assert abs(cy) < 1e-10
            assert abs(radius - 0.5) < 1e-10

    def test_constant_x_arcs(self):
        from pqwave.analysis.smith import smith_grid_circles

        grid = smith_grid_circles()
        x_arcs = grid["x_arcs"]
        # X=0 arc: the real axis (center at infinity -> won't be a circle)
        # X=1 arc: center (1, 1), radius 1
        x1 = x_arcs.get("1") or x_arcs.get(1)
        if x1 is not None:
            cx, cy, radius = x1
            assert abs(cx - 1.0) < 1e-10
            assert abs(cy - 1.0) < 1e-10
            assert abs(radius - 1.0) < 1e-10

    def test_standard_r_values_present(self):
        from pqwave.analysis.smith import smith_grid_circles

        grid = smith_grid_circles()
        r_values = [str(k) for k in grid["r_circles"].keys()]
        for expected in ["0", "0.2", "0.5", "1", "2", "5"]:
            assert expected in r_values, f"R={expected} circle missing"

    def test_standard_x_values_present(self):
        from pqwave.analysis.smith import smith_grid_circles

        grid = smith_grid_circles()
        x_values = [str(k) for k in grid["x_arcs"].keys()]
        for expected in ["0.2", "0.5", "1", "2", "5"]:
            assert expected in x_values, f"X={expected} arc missing"
        for expected in ["-0.2", "-0.5", "-1", "-2", "-5"]:
            assert expected in x_values, f"X={expected} arc missing"


class TestNormalizeImpedance:
    """Test impedance normalization Z -> z = Z / Z0."""

    def test_normalize_50_to_50(self):
        from pqwave.analysis.smith import normalize_impedance

        z = np.array([50.0 + 0.0j])
        zn = normalize_impedance(z, z0=50.0)
        assert np.allclose(zn, 1.0 + 0.0j)

    def test_normalize_array(self):
        """Test normalization with multiple values."""
        from pqwave.analysis.smith import normalize_impedance

        z = np.array([50.0 + 0.0j, 100.0 + 0.0j, 25.0 + 0.0j])
        zn = normalize_impedance(z, z0=50.0)
        expected = np.array([1.0 + 0.0j, 2.0 + 0.0j, 0.5 + 0.0j])
        assert np.allclose(zn, expected)

    def test_normalize_complex(self):
        """Test normalization with complex impedance."""
        from pqwave.analysis.smith import normalize_impedance

        z = np.array([50.0 + 50.0j])
        zn = normalize_impedance(z, z0=50.0)
        assert np.allclose(zn, 1.0 + 1.0j)


class TestClampGamma:
    """Test clamping of reflection coefficient magnitude."""

    def test_no_clamp_needed(self):
        from pqwave.analysis.smith import clamp_gamma

        gamma = np.array([0.5 + 0.0j])
        result = clamp_gamma(gamma, max_mag=0.999)
        assert np.allclose(result, gamma)
        # Should be original object (no copy needed)
        assert result is gamma

    def test_clamp_excessive(self):
        from pqwave.analysis.smith import clamp_gamma

        gamma = np.array([5.0 + 0.0j])  # |Gamma| = 5
        result = clamp_gamma(gamma, max_mag=0.999)
        assert np.abs(result[0]) < 1.0
        assert abs(np.abs(result[0]) - 0.999) < 1e-10
        # Phase should be preserved (0 deg)
        assert np.allclose(result, 0.999 + 0.0j)

    def test_clamp_preserves_phase(self):
        from pqwave.analysis.smith import clamp_gamma

        gamma = np.array([0.0 + 5.0j])  # |Gamma| = 5, phase = 90 deg
        result = clamp_gamma(gamma, max_mag=0.999)
        assert np.abs(result[0]) < 1.0
        # Phase should be 90 deg
        assert abs(np.angle(result[0]) - np.pi / 2) < 1e-10

    def test_mixed_array(self):
        from pqwave.analysis.smith import clamp_gamma

        gamma = np.array([0.2 + 0.0j, 5.0 + 0.0j, 0.3 + 0.0j])
        result = clamp_gamma(gamma, max_mag=0.999)
        assert np.allclose(result[0], gamma[0])
        assert np.abs(result[1]) < 1.0
        assert np.allclose(result[2], gamma[2])

    def test_custom_max_mag(self):
        from pqwave.analysis.smith import clamp_gamma

        gamma = np.array([5.0 + 0.0j])
        result = clamp_gamma(gamma, max_mag=0.5)
        assert np.allclose(result, 0.5 + 0.0j)
