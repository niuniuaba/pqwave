"""Polar plot analysis — pure-numpy computation for polar (magnitude/phase) plots.

Follows the same pattern as pqwave.analysis.nyquist.
"""

from __future__ import annotations

import numpy as np


def compute_polar_trace(
    mag: np.ndarray,
    phase: np.ndarray,
    phase_is_degrees: bool = True,
) -> dict:
    """Compute Cartesian (x, y) from polar (magnitude, phase) data.

    Args:
        mag: Magnitude array.
        phase: Phase array.
        phase_is_degrees: If True, phase is in degrees; if False, radians.

    Returns:
        dict with keys ``x``, ``y``, ``mag``, ``phase``.
    """
    if phase_is_degrees:
        phase_rad = np.deg2rad(phase)
    else:
        phase_rad = phase

    x = mag * np.cos(phase_rad)
    y = mag * np.sin(phase_rad)

    return {"x": x, "y": y, "mag": mag, "phase": phase}


def detect_polar_vectors(var_names: list[str]) -> tuple[str, str] | None:
    """Detect magnitude/phase vector pairs in a list of variable names.

    Supports conventions:
      - ``<name>_mag`` / ``<name>_phase``  (e.g., ``v(out)_mag``)
      - ``mag(<name>)`` / ``phase(<name>)`` (e.g., ``mag(v(out))``)
      - ``<name>_magnitude`` / ``<name>_phase``

    Returns:
        ``(mag_var, phase_var)`` tuple or ``None``.
    """
    mag_candidates = [
        v
        for v in var_names
        if v.endswith("_mag") or "mag(" in v.lower() or v.endswith("_magnitude")
    ]
    phase_candidates = [
        v for v in var_names if v.endswith("_phase") or "phase(" in v.lower()
    ]

    for mag in mag_candidates:
        base = mag
        # Strip known suffixes — use rsplit to avoid corrupting partial matches
        for suffix in ("_magnitude", "_mag"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        base = base.replace("mag(", "").rstrip(")")
        for phase in phase_candidates:
            phase_base = phase
            if phase_base.endswith("_phase"):
                phase_base = phase_base[: -len("_phase")]
            phase_base = phase_base.replace("phase(", "").rstrip(")")
            if base == phase_base:
                return (mag, phase)

    return None
