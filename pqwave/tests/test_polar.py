"""Tests for polar plot analysis module."""
import numpy as np
import pytest


class TestDetectPolarVectors:
    """Test auto-detection of magnitude/phase vector pairs."""

    def test_detect_mag_phase_suffix(self):
        from pqwave.analysis.polar import detect_polar_vectors
        names = ["time", "v(out)_mag", "v(out)_phase", "frequency"]
        result = detect_polar_vectors(names)
        assert result is not None
        mag, phase = result
        assert mag == "v(out)_mag"
        assert phase == "v(out)_phase"

    def test_detect_mag_phase_parens(self):
        from pqwave.analysis.polar import detect_polar_vectors
        names = ["time", "mag(v(out))", "phase(v(out))", "v(in)"]
        result = detect_polar_vectors(names)
        assert result is not None
        mag, phase = result
        assert mag == "mag(v(out))"
        assert phase == "phase(v(out))"

    def test_detect_no_pair(self):
        from pqwave.analysis.polar import detect_polar_vectors
        names = ["time", "v(out)", "v(in)", "frequency"]
        result = detect_polar_vectors(names)
        assert result is None

    def test_detect_magnitude_phase_keywords(self):
        from pqwave.analysis.polar import detect_polar_vectors
        names = ["time", "v(out)_magnitude", "v(out)_phase"]
        result = detect_polar_vectors(names)
        assert result is not None


class TestComputePolarTrace:
    """Test polar trace computation."""

    def test_constant_phase_zero(self):
        from pqwave.analysis.polar import compute_polar_trace
        mag = np.array([0.5, 1.0, 2.0])
        phase = np.array([0.0, 0.0, 0.0])
        result = compute_polar_trace(mag, phase)
        # x = mag * cos(0) = mag, y = mag * sin(0) = 0
        assert np.allclose(result["x"], [0.5, 1.0, 2.0])
        assert np.allclose(result["y"], [0.0, 0.0, 0.0])

    def test_constant_phase_90_degrees(self):
        from pqwave.analysis.polar import compute_polar_trace
        mag = np.array([1.0, 2.0])
        phase = np.array([90.0, 90.0])
        result = compute_polar_trace(mag, phase, phase_is_degrees=True)
        # x = mag * cos(90°) = 0, y = mag * sin(90°) = mag
        assert np.allclose(result["x"], [0.0, 0.0], atol=1e-10)
        assert np.allclose(result["y"], [1.0, 2.0], atol=1e-10)

    def test_phase_in_radians(self):
        from pqwave.analysis.polar import compute_polar_trace
        mag = np.array([1.0])
        phase = np.array([np.pi / 2])  # 90 degrees in radians
        result = compute_polar_trace(mag, phase, phase_is_degrees=False)
        assert np.allclose(result["x"], [0.0], atol=1e-10)
        assert np.allclose(result["y"], [1.0], atol=1e-10)

    def test_output_dict_keys(self):
        from pqwave.analysis.polar import compute_polar_trace
        result = compute_polar_trace(np.array([1.0]), np.array([0.0]))
        assert "x" in result
        assert "y" in result
        assert "mag" in result
        assert "phase" in result
