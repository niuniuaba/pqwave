#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nyquist analysis module — pure-numpy computation for Nyquist plots.

Provides functions for computing Nyquist traces from real and imaginary
vector data, and for detecting real/imag vector pairs in variable lists.
"""

from __future__ import annotations

import numpy as np


def compute_nyquist_trace(
    real: np.ndarray,
    imag: np.ndarray,
    freq: np.ndarray | None = None,
) -> dict:
    """Compute a Nyquist trace from real and imaginary data.

    Args:
        real: Real-part data array.
        imag: Imaginary-part data array.
        freq: Optional frequency data array (same length as real/imag).

    Returns:
        dict with keys ``x`` (real), ``y`` (imag), and ``freq`` (optional).
    """
    return {"x": real, "y": imag, "freq": freq}


def detect_nyquist_vectors(var_names: list[str]) -> tuple[str, str] | None:
    """Detect real/imaginary vector pairs in a list of variable names.

    Supports naming conventions:
      - ``<name>_real`` / ``<name>_imag`` (e.g. ``v(out)_real``)
      - ``<name>(real)`` / ``<name>(imag)`` (e.g. ``I(R1)(real)``)
      - ``<name>.re`` / ``<name>.im`` (e.g. ``V(out).re``)
      - ``<name>.real`` / ``<name>.imag`` (e.g. ``V(out).real``)

    Returns:
        ``(real_var, imag_var)`` tuple if a matching pair is found,
        ``None`` otherwise.
    """
    # Convention 1: _real / _imag suffix
    real_candidates = [
        v for v in var_names
        if v.endswith("_real") or "(real)" in v.lower()
    ]
    imag_candidates = [
        v for v in var_names
        if v.endswith("_imag") or "(imag)" in v.lower()
    ]
    for r in real_candidates:
        base = r.replace("_real", "").replace("(real)", "").replace("(REAL)", "")
        for i in imag_candidates:
            ib = i.replace("_imag", "").replace("(imag)", "").replace("(IMAG)", "")
            if ib == base:
                return (r, i)

    # Convention 2: .re / .im or .real / .imag suffix
    re_parts = [
        v for v in var_names
        if v.lower().endswith(".re") or v.lower().endswith(".real")
    ]
    im_parts = [
        v for v in var_names
        if v.lower().endswith(".im") or v.lower().endswith(".imag")
    ]
    # Match by base name (strip suffix)
    for r in re_parts:
        r_base = r[:-3] if r.lower().endswith(".re") else r[:-5]
        r_base_lower = r_base.lower()
        for i in im_parts:
            i_base = i[:-3] if i.lower().endswith(".im") else i[:-5]
            if i_base.lower() == r_base_lower:
                return (r, i)

    return None
