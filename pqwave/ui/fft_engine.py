#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FFT engine — windowed FFT computation for waveform analysis.

Provides compute_fft() for the trace expression system and spectral
analysis helpers for the measure engine (THD, SINAD, SNR, SFDR).
"""

from __future__ import annotations

from typing import Tuple, Optional

import numpy as np

try:
    from scipy.signal.windows import (
        hann, hamming, blackman, kaiser,
        triang, parzen, cosine,
        bohman, nuttall, blackmanharris, flattop,
        gaussian, general_gaussian, tukey, chebwin,
        barthann, lanczos, exponential,
    )
    _HAS_SCIPY_WINDOWS = True
except ImportError:
    _HAS_SCIPY_WINDOWS = False


def _welch_window(n: int) -> np.ndarray:
    """Welch (parabolic) window: 1 - ((n - (N-1)/2) / ((N-1)/2))^2"""
    half = (n - 1) / 2.0
    i = np.arange(n)
    return 1.0 - ((i - half) / half) ** 2


def _nextpow2(n: int) -> int:
    return 1 << (n - 1).bit_length()


# Window registry: name → factory(n)  (callable or lambda for parameterized windows)
def _build_window_registry():
    if not _HAS_SCIPY_WINDOWS:
        return {}
    return {
        "none":              np.ones,
        "hann":              hann,
        "hamming":           hamming,
        "blackman":          blackman,
        "kaiser":            lambda n: kaiser(n, beta=14.0),
        "triangular":        triang,
        "parzen":            parzen,
        "welch":             _welch_window,
        "cosine":            cosine,
        "bohman":            bohman,
        "nuttall":           nuttall,
        "blackman-harris":   blackmanharris,
        "flattop":           flattop,
        "gaussian":          lambda n: gaussian(n, std=0.4),
        "general-gaussian":  lambda n: general_gaussian(n, p=1.5, sig=0.4),
        "tukey":             lambda n: tukey(n, alpha=0.5),
        "dolph-chebyshev":   lambda n: chebwin(n, at=100),
        "bartlett-hann":     barthann,
        "lanczos":           lanczos,
        "poisson":           lambda n: exponential(n, tau=3.0),
    }


_WINDOW_REGISTRY = _build_window_registry()


def _get_window(n: int, window_name: str) -> np.ndarray:
    """Return a window array of length n."""
    w = window_name.lower()
    if w == "none":
        return np.ones(n)
    if w in _WINDOW_REGISTRY:
        return _WINDOW_REGISTRY[w](n)
    if not _HAS_SCIPY_WINDOWS:
        if w == "hann":
            return np.hanning(n)
        elif w == "hamming":
            return np.hamming(n)
        elif w == "blackman":
            return np.blackman(n)
        raise ValueError(f"Window '{window_name}' requires scipy")
    raise ValueError(f"Unknown window: {window_name!r}")


def _binomial_smooth(data: np.ndarray, n_passes: int) -> np.ndarray:
    """Apply binomial (moving-average) smoothing.

    Each pass convolves with [1, 1] / 2, equivalent to a binomial filter.
    """
    if n_passes <= 0 or len(data) < 2:
        return data
    kernel = np.array([1.0, 1.0]) / 2.0
    result = data
    for _ in range(n_passes):
        result = np.convolve(result, kernel, mode='same')
    return result


def compute_fft(
    time_data: np.ndarray,
    signal: np.ndarray,
    window: str = "none",
    fft_size: int = 0,
    dc_removal: bool = True,
    representation: str = "db",
    x_range_mode: str = "full",
    x_range_start: float = 0.0,
    x_range_end: float = 0.0,
    binomial_smooth: int = 0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute windowed FFT and return (freq_array, magnitude_array).

    Args:
        time_data: Time values (1-D array), used to determine dt.
        signal: Signal values (1-D array) in linear space.
        window: Window name (see _get_window for supported values).
        fft_size: FFT length (0 = auto nextpow2).
        dc_removal: If True, subtract the mean before FFT.
        representation: "db" for dB, "linear" for raw magnitude.
        x_range_mode: "full" = entire signal; "manual" = slice to [start, end].
            "current zoom" must be handled by the caller before invoking.
        x_range_start: Start time for "manual" x_range_mode (seconds).
        x_range_end: End time for "manual" x_range_mode (seconds).
        binomial_smooth: Number of binomial smoothing passes (0 = off).

    Returns:
        (freq, magnitude) — 1-D arrays of same length (positive frequencies only).
    """
    if x_range_mode == "manual":
        mask = (time_data >= x_range_start) & (time_data <= x_range_end)
        time_data = time_data[mask]
        signal = signal[mask]

    n = len(signal)
    if n < 2 or len(time_data) < 2:
        raise ValueError("Signal and time data must have at least 2 points for FFT")

    if binomial_smooth > 0:
        signal = _binomial_smooth(signal, binomial_smooth)

    if dc_removal:
        signal = signal - np.mean(signal)

    win = _get_window(n, window)
    signal_win = signal * win / (np.mean(win) + 1e-300)  # coherent gain normalization

    if fft_size <= 0:
        fft_size = _nextpow2(n)

    dt = float(time_data[1] - time_data[0])
    if dt <= 0:
        raise ValueError("Time data must be strictly increasing")

    if n > 2:
        steps = np.diff(time_data)
        rel_variation = (np.max(steps) - np.min(steps)) / np.mean(steps)
        if rel_variation > 0.01:
            from pqwave.logging_config import get_logger
            get_logger(__name__).warning(
                "Non-uniform time steps detected (variation %.1f%%). FFT assumes uniform sampling.",
                rel_variation * 100,
            )

    spectrum = np.fft.rfft(signal_win, n=fft_size)
    freq = np.fft.rfftfreq(fft_size, d=dt)
    mag = np.abs(spectrum)

    if representation == "db":
        mag = 20.0 * np.log10(mag + 1e-300)

    return freq, mag


