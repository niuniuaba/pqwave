"""Impedance format conversion and display utilities.

Provides format_complex() for displaying complex values in polar (|Z|∠θ)
or rectangular (R+jX) format with SI prefixes.
"""
from __future__ import annotations

import math


def format_complex(
    value: complex, unit: str = "", mode: str = "polar"
) -> str:
    """Format a complex number for display.

    Args:
        value: Complex number (R + jX).
        unit: Unit string (e.g., "Ω", "V", "A"). Empty for unitless.
        mode: "polar" for |Z|∠θ or "rectangular" for R+jX.

    Returns:
        Formatted string.
    """
    r, x = value.real, value.imag

    if mode == "polar":
        mag = math.sqrt(r * r + x * x)
        phase = math.degrees(math.atan2(x, r))
        mag_str = _format_with_prefix(mag, unit)
        return f"{mag_str} ∠ {phase:.1f}°"

    else:  # rectangular
        r_str = _format_with_prefix(r, unit)
        if abs(x) < 1e-15:
            return r_str
        x_abs_str = _format_with_prefix(abs(x), unit)
        if x >= 0:
            return f"{r_str} + j{x_abs_str}"
        else:
            return f"{r_str} - j{x_abs_str}"


def polar_to_rect(magnitude: float, phase_rad: float) -> tuple[float, float]:
    """Convert polar (mag, phase_rad) to rectangular (R, X)."""
    return magnitude * math.cos(phase_rad), magnitude * math.sin(phase_rad)


def rect_to_polar(r: float, x: float) -> tuple[float, float]:
    """Convert rectangular (R, X) to polar (mag, phase_rad)."""
    return math.sqrt(r * r + x * x), math.atan2(x, r)


def _format_with_prefix(value: float, unit: str) -> str:
    """Format a real value with SI prefix and optional unit."""
    if value == 0.0:
        return f"0 {unit}".strip() if unit else "0"

    abs_val = abs(value)
    sign = "-" if value < 0 else ""

    if abs_val >= 1e12:
        return f"{sign}{abs_val/1e12:.3g} T{unit}"
    elif abs_val >= 1e9:
        return f"{sign}{abs_val/1e9:.3g} G{unit}"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val/1e6:.3g} M{unit}"
    elif abs_val >= 1e3:
        return f"{sign}{abs_val/1e3:.3g} k{unit}"
    elif abs_val >= 1.0:
        return f"{sign}{abs_val:.3g} {unit}".strip() if unit else f"{sign}{abs_val:.3g}"
    elif abs_val >= 1e-3:
        return f"{sign}{abs_val*1e3:.3g} m{unit}"
    elif abs_val >= 1e-6:
        return f"{sign}{abs_val*1e6:.3g} µ{unit}"
    elif abs_val >= 1e-9:
        return f"{sign}{abs_val*1e9:.3g} n{unit}"
    elif abs_val >= 1e-12:
        return f"{sign}{abs_val*1e12:.3g} p{unit}"
    else:
        return f"{sign}{abs_val:.3g} {unit}".strip() if unit else f"{sign}{abs_val:.3g}"
