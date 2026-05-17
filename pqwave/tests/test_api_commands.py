#!/usr/bin/env python3
"""Comprehensive test of all registered API commands via the REPL code path.

Tests every command in the SessionAPI command registry through
ReplExecutor.run_sync(), covering success round-trips and error handling.

Usage:
    cd /home/wing/Apps/pqwave.git
    source venv/bin/activate
    pytest pqwave/tests/test_api_commands.py -v
"""

import sys
import os
import tempfile
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

# Project root for test data file resolution
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from pqwave.session.api import get_command_registry
from pqwave.models.state import ApplicationState
from pqwave.ui.repl import ReplExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_state():
    """Reset the ApplicationState singleton to a clean slate."""
    if ApplicationState._instance is not None:
        ApplicationState._instance._initialize()


def _fresh_executor():
    """Return a ReplExecutor with fresh ApplicationState."""
    _reset_state()
    return ReplExecutor()


def _load(executor, relpath):
    """Load a test data file through the REPL. Returns the result dict."""
    return executor.run_sync(f"load('{relpath}')")


def _add(executor, expr, axis="Y1"):
    """Add a trace through the REPL. Returns the result dict."""
    return executor.run_sync(f"add('{expr}', axis='{axis}')")




# ---------------------------------------------------------------------------
# COMMAND_SPECS — auto-discovery gate
# ---------------------------------------------------------------------------

COMMAND_SPECS = {
    # File I/O & Info
    "load":          {"needs": "none",     "valid_call": "load('pqwave/tests/bridge.raw')"},
    "signals":       {"needs": "none",     "valid_call": "signals()"},
    "info":          {"needs": "none",     "valid_call": "info()"},

    # Trace CRUD
    "add":           {"needs": "file_loaded", "valid_call": "add('v(ac_p)')"},
    "show":          {"needs": "trace_added", "valid_call": "show('v(ac_p)')"},
    "hide":          {"needs": "trace_added", "valid_call": "hide('v(ac_p)')"},
    "remove":        {"needs": "trace_added", "valid_call": "remove(0)"},
    "add_all":       {"needs": "file_loaded", "valid_call": "add_all()"},
    "show_all":      {"needs": "trace_added", "valid_call": "show_all()"},
    "hide_all":      {"needs": "trace_added", "valid_call": "hide_all()"},
    "remove_all":    {"needs": "trace_added", "valid_call": "remove_all()"},
    "show_matching": {"needs": "file_loaded", "valid_call": "show_matching('v(*)')"},

    # Measurements
    "measure":        {"needs": "trace_added", "valid_call": "measure('avg(v(ac_p))')"},
    "measure_script": {"needs": "trace_added", "valid_call": "measure_script('avg(v(ac_p))')"},

    # Analysis
    "fft":        {"needs": "trace_added", "valid_call": "fft('v(ac_p)')"},
    "power":      {"needs": "two_traces",  "valid_call": "power('v(ac_p)', 'v(r1)')"},
    "eye":        {"needs": "file_loaded", "valid_call": "eye('V(eye)')"},
    "fft_config": {"needs": "none",        "valid_call": "fft_config(window='hann')"},

    # View Control
    "range":         {"needs": "none", "valid_call": "range(xmin=0, xmax=0.001)"},
    "log_x":         {"needs": "none", "valid_call": "log_x(True)"},
    "log_y":         {"needs": "none", "valid_call": "log_y(True)"},
    "grid":          {"needs": "none", "valid_call": "grid(True)"},
    "legend":        {"needs": "none", "valid_call": "legend(True)"},
    "cross_hair":    {"needs": "none", "valid_call": "cross_hair(True)"},
    "zoom_fit":      {"needs": "none", "valid_call": "zoom_fit()"},
    "auto_range_x":  {"needs": "none", "valid_call": "auto_range_x()"},
    "auto_range_y":  {"needs": "none", "valid_call": "auto_range_y()"},
    "title":         {"needs": "none", "valid_call": "title('test')"},

    # Cursors
    "cursor_xa":         {"needs": "none", "valid_call": "cursor_xa('1m')"},
    "cursor_xb":         {"needs": "none", "valid_call": "cursor_xb('2m')"},
    "cursor_ya":         {"needs": "none", "valid_call": "cursor_ya('1')"},
    "cursor_yb":         {"needs": "none", "valid_call": "cursor_yb('2')"},
    "cursor_delta":      {"needs": "none", "valid_call": "cursor_delta()"},
    "cursor":            {"needs": "none", "valid_call": "cursor()"},
    "cursor_xa_visible": {"needs": "none", "valid_call": "cursor_xa_visible(True)"},
    "cursor_xb_visible": {"needs": "none", "valid_call": "cursor_xb_visible(True)"},
    "cursor_ya_visible": {"needs": "none", "valid_call": "cursor_ya_visible(True)"},
    "cursor_yb_visible": {"needs": "none", "valid_call": "cursor_yb_visible(True)"},

    # Export
    "export_csv":   {"needs": "file_loaded", "valid_call": "export_csv('/tmp/test_api.csv')"},
    "export_plot":  {"needs": "none",         "valid_call": "export_plot('/tmp/test_api.png')"},

    # Bus / Digital
    "bus":      {"needs": "file_loaded", "valid_call": "bus(['v(ac_p)','v(ac_n)'], 'test_bus')"},
    "expand":   {"needs": "none",        "valid_call": "expand('test_bus')"},
    "collapse": {"needs": "none",        "valid_call": "collapse('test_bus')"},
    "digital":  {"needs": "none",        "valid_call": "digital('v(ac_p)', True)"},

    # Panel / Zoom / Misc
    "split_horizontal": {"needs": "none", "valid_call": "split_horizontal()"},
    "split_vertical":   {"needs": "none", "valid_call": "split_vertical()"},
    "close_panel":      {"needs": "none", "valid_call": "close_panel()"},
    "zoom_in":          {"needs": "none", "valid_call": "zoom_in()"},
    "zoom_out":         {"needs": "none", "valid_call": "zoom_out()"},
    "theme":            {"needs": "none", "valid_call": "theme('dark')"},
    "reload":           {"needs": "none", "valid_call": "reload()"},
    "change_x":         {"needs": "file_loaded", "valid_call": "change_x('time')"},
    "set_trace":        {"needs": "trace_added", "valid_call": "set_trace('v(ac_p)', alias='foo')"},

    # View Templates
    "save_template":  {"needs": "none", "valid_call": "save_template('test_template')"},
    "load_template":  {"needs": "none", "valid_call": "load_template('test_template')"},
    "list_templates": {"needs": "none", "valid_call": "list_templates()"},
}


