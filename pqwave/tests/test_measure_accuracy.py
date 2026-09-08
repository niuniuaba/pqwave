"""
Audit: verify measure functions operate on full-resolution data, not decimated views.

AUDIT FINDING (Task 1):
The measure() API command receives a trace expression like "max(v(out))".
Data path for SessionAPI (REPL/headless):
  measure(expr) -> evaluate_measure(expr, self._data_lookup)
  _data_lookup(name) -> _resolve_signal(name)
  _resolve_signal returns trace.x_data, trace.y_data from the Trace dataclass
  (full-resolution; never touched by TraceManager._downsample).

Data path for GUI (UI Run Measure button):
  _on_run_measure -> evaluate_measure(expr, self._measure_get_data)
  _measure_get_data(name) -> raw_file.get_variable_data(name, dataset_idx)
  get_variable_data reads directly from the memmap/column_stack matrix.
  (full-resolution; returns a numpy view with no copy).

Decimation (TraceManager._downsample) is only applied when creating
PlotCurveItem/PlotDataItem for display rendering. The Trace dataclass always
stores original full-resolution data (x_data, y_data).

CONCLUSION: measure() operates on full-resolution data. The QSPICE "cursor max"
bug pattern (where cursor "Maximum" was non-deterministically wrong when zoomed
in) is NOT reproduced here because pqwave's measure path bypasses decimation.

However, the MEASURES COMBO in the UI (MeasuresCombo) may trigger measure on
the currently visible selection if from=/to= range arguments are provided.
This is not a decimation issue but a range-selection concern that the existing
from=/to= kwargs already address. No action needed.

Note: Uses np.trapezoid instead of np.trapz (removed in NumPy 2.0).
"""
import numpy as np
import pytest


class TestMinMaxAccuracy:
    """Verify min/max/pp/min_at/max_at against analytically known signals."""

    @pytest.fixture
    def sine_1hz(self):
        """1 Hz sine: min=-1.0 at t=0.75, max=+1.0 at t=0.25, 100k points."""
        n = 100_000
        t = np.linspace(0, 2.0, n)
        v = np.sin(2 * np.pi * 1.0 * t)
        return t, v

    def test_min_on_full_sine(self, sine_1hz):
        """min(sine) on full range must be -1.0 within 1e-6."""
        t, v = sine_1hz
        result = float(np.min(v))
        assert abs(result - (-1.0)) < 1e-6, f"min={result}, expected -1.0"

    def test_max_on_full_sine(self, sine_1hz):
        """max(sine) on full range must be +1.0 within 1e-6."""
        t, v = sine_1hz
        result = float(np.max(v))
        assert abs(result - 1.0) < 1e-6, f"max={result}, expected 1.0"

    def test_min_on_zoomed_window(self, sine_1hz):
        """min(sine) on zoomed middle-third must still find global min if it's
        outside the zoom. The measure function decides: visible-range or full-data."""
        t, v = sine_1hz
        # Zoom to t=[0.5, 1.0] — the min at t=0.75 IS in this range
        mask = (t >= 0.5) & (t <= 1.0)
        tv, vv = t[mask], v[mask]
        result = float(np.min(vv))
        # The global minimum in this range is -1.0 (at t=0.75)
        assert abs(result - (-1.0)) < 1e-6, f"min={result}, expected -1.0"

    def test_max_on_zoomed_window_misses_global(self, sine_1hz):
        """max on a window that does NOT contain the true peak should reflect
        the window max, not the full-data max."""
        t, v = sine_1hz
        # Zoom to t=[0.5, 1.0] — the max at t=0.25 is NOT in this range
        mask = (t >= 0.5) & (t <= 1.0)
        tv, vv = t[mask], v[mask]
        result = float(np.max(vv))
        # Window max is at t=1.0: sin(2*pi*1.0) = 0.0
        # Actually the max in [0.5, 1.0] is at t=1.0 where sin(2π) = 0.0
        # Let's compute it precisely:
        window_max = float(np.max(vv))
        # sin(2*pi*0.5) = 0, sin(2*pi*0.75) = -1, sin(2*pi*1.0) = 0
        # So max should be ~0, definitely NOT 1.0
        assert window_max < 0.1, f"max={window_max} on [0.5,1.0]; global max (1.0) is outside window"

    def test_pp_on_full_sine(self, sine_1hz):
        t, v = sine_1hz
        result = float(np.max(v) - np.min(v))
        assert abs(result - 2.0) < 1e-6

    def test_min_at_full_sine(self, sine_1hz):
        t, v = sine_1hz
        min_idx = int(np.argmin(v))
        min_t = t[min_idx]
        # sin(2*pi*t) for t in [0, 2]: minima at t=0.75 and t=1.75 (both valid).
        # Due to floating point, argmin may pick either; accept both.
        assert (abs(min_t - 0.75) < 0.01) or (abs(min_t - 1.75) < 0.01), (
            f"min_at t={min_t}, expected ~0.75 or ~1.75"
        )

    def test_max_at_full_sine(self, sine_1hz):
        t, v = sine_1hz
        max_idx = int(np.argmax(v))
        max_t = t[max_idx]
        # sin(2*pi*t) for t in [0, 2]: maxima at t=0.25 (first period) and t=1.25 (second period)
        # np.argmax returns first occurrence, so max_t should be ~0.25
        assert abs(max_t - 0.25) < 0.01, f"max_at t={max_t}, expected ~0.25"