def find_spectral_peaks(
    freq: np.ndarray,
    mag: np.ndarray,
    fundamental: Optional[float] = None,
    max_harmonics: int = 10,
    min_height_db: float = -120.0,
) -> Tuple[float, list[float], list[float]]:
    """Find fundamental and harmonic peaks in a spectrum.

    Returns:
        (fundamental_freq, harmonic_freqs, harmonic_magnitudes)
    """
    if fundamental is None:
        peak_idx = np.argmax(mag)
        fundamental = float(freq[peak_idx])

    harmonic_freqs = []
    harmonic_mags = []

    for k in range(2, max_harmonics + 1):
        h_freq = fundamental * k
        tolerance = h_freq * 0.05
        mask = (freq >= h_freq - tolerance) & (freq <= h_freq + tolerance)
        if not np.any(mask):
            break
        idx = np.argmax(mag[mask])
        h_mag = float(mag[mask][idx])
        if h_mag < min_height_db:
            break
        harmonic_freqs.append(float(freq[mask][idx]))
        harmonic_mags.append(h_mag)

    return fundamental, harmonic_freqs, harmonic_mags


def compute_thd_from_spectrum(
    freq: np.ndarray,
    mag: np.ndarray,
    fundamental: Optional[float] = None,
    max_harmonics: int = 10,
) -> float:
    """Compute THD (Total Harmonic Distortion) as a ratio (0-1)."""
    fund_freq, h_freqs, h_mags = find_spectral_peaks(
        freq, mag, fundamental, max_harmonics
    )

    fund_linear = 10.0 ** (float(np.interp(fund_freq, freq, mag)) / 20.0)
    fund_power = fund_linear ** 2

    harmonic_power = 0.0
    for h_mag in h_mags:
        h_linear = 10.0 ** (h_mag / 20.0)
        harmonic_power += h_linear ** 2

    if fund_power <= 0:
        return 0.0

    return float(np.sqrt(harmonic_power) / np.sqrt(fund_power))


def compute_sinad_from_spectrum(
    freq: np.ndarray,
    mag: np.ndarray,
    fundamental: Optional[float] = None,
    max_harmonics: int = 10,
    exclude_dc_bins: int = 2,
) -> float:
    """Compute SINAD in dBc (positive = better)."""
    fund_freq, h_freqs, h_mags = find_spectral_peaks(
        freq, mag, fundamental, max_harmonics
    )

    mag_linear = 10.0 ** (mag / 20.0)
    total_power = np.sum(mag_linear[exclude_dc_bins:] ** 2)

    signal_power = 0.0
    fund_idx = np.argmin(np.abs(freq - fund_freq))
    signal_power += mag_linear[fund_idx] ** 2
    for h_freq in h_freqs:
        h_idx = np.argmin(np.abs(freq - h_freq))
        signal_power += mag_linear[h_idx] ** 2

    noise_dist_power = total_power - signal_power
    if noise_dist_power <= 0 or signal_power <= 0:
        return 0.0

    return float(10.0 * np.log10(signal_power / noise_dist_power))


def compute_snr_from_spectrum(
    freq: np.ndarray,
    mag: np.ndarray,
    fundamental: Optional[float] = None,
    max_harmonics: int = 10,
    exclude_dc_bins: int = 2,
) -> float:
    """Compute SNR in dBc (positive = better)."""
    fund_freq, h_freqs, h_mags = find_spectral_peaks(
        freq, mag, fundamental, max_harmonics
    )

    mag_linear = 10.0 ** (mag / 20.0)

    fund_idx = np.argmin(np.abs(freq - fund_freq))
    signal_power = mag_linear[fund_idx] ** 2

    exclude_mask = np.zeros(len(freq), dtype=bool)
    exclude_mask[:exclude_dc_bins] = True
    for df in [-1, 0, 1]:
        idx = fund_idx + df
        if 0 <= idx < len(freq):
            exclude_mask[idx] = True
    for h_freq in h_freqs:
        base_idx = np.argmin(np.abs(freq - h_freq))
        for df in [-1, 0, 1]:
            idx = base_idx + df
            if 0 <= idx < len(freq):
                exclude_mask[idx] = True

    noise_power = np.sum(mag_linear[~exclude_mask] ** 2)

    if noise_power <= 0 or signal_power <= 0:
        return 0.0

    return float(10.0 * np.log10(signal_power / noise_power))


def compute_sfdr_from_spectrum(
    freq: np.ndarray,
    mag: np.ndarray,
    fundamental: Optional[float] = None,
    exclude_dc_bins: int = 2,
) -> float:
    """Compute SFDR in dBc (positive = better)."""
    if fundamental is None:
        peak_idx = np.argmax(mag)
        fundamental = float(freq[peak_idx])

    fund_idx = np.argmin(np.abs(freq - fundamental))
    fund_mag = float(mag[fund_idx])

    exclude_mask = np.zeros(len(mag), dtype=bool)
    exclude_mask[:exclude_dc_bins] = True
    for df in range(-3, 4):
        idx = fund_idx + df
        if 0 <= idx < len(mag):
            exclude_mask[idx] = True

    remaining = mag.copy()
    remaining[exclude_mask] = -np.inf
    spur_idx = np.argmax(remaining)
    spur_mag = float(mag[spur_idx])

    return fund_mag - spur_mag
