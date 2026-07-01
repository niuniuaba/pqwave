"""Tests for impedance format conversion and display."""
import numpy as np
import pytest


class TestFormatComplex:
    """Test format_complex utility function."""

    def test_polar_positive_phase(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(100.0 + 50.0j, "Ω", "polar")
        # |Z| = sqrt(100²+50²) ≈ 111.8, θ = atan2(50,100) ≈ 26.6°
        assert "111.8" in result or "112" in result
        assert "26.6" in result or "26." in result
        assert "°" in result

    def test_polar_negative_phase(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(50.0 - 30.0j, "Ω", "polar")
        assert "-" in result or "∠" in result  # negative phase marker

    def test_rectangular_positive_reactance(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(100.0 + 50.0j, "Ω", "rectangular")
        assert "+ j50" in result or "+j50" in result

    def test_rectangular_negative_reactance(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(100.0 - 50.0j, "Ω", "rectangular")
        assert "- j50" in result or "-j50" in result

    def test_rectangular_pure_real(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(75.0 + 0.0j, "Ω", "rectangular")
        assert "75" in result
        assert "j" not in result

    def test_rectangular_pure_imag_positive(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(0.0 + 30.0j, "Ω", "rectangular")
        assert "j30" in result

    def test_rectangular_pure_imag_negative(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(0.0 - 30.0j, "Ω", "rectangular")
        assert "-j30" in result or "j-30" in result or "- j30" in result

    def test_roundtrip_conversion(self):
        """Polar → Rect → Polar must recover original within 1e-12."""
        from pqwave.utils.impedance_format import polar_to_rect, rect_to_polar
        mag, phase_deg = 100.0, 30.0
        r, x = polar_to_rect(mag, np.deg2rad(phase_deg))
        mag2, phase2_rad = rect_to_polar(r, x)
        assert abs(mag2 - mag) < 1e-12
        assert abs(np.rad2deg(phase2_rad) - phase_deg) < 1e-12

    def test_si_prefix_kilo(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(1200.0 + 0.0j, "Ω", "polar")
        assert "1.2 kΩ" in result or "1.20 kΩ" in result

    def test_si_prefix_milli(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(0.05 + 0.0j, "Ω", "polar")
        assert "50 mΩ" in result or "mΩ" in result

    def test_default_polar(self):
        from pqwave.utils.impedance_format import format_complex
        result = format_complex(100.0 + 50.0j, "", "polar")
        # Should work without unit suffix
        assert "111.8" in result or "112" in result