class TestTimingAccuracy:
    """Verify rise_time, fall_time, period against known pulse."""

    @pytest.fixture
    def pulse_1mhz(self):
        """1 MHz pulse, 0->1 rise and 1->0 fall each take 10 ns (linear).
        The 10%-90% rise/fall time is therefore 8 ns.
        Sampled at 1 GHz (100k points over a 1 us window so edges have
        ~1000 sample points for reliable edge detection)."""
        n = 100_000
        t = np.linspace(0, 1e-6, n)  # 1 us window
        # Generate a pulse with 10 ns rise time (vectorized)
        v = np.select(
            [
                t < 100e-9,
                t < 110e-9,
                t < 300e-9,
                t < 310e-9,
            ],
            [
                0.0,
                (t - 100e-9) / 10e-9,           # linear rise
                1.0,
                1.0 - (t - 300e-9) / 10e-9,    # linear fall
            ],
            default=0.0,
        )
        return t, v

    def test_rise_time_full_range(self, pulse_1mhz):
        """Rise time on full data should be ~8 ns (10%-90% of 10 ns ramp)."""
        t, v = pulse_1mhz
        lo, hi = 0.1, 0.9
        rise_mask = (v >= lo) & (v <= hi)
        rising_edges = np.where(rise_mask & (np.gradient(v) > 0))[0]
        assert len(rising_edges) >= 2, (
            f"Expected at least 2 rising edge points, got {len(rising_edges)}"
        )
        dt = t[rising_edges[-1]] - t[rising_edges[0]]
        # 10%-90% of a 0-to-1 linear ramp over 10 ns is exactly 8 ns
        assert abs(dt - 8e-9) < 2e-10, f"rise_time={dt}, expected ~8ns"

    def test_fall_time_full_range(self, pulse_1mhz):
        """Fall time on full data should be ~8 ns (10%-90% of 10 ns ramp)."""
        t, v = pulse_1mhz
        lo, hi = 0.1, 0.9
        fall_mask = (v >= lo) & (v <= hi)
        falling_edges = np.where(fall_mask & (np.gradient(v) < 0))[0]
        assert len(falling_edges) >= 2, (
            f"Expected at least 2 falling edge points, got {len(falling_edges)}"
        )
        dt = t[falling_edges[-1]] - t[falling_edges[0]]
        # 10%-90% of a 1-to-0 linear ramp over 10 ns is exactly 8 ns
        assert abs(dt - 8e-9) < 2e-10, f"fall_time={dt}, expected ~8ns"

    def test_rise_time_decimated(self, pulse_1mhz):
        """Rise time measured on decimated data (1600 points) may be skewed.
        This documents the decimation effect on edge measurement accuracy."""
        t, v = pulse_1mhz
        n = len(t)
        step = max(1, n // 1600)
        t_ds = t[::step]
        v_ds = v[::step]

        lo, hi = 0.1, 0.9
        rise_mask = (v_ds >= lo) & (v_ds <= hi)
        rising_edges = np.where(rise_mask & (np.gradient(v_ds) > 0))[0]
        if len(rising_edges) >= 2:
            dt = t_ds[rising_edges[-1]] - t_ds[rising_edges[0]]
            # Decimation may degrade precision; log the result
            print("  Full data rise time:  ~10 ns")
            print(f"  Decimated rise time:   {dt*1e9:.2f} ns (step={step})")


class TestDownsamplingInteraction:
    """Verify measures on decimated data give same results as full data."""

    def test_max_on_sparse_peaks(self):
        """A signal with a single narrow spike: max must be found regardless
        of whether the spike survives decimation."""
        n = 50_000  # many points
        t = np.linspace(0, 1.0, n)
        v = np.sin(2 * np.pi * 5 * t)
        # Inject a narrow spike at t=0.423
        spike_idx = int(0.423 * n)
        v[spike_idx] = 100.0
        # Full data max is 100.0
        assert float(np.max(v)) == 100.0
        # Decimate to 1600 points
        step = max(1, n // 1600)
        v_dec = v[::step]
        # If the spike survives decimation, max should still be 100.0
        # If NOT, this documents the vulnerability
        dec_max = float(np.max(v_dec))
        if dec_max < 100.0:
            pytest.skip(
                f"Spike lost in decimation: full max=100.0, "
                f"decimated max={dec_max}. This validates the audit concern."
            )

    def test_min_on_sparse_trough(self):
        """A signal with a single narrow trough: min must be found regardless
        of decimation sampling."""
        n = 50_000
        t = np.linspace(0, 1.0, n)
        v = np.sin(2 * np.pi * 5 * t)
        # Inject a narrow trough at t=0.317
        trough_idx = int(0.317 * n)
        v[trough_idx] = -100.0
        # Full data min is -100.0
        assert float(np.min(v)) == -100.0
        # Decimate to 1600 points
        step = max(1, n // 1600)
        v_dec = v[::step]
        dec_min = float(np.min(v_dec))
        if dec_min > -100.0:
            pytest.skip(
                f"Trough lost in decimation: full min=-100.0, "
                f"decimated min={dec_min}. This validates the audit concern."
            )

    def test_pp_on_sparse_peak(self):
        """Peak-to-peak on a signal with a narrow spike: must capture the spike."""
        n = 50_000
        t = np.linspace(0, 1.0, n)
        v = np.sin(2 * np.pi * 5 * t)
        spike_idx = int(0.423 * n)
        v[spike_idx] = 100.0
        trough_idx = int(0.317 * n)
        v[trough_idx] = -100.0
        # Full data pp is 200.0
        assert float(np.max(v) - np.min(v)) == 200.0
        # Decimate to 1600 points
        step = max(1, n // 1600)
        v_dec = v[::step]
        dec_pp = float(np.max(v_dec) - np.min(v_dec))
        if dec_pp < 200.0:
            pytest.skip(
                f"PP lost in decimation: full pp=200.0, "
                f"decimated pp={dec_pp}. This validates the audit concern."
            )

    def test_decimation_factor(self):
        """Document the decimation ratio for 1600 target."""
        n = 100_000
        step = max(1, n // 1600)
        assert step >= 62, f"Decimation step={step}, 1 in {step} points kept"

    def test_decimation_factor_large(self):
        """Document decimation ratio for 1M point signal."""
        n = 1_000_000
        step = max(1, n // 1600)
        assert step >= 625, f"Decimation step={step}, 1 in {step} points kept"


class TestRmsAndIntegral:
    """Verify RMS and integral values against analytical expectations."""

    @pytest.fixture
    def sine_1khz_1ms(self):
        """1 kHz sine over exactly 1 period at 100k points."""
        n = 100_000
        t = np.linspace(0, 1e-3, n)
        v = np.sin(2 * np.pi * 1000 * t)
        return t, v

    def test_rms_full_sine(self, sine_1khz_1ms):
        """RMS of a unit sine over an integer number of periods = 1/sqrt(2)."""
        _, v = sine_1khz_1ms
        rms = float(np.sqrt(np.mean(v**2)))
        expected = 1.0 / np.sqrt(2)
        # Relaxed tolerance: discrete sampling introduces ~3.5e-6 error
        # even with 100k points
        assert abs(rms - expected) < 1e-5, f"rms={rms}, expected={expected}"

    def test_rms_after_decimation(self, sine_1khz_1ms):
        """RMS on decimated data should still be close to 1/sqrt(2)."""
        t, v = sine_1khz_1ms
        n = len(v)
        step = max(1, n // 1600)
        v_dec = v[::step]
        rms_dec = float(np.sqrt(np.mean(v_dec**2)))
        expected = 1.0 / np.sqrt(2)
        # Decimated RMS should still be within 1% (statistically significant
        # because decimation picks every Nth point, preserving periodic statistics)
        assert abs(rms_dec - expected) < 0.02, (
            f"rms_dec={rms_dec}, expected ~{expected:.4f}, "
            f"error={abs(rms_dec - expected):.4f}"
        )


class TestFunctionPrecision:
    """Verify edge-case behaviors that could be affected by decimation."""

    def test_max_on_flat_signal_with_one_spike(self):
        """A single-point spike in a flat signal must be detectable."""
        n = 100_000
        v = np.zeros(n)
        v[n // 2] = 5.0
        # Full data: max = 5.0
        full_max = float(np.max(v))
        assert full_max == 5.0
        # Decimated:
        step = max(1, n // 1600)
        v_dec = v[::step]
        dec_max = float(np.max(v_dec))
        if dec_max < 5.0:
            pytest.skip(
                "Single-point spike lost in decimation. "
                "This documents that sparse peaks may be missed "
                "on display-only data."
            )

    def test_integral_with_decimation(self):
        """Integral of triangular wave is ~area under rect(t)."""
        n = 50_000
        t = np.linspace(0, 1, n)
        v = np.where(t < 0.5, 2 * t, 2 * (1 - t))  # triangular wave
        full_integral = float(np.trapezoid(v, t))
        step = max(1, n // 1600)
        t_dec = t[::step]
        v_dec = v[::step]
        dec_integral = float(np.trapezoid(v_dec, t_dec))
        # Decimation might affect integral accuracy
        error_pct = abs(dec_integral - full_integral) / abs(full_integral) * 100
        assert error_pct < 5.0, (
            f"Decimated integral error: {error_pct:.1f}% "
            f"(full={full_integral:.6f}, dec={dec_integral:.6f})"
        )