class TestCommandCoverage:
    """Verify every registered command has a COMMAND_SPECS entry."""

    def test_all_commands_have_spec(self):
        registry = get_command_registry()
        missing = []
        for name in sorted(registry):
            if name not in COMMAND_SPECS:
                missing.append(name)
        if missing:
            msg = (
                f"{len(missing)} command(s) have no test coverage. "
                f"Add them to COMMAND_SPECS:\n  "
                + "\n  ".join(missing)
            )
            pytest.fail(msg)

    def test_no_stale_spec_entries(self):
        """COMMAND_SPECS should not reference commands that don't exist."""
        registry = get_command_registry()
        stale = []
        for name in COMMAND_SPECS:
            if name not in registry:
                stale.append(name)
        if stale:
            pytest.fail(
                f"COMMAND_SPECS has {len(stale)} stale entries not in registry: {stale}"
            )


# ======================================================================
# Task 2: File I/O & Info
# ======================================================================


class TestFileIOAndInfo:
    """load, signals, info — and session.help() (not an @api_command but
    available via the 'session' variable in REPL namespace)."""

    # -- load --

    def test_load_bridge_returns_file_metadata(self):
        e = _fresh_executor()
        r = e.run_sync("load('pqwave/tests/bridge.raw')")
        assert r["ok"] is True
        info = r["result"]
        assert info["file_type"] == "raw"
        assert info["n_points"] == 4015
        assert info["n_variables"] == 5
        assert "v(ac_p)" in info["signals"]

    def test_load_cdg_returns_complex_derived_signals(self):
        e = _fresh_executor()
        r = e.run_sync("load('pqwave/tests/cdg.raw')")
        assert r["ok"] is True
        info = r["result"]
        assert info["file_type"] == "raw"
        assert "mag(ac_data)" in info["signals"]
        assert "real(ac_data)" in info["signals"]

    def test_load_mixed_signal_raw(self):
        e = _fresh_executor()
        r = e.run_sync("load('tests/mixed_signal.raw')")
        assert r["ok"] is True
        assert r["result"]["file_type"] == "raw"
        assert "v(v_q1)" in r["result"]["signals"]

    def test_load_eyediagram_demo(self):
        e = _fresh_executor()
        r = e.run_sync("load('tests/eyediagram_demo.raw')")
        assert r["ok"] is True
        assert "V(eye)" in r["result"]["signals"]

    def test_load_nonexistent_file_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("load('/nonexistent/path.raw')")
        assert r["ok"] is False
        assert "error" in r

    def test_load_vcd_returns_file_metadata(self):
        e = _fresh_executor()
        r = e.run_sync("load('tests/mixed_signal.vcd')")
        assert r["ok"] is True
        info = r["result"]
        assert info["file_type"] == "vcd"
        assert info["n_variables"] >= 5
        assert "dig_clk" in info["signals"]
        assert "q1" in info["signals"]

    def test_load_json_project_returns_unsupported_error(self):
        e = _fresh_executor()
        r = e.run_sync("load('tests/eyediagram_demo.json')")
        assert r["ok"] is True
        assert "error" in r["result"]

    # -- signals --

    def test_signals_empty_without_file(self):
        e = _fresh_executor()
        r = e.run_sync("signals()")
        assert r["ok"] is True
        assert r["result"] == []

    def test_signals_after_load_returns_names(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("signals()")
        assert r["ok"] is True
        assert isinstance(r["result"], list)
        assert "v(ac_p)" in r["result"]
        assert "time" in r["result"]

    # -- info --

    def test_info_without_file_shows_zero_counts(self):
        e = _fresh_executor()
        r = e.run_sync("info()")
        assert r["ok"] is True
        assert r["result"]["n_points"] == 0
        assert r["result"]["n_traces"] == 0
        assert r["result"]["datasets"] == 0

    def test_info_after_load_reflects_dataset(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("info()")
        assert r["ok"] is True
        assert r["result"]["datasets"] == 1
        assert r["result"]["n_points"] == 4015
        assert r["result"]["n_variables"] == 5
        assert r["result"]["active_panel"] is not None

    def test_info_trace_count_updates_after_add(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 1
        _add(e, "v(ac_n)")
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 2

    # -- session.help() (not an @api_command, accessed via REPL 'session' var) --

    def test_session_help_lists_commands(self):
        e = _fresh_executor()
        r = e.run_sync("session.help()")
        assert r["ok"] is True
        help_text = r["result"]
        assert "add(" in help_text
        assert "signals()" in help_text

    def test_session_help_specific_command(self):
        e = _fresh_executor()
        r = e.run_sync("session.help('add')")
        assert r["ok"] is True
        assert "Add a trace" in r["result"]


# ======================================================================
# Task 3: Trace CRUD
# ======================================================================


class TestTraceCRUD:
    """add, show, hide, remove, add_all, show_all, hide_all, remove_all, show_matching."""

    # -- add --

    def test_add_single_trace_returns_name(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = _add(e, "v(ac_p)")
        assert r["ok"] is True
        assert r["result"] == "v(ac_p)"

    def test_add_complex_signal_auto_wraps_mag(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/cdg.raw")
        r = _add(e, "ac_data")
        assert r["ok"] is True
        # Complex signals auto-wrap with mag(); returns the wrapped expression
        assert "mag(ac_data)" == r["result"]

    def test_add_list_of_signals(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("add(['v(ac_p)', 'v(ac_n)'])")
        assert r["ok"] is True
        assert isinstance(r["result"], list)
        assert len(r["result"]) == 2

    def test_add_nonexistent_signal_returns_error(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("add('nonexistent_signal')")
        assert r["ok"] is False
        assert "not found" in r["error"].lower()

    def test_add_without_file_loaded_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("add('vout')")
        assert r["ok"] is False

    def test_add_with_missing_args_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("add()")
        assert r["ok"] is False

    # -- show / hide / remove round-trip --

    def test_show_hide_remove_round_trip(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("hide('v(ac_p)')")
        assert r["ok"] is True
        r = e.run_sync("show('v(ac_p)')")
        assert r["ok"] is True
        r = e.run_sync("remove('v(ac_p)')")
        assert r["ok"] is True
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 0

    def test_remove_by_index(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        _add(e, "v(ac_n)")
        r = e.run_sync("remove(0)")
        assert r["ok"] is True
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 1

    def test_show_nonexistent_trace_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("show('nonexistent')")
        assert r["ok"] is False

    def test_hide_nonexistent_trace_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("hide('nonexistent')")
        assert r["ok"] is False

    def test_remove_nonexistent_trace_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("remove('nonexistent')")
        assert r["ok"] is False

    # -- add_all --

    def test_add_all_plots_all_non_axis_signals(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("add_all()")
        assert r["ok"] is True
        shown = r["result"]["shown"]
        assert "v(ac_p)" in shown
        assert "v(ac_n)" in shown
        assert "v(r1)" in shown
        assert "v(r2)" in shown
        assert "time" not in shown
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 4

    # -- show_all / hide_all --

    def test_show_all_and_hide_all(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        _add(e, "v(ac_n)")
        r = e.run_sync("hide_all()")
        assert r["ok"] is True
        r = e.run_sync("show_all()")
        assert r["ok"] is True

    # -- remove_all --

    def test_remove_all_clears_all_traces(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        _add(e, "v(ac_n)")
        r = e.run_sync("remove_all()")
        assert r["ok"] is True
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 0

    # -- show_matching --

    def test_show_matching_glob_pattern(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("show_matching('v(ac*)')")
        assert r["ok"] is True
        assert "v(ac_p)" in r["result"]["shown"]
        assert "v(ac_n)" in r["result"]["shown"]

    def test_show_matching_no_match_returns_empty(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("show_matching('zzz*')")
        assert r["ok"] is True
        assert r["result"]["shown"] == []

    def test_range_expansion_no_matching_signals_raises(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("add('q1~q4')")
        assert r["ok"] is False
        assert "No signals match range" in r.get("error", "")

    def test_glob_in_add_delegates_to_show_matching(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("add('v(*)')")
        assert r["ok"] is True
        shown = r["result"] if isinstance(r["result"], list) else r["result"]["shown"]
        assert len(shown) >= 4


# ======================================================================
# Task 4: Measurements
# ======================================================================


class TestMeasurements:
    """measure, measure_script."""

    def test_measure_avg_returns_float(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure('avg(v(ac_p))')")
        assert r["ok"] is True
        assert isinstance(r["result"]["avg(v(ac_p))"], float)

    def test_measure_rms(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure('rms(v(ac_p))')")
        assert r["ok"] is True
        key = list(r["result"].keys())[0]
        assert isinstance(r["result"][key], float)

    def test_measure_pp(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure('pp(v(ac_p))')")
        assert r["ok"] is True

    def test_measure_min_max(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure('min(v(ac_p))')")
        assert r["ok"] is True
        r = e.run_sync("measure('max(v(ac_p))')")
        assert r["ok"] is True

    def test_measure_rise_time(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure('rise_time(v(ac_p))')")
        assert r["ok"] is True

    def test_measure_with_from_to_kwargs(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure('avg(v(ac_p))', from_='0', to='0.001')")
        assert r["ok"] is True

    def test_measure_missing_signal_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("measure('avg(nonexistent)')")
        assert r["ok"] is False

    def test_measure_malformed_expression_returns_error(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("measure('not_a_valid_expression')")
        assert r["ok"] is False

    # -- measure_script --

    def test_measure_script_single_line(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        code = "measure_script('avg(v(ac_p))')"
        r = e.run_sync(code)
        assert r["ok"] is True
        assert isinstance(r["result"], dict)

    def test_measure_script_with_label_syntax(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("measure_script('avg_vout avg(v(ac_p))')")
        assert r["ok"] is True
        assert isinstance(r["result"], dict)


# ======================================================================
# Task 5: Analysis
# ======================================================================


class TestAnalysis:
    """fft, power, eye, fft_config."""

    # -- fft --

    def test_fft_returns_freq_and_mag(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("fft('v(ac_p)')")
        assert r["ok"] is True
        assert "freq" in r["result"]
        assert "mag" in r["result"]
        assert len(r["result"]["freq"]) > 0
        assert len(r["result"]["mag"]) > 0

    def test_fft_missing_signal_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("fft('nonexistent')")
        assert r["ok"] is False

    # -- power --

    def test_power_returns_power_dict(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        _add(e, "v(r1)")
        r = e.run_sync("power('v(ac_p)', 'v(r1)')")
        assert r["ok"] is True
        result = r["result"]
        assert "avg_power" in result
        assert "p_inst" in result
        assert isinstance(result["avg_power"], float)

    def test_power_missing_signal_returns_error(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("power('v(ac_p)', 'nonexistent')")
        assert r["ok"] is False

    # -- eye --

    def test_eye_returns_signal_and_period(self):
        e = _fresh_executor()
        _load(e, "tests/eyediagram_demo.raw")
        r = e.run_sync("eye('V(eye)')")
        assert r["ok"] is True
        assert r["result"]["eye"] == "V(eye)"

    def test_eye_with_period(self):
        e = _fresh_executor()
        _load(e, "tests/eyediagram_demo.raw")
        r = e.run_sync("eye('V(eye)', period='100n')")
        assert r["ok"] is True

    def test_eye_headless_delegates_returns_ok(self):
        """eye() in headless mode delegates to callback, no signal validation."""
        e = _fresh_executor()
        r = e.run_sync("eye('nonexistent')")
        # Headless: delegates to _on_mutation, returns ok with params
        assert r["ok"] is True

    # -- fft_config --

    def test_fft_config_get_defaults(self):
        e = _fresh_executor()
        r = e.run_sync("fft_config()")
        assert r["ok"] is True
        assert "window" in r["result"]
        assert "representation" in r["result"]

    def test_fft_config_set_window(self):
        e = _fresh_executor()
        r = e.run_sync("fft_config(window='hamming')")
        assert r["ok"] is True
        assert r["result"]["window"] == "hamming"

    def test_fft_config_set_fft_size(self):
        e = _fresh_executor()
        r = e.run_sync("fft_config(fft_size=4096)")
        assert r["ok"] is True
        assert r["result"]["fft_size"] == 4096

    def test_fft_config_set_representation(self):
        e = _fresh_executor()
        r = e.run_sync("fft_config(representation='linear')")
        assert r["ok"] is True
        assert r["result"]["representation"] == "linear"


# ======================================================================
# Task 6: View Control
# ======================================================================


class TestViewControl:
    """range, log_x, log_y, grid, legend, cross_hair, title, zoom_fit,
    auto_range_x, auto_range_y."""

    def test_range_sets_view_bounds(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")  # range needs a panel
        r = e.run_sync("range(xmin=0, xmax=0.001)")
        assert r["ok"] is True
        assert r["result"]["xmin"] == 0
        assert r["result"]["xmax"] == 0.001

    def test_range_partial_args(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")  # range needs a panel
        r = e.run_sync("range(ymin=-1, ymax=5)")
        assert r["ok"] is True
        assert r["result"]["ymin"] == -1
        assert r["result"]["ymax"] == 5

    def test_log_x_toggle(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")  # log_x needs a panel
        r = e.run_sync("log_x(True)")
        assert r["ok"] is True
        assert r["result"]["log_x"] is True

    def test_log_y_toggle(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")  # log_y needs a panel
        r = e.run_sync("log_y(True)")
        assert r["ok"] is True
        assert r["result"]["log_y"] is True

    def test_grid_toggle(self):
        e = _fresh_executor()
        r = e.run_sync("grid(True)")
        assert r["ok"] is True
        assert r["result"]["grid"] is True

    def test_legend_toggle(self):
        e = _fresh_executor()
        r = e.run_sync("legend(True)")
        assert r["ok"] is True
        assert r["result"]["legend"] is True

    def test_cross_hair_toggle(self):
        e = _fresh_executor()
        r = e.run_sync("cross_hair(True)")
        assert r["ok"] is True
        assert r["result"]["cross_hair"] is True

    def test_title_set(self):
        e = _fresh_executor()
        r = e.run_sync("title('My Plot')")
        assert r["ok"] is True
        assert r["result"]["title"] == "My Plot"

    def test_zoom_fit_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("zoom_fit()")
        assert r["ok"] is True

    def test_auto_range_x_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("auto_range_x()")
        assert r["ok"] is True

    def test_auto_range_y_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("auto_range_y()")
        assert r["ok"] is True

    def test_view_commands_work_without_file_loaded(self):
        """View control commands should work without any file loaded."""
        e = _fresh_executor()
        for cmd in ["grid(True)", "legend(False)", "cross_hair(True)",
                     "title('test')", "zoom_fit()", "auto_range_x()"]:
            r = e.run_sync(cmd)
            assert r["ok"] is True, f"{cmd} failed: {r}"


# ======================================================================
# Task 7: Cursors
# ======================================================================


class TestCursors:
    """cursor_xa, cursor_xb, cursor_ya, cursor_yb, cursor, cursor_delta,
    cursor_xa_visible, cursor_xb_visible, cursor_ya_visible, cursor_yb_visible."""

    def test_cursor_xa_set_and_get(self):
        e = _fresh_executor()
        r = e.run_sync("cursor_xa('1m')")
        assert r["ok"] is True
        assert r["result"]["cursor_xa"] == "1m"

    def test_cursor_xb_set(self):
        e = _fresh_executor()
        r = e.run_sync("cursor_xb('2m')")
        assert r["ok"] is True
        assert r["result"]["cursor_xb"] == "2m"

    def test_cursor_ya_set(self):
        e = _fresh_executor()
        r = e.run_sync("cursor_ya('1')")
        assert r["ok"] is True
        assert r["result"]["cursor_ya"] == "1"

    def test_cursor_yb_set(self):
        e = _fresh_executor()
        r = e.run_sync("cursor_yb('2')")
        assert r["ok"] is True
        assert r["result"]["cursor_yb"] == "2"

    def test_cursor_delta_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("cursor_delta()")
        assert r["ok"] is True

    def test_cursor_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("cursor()")
        assert r["ok"] is True

    def test_cursor_visibility_toggles(self):
        e = _fresh_executor()
        for cmd in ["cursor_xa_visible(True)", "cursor_xb_visible(False)",
                     "cursor_ya_visible(True)", "cursor_yb_visible(False)"]:
            r = e.run_sync(cmd)
            assert r["ok"] is True, f"{cmd} failed: {r}"

    def test_cursor_commands_work_without_file_loaded(self):
        e = _fresh_executor()
        r = e.run_sync("cursor_xa('0.5')")
        assert r["ok"] is True


# ======================================================================
# Task 8: Export
# ======================================================================


class TestExport:
    """export_csv, export_plot."""

    def test_export_csv_writes_file(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        tmpdir = tempfile.gettempdir()
        csv_path = os.path.join(tmpdir, "test_api_export.csv")
        r = e.run_sync(f"export_csv('{csv_path}')")
        assert r["ok"] is True
        assert r["result"]["signals_exported"] >= 1
        assert os.path.exists(csv_path)
        os.remove(csv_path)

    def test_export_csv_no_traces_returns_zero(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        tmpdir = tempfile.gettempdir()
        csv_path = os.path.join(tmpdir, "test_api_empty.csv")
        r = e.run_sync(f"export_csv('{csv_path}')")
        assert r["ok"] is True
        assert r["result"]["signals_exported"] == 0
        if os.path.exists(csv_path):
            os.remove(csv_path)

    def test_export_csv_with_specific_signals(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        _add(e, "v(ac_n)")
        tmpdir = tempfile.gettempdir()
        csv_path = os.path.join(tmpdir, "test_api_specific.csv")
        r = e.run_sync(f"export_csv('{csv_path}', signals=['v(ac_p)'])")
        assert r["ok"] is True
        assert r["result"]["signals_exported"] == 1
        if os.path.exists(csv_path):
            os.remove(csv_path)

    def test_export_plot_headless_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("export_plot('/tmp/test_api_plot.png')")
        assert r["ok"] is True


# ======================================================================
# Task 9: Bus / Digital
# ======================================================================


class TestBusDigital:
    """bus, expand, collapse, digital."""

    def test_bus_creates_group(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("bus(['v(ac_p)', 'v(ac_n)'], 'test_bus')")
        assert r["ok"] is True
        assert r["result"]["bus"] == "test_bus"
        assert r["result"]["signals"] == ["v(ac_p)", "v(ac_n)"]

    def test_bus_default_name(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("bus(['v(ac_p)'])")
        assert r["ok"] is True
        assert r["result"]["bus"] == "bus"

    def test_bus_adds_signals_as_traces(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        e.run_sync("bus(['v(ac_p)', 'v(ac_n)'], 'my_bus')")
        r = e.run_sync("info()")
        assert r["result"]["n_traces"] == 2

    def test_expand_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("expand('test_bus')")
        assert r["ok"] is True
        assert r["result"]["expand"] == "test_bus"

    def test_collapse_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("collapse('test_bus')")
        assert r["ok"] is True
        assert r["result"]["collapse"] == "test_bus"

    def test_digital_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("digital('v(ac_p)', True)")
        assert r["ok"] is True
        assert r["result"]["digital"] == "v(ac_p)"
        assert r["result"]["on"] is True


# ======================================================================
# Task 10: Panel / Zoom / Misc
# ======================================================================


class TestPanelZoomMisc:
    """split_horizontal, split_vertical, close_panel, zoom_in, zoom_out,
    theme, reload, change_x, set_trace."""

    def test_split_horizontal_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("split_horizontal()")
        assert r["ok"] is True

    def test_split_vertical_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("split_vertical()")
        assert r["ok"] is True

    def test_close_panel_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("close_panel()")
        assert r["ok"] is True

    def test_zoom_in_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("zoom_in()")
        assert r["ok"] is True

    def test_zoom_out_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("zoom_out()")
        assert r["ok"] is True

    def test_theme_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("theme('dark')")
        assert r["ok"] is True
        assert r["result"]["theme"] == "dark"

    def test_reload_returns_ok(self):
        e = _fresh_executor()
        r = e.run_sync("reload()")
        assert r["ok"] is True
        assert r["result"]["reload"] is True

    def test_change_x_sets_x_variable(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("change_x('time')")
        assert r["ok"] is True
        assert r["result"]["change_x"] == "time"

    def test_change_x_nonexistent_variable_returns_ok_delegates(self):
        e = _fresh_executor()
        r = e.run_sync("change_x('nonexistent')")
        assert r["ok"] is True

    def test_set_trace_sets_properties(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("set_trace('v(ac_p)', alias='my_alias', height=2.0)")
        assert r["ok"] is True
        assert r["result"]["name"] == "v(ac_p)"
        assert r["result"]["alias"] == "my_alias"
        assert r["result"]["height"] == 2.0

    def test_set_trace_nonexistent_returns_ok_delegates(self):
        e = _fresh_executor()
        r = e.run_sync("set_trace('nonexistent', alias='x')")
        assert r["ok"] is True


# ======================================================================
# Task 11: Cross-cutting error handling
# ======================================================================


class TestErrorHandling:
    """Cross-cutting error cases not covered in category-specific tests."""

    def test_no_file_loaded_all_commands_return_error(self):
        """Commands that need file data should return errors, not crash."""
        e = _fresh_executor()
        cmds = [
            "add('vout')",
            "measure('avg(v(1))')",
            "fft('vout')",
            "power('v1', 'v2')",
        ]
        for cmd in cmds:
            r = e.run_sync(cmd)
            assert r["ok"] is False, f"{cmd} should fail without file loaded"

    def test_wrong_argument_count_returns_error(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("add()")
        assert r["ok"] is False
        r = e.run_sync("measure()")
        assert r["ok"] is False

    def test_bad_syntax_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("add('v(1)'")
        assert r["ok"] is False

    def test_nonexistent_command_returns_error(self):
        e = _fresh_executor()
        r = e.run_sync("nonexistent_cmd()")
        assert r["ok"] is False

    def test_commands_never_raise_unhandled_exceptions(self):
        """Every command should return a dict, never crash the REPL."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        cases = [
            "load('')",
            "add('')",
            "add(123)",
            "remove(-1)",
            "range(xmin='not_a_number')",
            "log_x('not_bool')",
        ]
        for code in cases:
            r = e.run_sync(code)
            assert isinstance(r, dict), f"{code} should return dict, got {type(r)}"
            assert "ok" in r, f"{code} should have 'ok' key"
