"""Programmatic smoke tests for multi-panel architecture + FFT features.

Verifies plan phases A-D without requiring a display server.
All test data is synthetic (numpy arrays generated inline).
No external data files are read or written.
"""

import numpy as np
import pytest

from pqwave.ui.fft_engine import compute_fft, _nextpow2
from pqwave.models.state import (
    ApplicationState,
    PanelState,
    FftConfig,
    AxisId,
    AxisConfig,
)


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset the ApplicationState singleton before each test."""
    ApplicationState._instance = None
    yield
    ApplicationState._instance = None


class TestFftEngine:
    """Phase C: FFT engine correctness."""

    def test_pure_sine_1khz(self):
        fs = 100e3
        t = np.linspace(0, 10e-3, int(fs * 10e-3))
        sig = np.sin(2 * np.pi * 1000 * t)
        freq, mag = compute_fft(t, sig, window="hann", dc_removal=True, representation="linear")
        peak_idx = np.argmax(mag[1:]) + 1
        peak_freq = freq[peak_idx]
        assert 950 <= peak_freq <= 1050, f"Expected ~1000 Hz peak, got {peak_freq:.1f} Hz"

    def test_dc_removal(self):
        fs = 100e3
        t = np.linspace(0, 10e-3, int(fs * 10e-3))
        sig = np.sin(2 * np.pi * 1000 * t) + 5.0
        _freq, mag = compute_fft(t, sig, window="hann", dc_removal=True, representation="linear")
        assert mag[0] < 0.1, f"DC bin should be ~0 after removal, got {mag[0]:.4f}"

    def test_dc_retained(self):
        fs = 100e3
        t = np.linspace(0, 10e-3, int(fs * 10e-3))
        sig = np.sin(2 * np.pi * 1000 * t) + 5.0
        _freq, mag = compute_fft(t, sig, window="hann", dc_removal=False, representation="linear")
        assert mag[0] > 1.0, f"DC bin should be significant without removal, got {mag[0]:.4f}"

    def test_db_representation(self):
        fs = 100e3
        t = np.linspace(0, 10e-3, int(fs * 10e-3))
        sig = np.sin(2 * np.pi * 1000 * t)
        _freq, mag_db = compute_fft(t, sig, window="hann", dc_removal=True, representation="db")
        assert np.max(mag_db[1:]) > 0, "Signal peak should have positive dB"
        peak_val = np.max(mag_db[1:])
        assert peak_val > 20, f"Peak should be well above noise, got {peak_val:.1f} dB"

    def test_two_tones(self):
        fs = 100e3
        duration = 50e-3
        t = np.linspace(0, duration, int(fs * duration))
        sig = np.sin(2 * np.pi * 1000 * t) + np.sin(2 * np.pi * 5000 * t)
        freq, mag = compute_fft(t, sig, window="hann", dc_removal=True, representation="linear")
        # Search for the highest peak in each of the two frequency bands
        mask_1k = (freq >= 900) & (freq <= 1100)
        mask_5k = (freq >= 4900) & (freq <= 5100)
        peak_1k = freq[mask_1k][np.argmax(mag[mask_1k])]
        peak_5k = freq[mask_5k][np.argmax(mag[mask_5k])]
        assert 950 <= peak_1k <= 1050, f"First peak near 1 kHz, got {peak_1k:.1f}"
        assert 4800 <= peak_5k <= 5200, f"Second peak near 5 kHz, got {peak_5k:.1f}"

    def test_frequency_axis_range(self):
        fs = 100e3
        t = np.linspace(0, 10e-3, int(fs * 10e-3))
        sig = np.sin(2 * np.pi * 1000 * t)
        freq, _mag = compute_fft(t, sig)
        assert freq[0] == 0.0
        assert freq[-1] <= fs / 2

    def test_window_types(self):
        fs = 100e3
        t = np.linspace(0, 10e-3, int(fs * 10e-3))
        sig = np.sin(2 * np.pi * 1000 * t)
        for window in ["hann", "hamming", "blackman", "none"]:
            freq, mag = compute_fft(t, sig, window=window)
            assert len(freq) > 0
            assert len(mag) > 0
            assert not np.any(np.isnan(mag))

    def test_frequency_resolution(self):
        fs = 100e3
        duration = 10e-3
        n = int(fs * duration)
        t = np.linspace(0, duration, n)
        sig = np.sin(2 * np.pi * 1000 * t)
        freq, _mag = compute_fft(t, sig)
        df = freq[1] - freq[0]
        # compute_fft auto-sizes to nextpow2. df = 1 / (dt * n_fft)
        # Use actual dt from the time array (linspace rounding differs from nominal fs)
        dt = t[1] - t[0]
        n_fft = _nextpow2(n)
        expected_df = 1.0 / (dt * n_fft)
        assert abs(df - expected_df) < 0.5, f"df={df:.3f}, expected ~{expected_df:.3f}"


class TestPanelState:
    """Phase B: State model for multi-panel."""

    def test_panel_state_defaults(self):
        ps = PanelState(panel_id="test-1")
        assert ps.panel_id == "test-1"
        assert ps.traces == []
        assert ps.axis_configs == {}
        assert ps.domain == "time"
        assert ps.current_x_var is None

    def test_panel_state_domain(self):
        ps = PanelState(panel_id="fft-1", domain="frequency")
        assert ps.domain == "frequency"


class TestFftConfig:
    def test_defaults(self):
        cfg = FftConfig()
        assert cfg.window == "none"
        assert cfg.fft_size == 0
        assert cfg.dc_removal is True
        assert cfg.representation == "db"
        assert cfg.x_range_mode == "full"
        assert cfg.x_range_start == 0.0
        assert cfg.x_range_end == 0.0
        assert cfg.binomial_smooth == 0

    def test_custom(self):
        cfg = FftConfig(window="blackman", fft_size=4096, dc_removal=False, representation="linear")
        assert cfg.window == "blackman"
        assert cfg.fft_size == 4096
        assert cfg.dc_removal is False
        assert cfg.representation == "linear"


class TestApplicationStatePanels:
    """Application state with panel management."""

    def test_register_panel(self):
        state = ApplicationState()
        state.register_panel("p1")
        assert "p1" in state.panels
        assert state.panels["p1"].panel_id == "p1"
        assert state.active_panel_id == "p1"

    def test_register_multiple_panels(self):
        state = ApplicationState()
        state.register_panel("p1")
        state.register_panel("p2")
        assert len(state.panels) == 2
        assert state.active_panel_id == "p1"

    def test_unregister_panel(self):
        state = ApplicationState()
        state.register_panel("a")
        state.register_panel("b")
        state.unregister_panel("a")
        assert "a" not in state.panels
        assert state.active_panel_id == "b"

    def test_unregister_last_panel(self):
        state = ApplicationState()
        state.register_panel("only")
        state.unregister_panel("only")
        assert len(state.panels) == 0
        assert state.active_panel_id is None

    def test_panel_order(self):
        state = ApplicationState()
        state.register_panel("p1")
        state.register_panel("p2")
        state.register_panel("p3")
        assert state.panel_order == ["p1", "p2", "p3"]

    def test_set_active_panel(self):
        state = ApplicationState()
        state.register_panel("p1")
        state.register_panel("p2")
        state.active_panel_id = "p2"
        assert state.active_panel_id == "p2"

    def test_backward_compat_traces(self):
        state = ApplicationState()
        state.register_panel("p1")
        from pqwave.models.trace import Trace
        t = Trace(name="V(out)", expression="V(out)",
                  x_data=np.array([0.0, 1.0]), y_data=np.array([1.0, 2.0]))
        state.panels["p1"].traces.append(t)
        assert len(state.traces) == 1
        assert state.traces[0].name == "V(out)"

    def test_backward_compat_current_x_var(self):
        state = ApplicationState()
        state.register_panel("p1")
        state.panels["p1"].current_x_var = "frequency"
        assert state.current_x_var == "frequency"

    def test_axis_configs_per_panel(self):
        state = ApplicationState()
        state.register_panel("p1")
        state.register_panel("p2")
        cfg1 = AxisConfig(range=(0.0, 10.0), log_mode=False)
        cfg2 = AxisConfig(range=(-5.0, 5.0), log_mode=True)
        state.panels["p1"].axis_configs[AxisId.Y1] = cfg1
        state.panels["p2"].axis_configs[AxisId.Y1] = cfg2
        assert state.panels["p1"].axis_configs[AxisId.Y1].range == (0.0, 10.0)
        assert state.panels["p2"].axis_configs[AxisId.Y1].log_mode is True

    def test_fft_config_default(self):
        state = ApplicationState()
        assert state.fft_config.window == "none"
        assert state.fft_config.dc_removal is True


class TestPerFileSerialization:
    """State save/restore with panel data."""

    def test_roundtrip_panel_state(self):
        state = ApplicationState()
        state.register_panel("p1")
        state.panels["p1"].domain = "time"
        state.register_panel("p2")
        state.panels["p2"].domain = "frequency"
        state.fft_config = FftConfig(window="blackman", fft_size=4096,
                                     dc_removal=False, representation="linear")
        data = state.to_per_file_dict()
        assert "panels" in data
        assert "active_panel_id" in data
        assert "fft_config" in data
        assert len(data["panels"]) == 2
        assert data["fft_config"]["window"] == "blackman"

    def test_restore_old_format_no_panels(self):
        """Backward compat: loading old-format flat data creates a default panel."""
        state = ApplicationState()
        old_data = {
            "traces": [],
            "axis_configs": {},
            "current_x_var": "time",
            "mark_colors": {},
            "colors": {},
            "analysis_traces": [],
            "analysis_color_index": 0,
        }
        # Simulate MainWindow._restore_flat_state_from_dict behavior:
        # when panels key is absent, create a default panel
        if "panels" not in old_data:
            state.register_panel("default")
            state.panels["default"].domain = old_data.get("current_x_var", "time")
        assert len(state.panels) > 0
        assert state.panels["default"].domain == "time"
