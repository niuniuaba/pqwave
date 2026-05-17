#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bode plot computation — magnitude/phase (AC analysis) and FFT modes.

Pure-numpy module with no Qt dependencies, callable from both UI and CLI.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def detect_bode_vectors(var_names: list[str]) -> tuple[str, str, str] | None:
    """Auto-detect magnitude (dB), phase (deg), and frequency vectors.

    Looks for pairs like ``v(out)_db`` / ``v(out)_phase`` or
    ``db(v(out))`` / ``phase(v(out))``. Returns ``(mag_name, phase_name,
    freq_name)`` or ``None``.

    Args:
        var_names: List of variable names (e.g. from a raw-file header).

    Returns:
        A ``(mag, phase, freq)`` tuple or ``None`` if no matching pair is found.
    """
    mag_candidates = [
        v for v in var_names
        if v.endswith("_db") or "db(" in v.lower()
    ]
    phase_candidates = [
        v for v in var_names
        if v.endswith("_phase") or "phase(" in v.lower()
    ]

    for mag in mag_candidates:
        base = mag.replace("_db", "").replace("db(", "").rstrip(")")
        for phase in phase_candidates:
            phase_base = phase.replace("_phase", "").replace("phase(", "").rstrip(")")
            if base == phase_base:
                freq_var = _find_frequency(var_names)
                return (mag, phase, freq_var)

    mag_candidates = [
        v for v in var_names
        if "magnitude" in v.lower() or v.endswith("_mag")
    ]
    if mag_candidates and phase_candidates:
        freq_var = _find_frequency(var_names)
        return (mag_candidates[0], phase_candidates[0], freq_var)

    return None


def _find_frequency(var_names: list[str]) -> str | None:
    """Try to locate a frequency-like variable from the list."""
    for v in var_names:
        low = v.lower()
        if low in ("frequency", "freq", "frequ", "freq."):
            return v
    for v in var_names:
        low = v.lower()
        if not any(low.startswith(p) for p in ("v(", "i(", "time", "x")):
            return v
    return None


def compute_bode(
    mag_db: np.ndarray | None = None,
    phase_deg: np.ndarray | None = None,
    freq: np.ndarray | None = None,
    signal: np.ndarray | None = None,
    sampling_rate: float | None = None,
) -> dict:
    """Compute a Bode plot from magnitude/phase vectors or a time-domain signal.

    Two modes are supported:

    **AC analysis mode** (pre-computed magnitude and phase):
        Provide ``mag_db``, ``phase_deg``, and optionally ``freq``.

    **FFT mode** (time-domain signal):
        Provide ``signal`` and ``sampling_rate``.  The DC component is
        excluded from the returned arrays.

    Args:
        mag_db: Magnitude in decibels (AC analysis mode).
        phase_deg: Phase in degrees (AC analysis mode).
        freq: Frequency vector (optional in AC analysis mode; defaults to
            integer indices).
        signal: Time-domain signal array (FFT mode).
        sampling_rate: Sampling rate in Hz (FFT mode).

    Returns:
        A dict with keys ``"gain_db"``, ``"phase_deg"``, and ``"freq"``,
        each containing a NumPy array.

    Raises:
        ValueError: If neither ``(mag_db, phase_deg)`` nor
            ``(signal, sampling_rate)`` is provided.
    """
    if signal is not None and sampling_rate is not None:
        n = len(signal)
        fft = np.fft.rfft(signal)
        freq = np.fft.rfftfreq(n, d=1.0 / sampling_rate)
        mag = np.abs(fft)
        mag_db = 20 * np.log10(mag + 1e-300)
        phase_deg = np.angle(fft, deg=True)
        # Skip the DC bin (index 0)
        return {
            "gain_db": mag_db[1:],
            "phase_deg": phase_deg[1:],
            "freq": freq[1:],
        }

    if mag_db is not None and phase_deg is not None:
        freq_arr = freq if freq is not None else np.arange(len(mag_db), dtype=float)
        return {
            "gain_db": np.asarray(mag_db),
            "phase_deg": np.asarray(phase_deg),
            "freq": np.asarray(freq_arr),
        }

    raise ValueError(
        "Either (mag_db, phase_deg) or (signal, sampling_rate) must be provided"
    )
