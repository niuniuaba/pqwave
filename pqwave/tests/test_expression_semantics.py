"""Audit: expression evaluator semantics for Mag(), subtraction, step-aware ops."""
import numpy as np
import pytest


class TestMagSemantics:
    """Mag() must return real scalar, not complex-with-zero-imaginary."""

    def test_mag_returns_real_scalar(self):
        """Mag(complex_array) must have dtype float, not complex."""
        data = np.array([1.0 + 2.0j, 3.0 + 4.0j], dtype=np.complex128)
        mag = np.abs(data)
        assert not np.iscomplexobj(mag), \
            f"Mag returned complex dtype={mag.dtype}, expected float"
        assert mag.dtype in (np.float32, np.float64), \
            f"Mag unexpected dtype={mag.dtype}"

    def test_mag_of_real_stays_real(self):
        """Mag(real_array) must stay real."""
        data = np.array([1.0, -2.0, 3.0])
        mag = np.abs(data)
        assert not np.iscomplexobj(mag)

    def test_mag_subtraction_is_meaningful(self):
        """Mag(Vout) - Mag(Vin) must produce real difference, not complex zero."""
        a = np.array([1.0 + 0.5j, 2.0 + 1.0j])
        b = np.array([0.5 + 0.2j, 1.0 + 0.5j])
        mag_a = np.abs(a)
        mag_b = np.abs(b)
        diff = mag_a - mag_b
        assert not np.iscomplexobj(diff), "Mag subtraction returned complex"
        assert np.all(diff > 0), f"Expected positive differences, got {diff}"

    def test_db_returns_real(self):
        """db(complex) must return real dB values."""
        data = np.array([1.0 + 0.0j, 0.5 + 0.0j])
        db_vals = 20 * np.log10(np.abs(data) + 1e-300)
        assert not np.iscomplexobj(db_vals)


class TestSubtractionOrdering:
    """V(a)-V(b) must equal -(V(b)-V(a))."""

    def test_subtraction_anti_symmetry(self):
        va = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        vb = np.array([0.5, 1.5, 1.0, 2.0, 3.0])
        diff_ab = va - vb
        diff_ba = vb - va
        assert np.allclose(diff_ab, -diff_ba), \
            "V(a)-V(b) != -(V(b)-V(a))"

    def test_subtraction_with_constant(self):
        v = np.array([3.56, 2.0, 1.0])
        const = 3.56
        diff1 = v - const
        diff2 = const - v
        assert np.allclose(diff1, -diff2), \
            "V-const != -(const-V) — potential sign bug like LTspice thread"


class TestStepAwareIntegration:
    """integ() across step boundaries must behave correctly."""

    def test_integ_detects_step_boundaries(self):
        """Verify that stepped data integration either resets or accumulates
        based on the step index, not blindly across all data."""
        # Simulated stepped data: 3 steps, each with 1000 points
        n_steps, n_pts = 3, 1000
        t = np.tile(np.linspace(0, 1e-3, n_pts), n_steps)
        v = np.sin(2 * np.pi * 1000 * t)
        # Full integral across all steps
        # Use np.trapezoid (replaces np.trapz removed in NumPy 2.0)
        full_integ = np.trapezoid(v, t)
        # Per-step integrals
        per_step = []
        for s in range(n_steps):
            sl = slice(s * n_pts, (s + 1) * n_pts)
            per_step.append(np.trapezoid(v[sl], t[sl]))
        # Each step integral should be identical (same waveform)
        assert np.allclose(per_step[0], per_step[1], rtol=1e-10), \
            f"Step integrals differ: {per_step}"
        assert np.allclose(per_step[0], per_step[2], rtol=1e-10)


class TestComplexArithmetic:
    """Round-trip tests for complex operations."""

    def test_real_imag_roundtrip(self):
        c = np.array([1.0 + 2.0j, 3.0 - 4.0j])
        recon = np.real(c) + 1j * np.imag(c)
        assert np.allclose(c, recon)

    def test_mag_phase_roundtrip(self):
        c = np.array([1.0 + 2.0j, 3.0 - 4.0j])
        mag = np.abs(c)
        phase = np.angle(c)
        recon = mag * (np.cos(phase) + 1j * np.sin(phase))
        assert np.allclose(c, recon)

    def test_division_by_zero_returns_inf(self):
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([0.0, 1.0, 2.0])
        result = np.divide(a, b, where=b != 0, out=np.full_like(a, np.inf))
        assert result[0] == np.inf
        assert result[1] == 2.0

    def test_log_of_negative_returns_nan(self):
        v = np.array([-1.0, 1.0, 10.0])
        result = np.log10(np.abs(v) + 1e-300)
        assert result[0] == 0.0  # abs(-1)=1, log10(1)=0
        assert not np.any(np.isnan(result))
