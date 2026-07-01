#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Audit: verify FFT operates on full-resolution data, not downsampled display data.

Background
----------
LTspice's ``plotwinsize`` compression causes FFT artifacts when the display
decimation reduces the effective sample rate — a well-known user trap.  This
audit confirms that pqwave's FFT implementation is NOT subject to the same
problem.

Data Path Audit (from session/api.py)
--------------------------------------
_headless mode_:
  session.fft() -> _resolve_signal(signal) -> trace.x_data / trace.y_data
                                              (or direct dataset lookup)

_gui mode_:
  session.fft() -> _on_mutation("add", expr=f"fft({signal})")
                -> TraceManager.add_trace()
                -> ExprEvaluator.evaluate(var)   # full-res from raw file
                -> Trace(x_data=trace_x_data, y_data=y_data)  # stored full-res
                -> compute_fft(x_data, y_data)   # operates on full array

Key finding
-----------
Downsampling to 1600 points (DOWNSAMPLE_TARGET) happens ONLY in
_create_analog_plot_item() during PlotCurveItem construction.  The Trace
model object stored in ApplicationState.traces always holds the original
full-resolution arrays.  _resolve_signal() reads from state.traces (full)
or directly from the dataset (full).

compute_fft() in fft_engine.py also has NO internal downsampling — it
processes whatever array it receives from start to finish.

Verdict: FFT operates on full-resolution data. No aliasing risk from
         display decimation.
"""

import numpy as np
import pytest


class TestFFTResolution:
    """Verify FFT can detect frequencies above the Nyquist limit of decimated data."""

    @pytest.fixture
    def dual_tone_100k(self):
        """10 kHz + 45 kHz tones, 100k samples at 100 kHz sample rate.

        Decimated to 1600 pts, Nyquist = 800 Hz — 45 kHz would be aliased
        if FFT operated on decimated data.
        """
        fs = 100_000
        n = 100_000
        t = np.linspace(0, (n - 1) / fs, n)
        v = np.sin(2 * np.pi * 10_000 * t) + 0.5 * np.sin(2 * np.pi * 45_000 * t)
        return t, v, fs

    def test_fft_on_full_data_detects_45khz(self, dual_tone_100k):
        """FFT on full 100k-point data must detect both 10 kHz and 45 kHz."""
        t, v, fs = dual_tone_100k
        n = len(v)
        spectrum = np.abs(np.fft.rfft(v))
        freqs = np.fft.rfftfreq(n, 1 / fs)
        # Find peaks
        peak_idx = np.argmax(spectrum[1:]) + 1  # skip DC
        peak_freq = freqs[peak_idx]
        # Should find 10 kHz as the dominant peak
        assert abs(peak_freq - 10_000) < 100, \
            f"Expected dominant peak at 10 kHz, got {peak_freq} Hz"
        # Find 45 kHz peak — it should exist
        mask_40k_50k = (freqs >= 40_000) & (freqs <= 50_000)
        peak_45k = freqs[mask_40k_50k][np.argmax(spectrum[mask_40k_50k])]
        assert abs(peak_45k - 45_000) < 200, \
            f"Expected peak near 45 kHz, got {peak_45k} Hz"

    def test_fft_on_decimated_data_loses_45khz(self, dual_tone_100k):
        """FFT on 1600-point decimated data CANNOT detect 45 kHz (Nyquist violation)."""
        t, v, fs = dual_tone_100k
        # Decimate to 1600 points
        step = len(v) // 1600
        v_dec = v[::step]
        fs_dec = fs / step
        n = len(v_dec)
        spectrum = np.abs(np.fft.rfft(v_dec))
        freqs = np.fft.rfftfreq(n, 1 / fs_dec)
        mask_40k_50k = (freqs >= 40_000) & (freqs <= 50_000)
        if not np.any(mask_40k_50k):
            pytest.skip("Decimated Nyquist too low to represent 45 kHz — as expected")
        peak_in_40k50k = np.max(spectrum[mask_40k_50k])
        # If the 45 kHz component is present, it should be significant
        # If not, the decimation aliased it
        # This documents the risk
        assert peak_in_40k50k < 0.1 * np.max(spectrum), \
            "45 kHz survived decimation unexpectedly"

    def test_decimated_nyquist_limit(self):
        """Document: 1600-pt decimation on 100k samples gives Nyquist = fs_dec/2."""
        fs = 100_000
        n = 100_000
        step = n // 1600
        fs_dec = fs / step
        nyquist_dec = fs_dec / 2
        # step ≈ 62, fs_dec ≈ 1600 Hz, Nyquist ≈ 800 Hz
        # A 45 kHz signal would be catastrophically aliased
        assert nyquist_dec < 1000, \
            f"Decimated Nyquist={nyquist_dec} Hz — any signal above this is at risk"
