#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Smith chart analysis — reflection coefficient, grid computation, normalization.

Pure-numpy module with no Qt dependencies. Follows the same pattern as
:mod:`pqwave.analysis.nyquist` and :mod:`pqwave.analysis.bode`.
"""

from __future__ import annotations

import numpy as np


def compute_reflection_coefficient(z: np.ndarray, z0: float = 50.0) -> np.ndarray:
    """Compute reflection coefficient Gamma = (Z - Z0) / (Z + Z0).

    Args:
        z: Complex impedance array Z = R + jX.
        z0: Reference impedance (default 50 Ohm).

    Returns:
        Complex reflection coefficient array.

    Notes:
        Open circuit (Z = inf) maps to Gamma = 1.0 + 0j.
        Short circuit (Z = 0) maps to Gamma = -1.0 + 0j.
    """
    z = np.asarray(z)
    inf_mask = np.isinf(z)
    # Avoid division by inf/inf (which would produce nan); handle after.
    with np.errstate(invalid="ignore", divide="ignore"):
        gamma = (z - z0) / (z + z0)
    if np.any(inf_mask):
        gamma = np.where(inf_mask, np.array(1.0 + 0.0j), gamma)
    # Guard against gamma still containing inf/nan after inf_mask handling.
    # This can happen when z = -z0, making the denominator zero and gamma = -inf,
    # which the inf_mask on z (not gamma) does not catch.
    gamma_inf = np.isinf(gamma)
    gamma_nan = np.isnan(gamma)
    if np.any(gamma_inf | gamma_nan):
        # Map inf/nan to unit circle boundary:
        #   z = -z0  ->  gamma = -inf  ->  -1.0+0j (short circuit)
        #   NaN from other edge cases  ->   1.0+0j (open circuit)
        gamma = np.where(
            gamma_inf,
            np.array(-1.0 + 0.0j),
            np.where(gamma_nan, np.array(1.0 + 0.0j), gamma),
        )
    return gamma


def normalize_impedance(z: np.ndarray, z0: float = 50.0) -> np.ndarray:
    """Normalize impedance: z_norm = Z / Z0.

    Args:
        z: Complex impedance array.
        z0: Reference impedance.

    Returns:
        Normalized complex impedance.
    """
    return z / z0


def smith_grid_circles() -> dict:
    """Compute Smith chart grid circle parameters.

    Constant-R circles in the Gamma-plane:

        center = (r/(r+1), 0),  radius = 1/(r+1)

    Constant-X arcs in the Gamma-plane:

        center = (1, 1/x),  radius = 1/|x|

    Returns:
        dict with keys:

        - ``r_circles``: dict mapping r_value (str) -> (cx, cy, radius)
        - ``x_arcs``: dict mapping x_value (str) -> (cx, cy, radius)
    """
    r_values = [0.0, 0.2, 0.5, 1.0, 2.0, 5.0]
    x_values_pos = [0.2, 0.5, 1.0, 2.0, 5.0]
    x_values = x_values_pos + [-x for x in x_values_pos]

    r_circles = {}
    for r in r_values:
        if np.isinf(r):
            continue
        cx = r / (r + 1.0)
        cy = 0.0
        radius = 1.0 / (r + 1.0)
        r_circles[f"{r:g}"] = (cx, cy, radius)

    x_arcs = {}
    for x in x_values:
        if abs(x) < 1e-12:
            continue
        cx = 1.0
        cy = 1.0 / x
        radius = 1.0 / abs(x)
        x_arcs[f"{x:g}"] = (cx, cy, radius)

    return {"r_circles": r_circles, "x_arcs": x_arcs}


def clamp_gamma(gamma: np.ndarray, max_mag: float = 0.999) -> np.ndarray:
    """Clamp |Gamma| to *max_mag*, preserving phase.

    Returns a copy when clamping is needed; returns the original array when
    no clamping is required (avoids unnecessary allocation).

    Args:
        gamma: Complex reflection coefficient array.
        max_mag: Maximum allowed magnitude (default 0.999).

    Returns:
        Clamped complex array.
    """
    mag = np.abs(gamma)
    mask = mag > max_mag
    if np.any(mask):
        result = gamma.copy()
        # Guard against inf/inf or nan/inf in mag division (safety net)
        with np.errstate(invalid="ignore", divide="ignore"):
            clamped = max_mag * (result[mask] / mag[mask])
        clamped = np.where(np.isfinite(clamped), clamped, max_mag + 0.0j)
        result[mask] = clamped
        return result
    return gamma
