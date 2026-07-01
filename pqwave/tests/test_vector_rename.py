#!/usr/bin/env python3
"""Tests for vector rename API and propagation.

Tests cover:
- Dataset.rename_variable() method (unit tests)
- rename_vector session API command (integration tests)
- Blocking rename when active traces reference the old name
- Error handling for nonexistent/duplicate names and bad indices
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pqwave.ui.repl import ReplExecutor
from pqwave.models.state import ApplicationState

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
# Dataset model unit tests (pure, no file I/O)
# ---------------------------------------------------------------------------

class TestRenameVariable:
    """Test Dataset.rename_variable method with minimal in-memory Dataset.

    These tests construct a Dataset using a FakeRawFile mock, so they do NOT
    depend on any real .raw file or ReplExecutor.  This keeps them as true
    unit tests that can run without test data on disk.
    """

    # ------------------------------------------------------------------
    # Helper: build a minimal in-memory Dataset
    # ------------------------------------------------------------------

    @staticmethod
    def _make_dataset():
        """Construct a minimal Dataset backed by a FakeRawFile (no I/O)."""
        import numpy as np
        from pqwave.models.dataset import Dataset

        class _FakeRawFile:
            pass

        rf = _FakeRawFile()
        rf.datasets = [{
            "title": "test",
            "date": "",
            "plotname": "Transient Analysis",
            "flags": "real",
            "variables": [
                {"index": 0, "name": "time", "type": "time"},
                {"index": 1, "name": "v(in)", "type": "voltage"},
                {"index": 2, "name": "v(out)", "type": "voltage"},
            ],
            "data": np.column_stack([
                np.linspace(0, 1e-6, 100),
                np.sin(np.linspace(0, np.pi, 100)),
                np.cos(np.linspace(0, np.pi, 100)),
            ]),
            "_is_ac_or_complex": False,
        }]
        return Dataset(rf)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_rename_updates_var_map(self):
        """After rename, _var_map must contain the new name, not old."""
        ds = self._make_dataset()
        ds.rename_variable("v(in)", "v(in_renamed)")
        assert "v(in)" not in ds._var_map
        assert "v(in_renamed)" in ds._var_map

    def test_rename_updates_variable_object_name(self):
        """The Variable object's name attribute must be updated."""
        ds = self._make_dataset()
        var = ds.get_variable("v(in)")
        assert var is not None
        ds.rename_variable("v(in)", "v(in_renamed)")
        assert var.name == "v(in_renamed)"

    def test_rename_nonexistent_raises_keyerror(self):
        """KeyError must be raised when old_name is not found."""
        ds = self._make_dataset()
        with pytest.raises(KeyError):
            ds.rename_variable("nonexistent", "newname")

    def test_rename_duplicate_raises_valueerror(self):
        """ValueError must be raised when new_name already exists."""
        ds = self._make_dataset()
        with pytest.raises(ValueError):
            ds.rename_variable("v(in)", "v(out)")


# ---------------------------------------------------------------------------
# Dataset model integration tests (uses ReplExecutor + real .raw file)
# ---------------------------------------------------------------------------

class TestRenameVariableIntegration:
    """Integration-level: tests Dataset.rename_variable via ReplExecutor.

    These tests exercise the full code path (ReplExecutor -> ApplicationState
    -> Dataset -> RawFile) with a real bridge.raw file on disk.  They verify
    that rename_variable works end-to-end through a parsed RawFile, which is
    a heavier dependency than the in-memory unit tests above.
    """

    def test_rename_updates_var_map(self):
        """After rename, _var_map must contain the new name, not old."""
        from pqwave.models.state import ApplicationState
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        state = ApplicationState()
        ds = state.datasets[0]
        ds.rename_variable("v(ac_p)", "v(ac_p_renamed)")
        assert "v(ac_p)" not in ds._var_map
        assert "v(ac_p_renamed)" in ds._var_map

    def test_rename_updates_variable_object_name(self):
        """The Variable object's name attribute must be updated."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        from pqwave.models.state import ApplicationState
        state = ApplicationState()
        ds = state.datasets[0]
        var = ds.get_variable("v(ac_p)")
        assert var is not None
        ds.rename_variable("v(ac_p)", "v(ac_p_renamed)")
        assert var.name == "v(ac_p_renamed)"

    def test_rename_nonexistent_raises_keyerror(self):
        """KeyError must be raised when old_name is not found."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        from pqwave.models.state import ApplicationState
        state = ApplicationState()
        ds = state.datasets[0]
        with pytest.raises(KeyError):
            ds.rename_variable("nonexistent", "newname")

    def test_rename_duplicate_raises_valueerror(self):
        """ValueError must be raised when new_name already exists."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        from pqwave.models.state import ApplicationState
        state = ApplicationState()
        ds = state.datasets[0]
        with pytest.raises(ValueError):
            ds.rename_variable("v(ac_p)", "v(ac_n)")


# ---------------------------------------------------------------------------
# Session API integration tests
# ---------------------------------------------------------------------------

class TestRenameVectorAPI:
    """Test rename_vector via the session API / REPL code path."""

    def test_rename_success(self):
        """Rename v(ac_p) to v(ac_p_renamed) and verify signals() reflects it."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("rename_vector(0, 'v(ac_p)', 'v(ac_p_renamed)')")
        assert r["ok"] is True
        assert r["result"]["status"] == "ok"
        # Verify old name is gone, new name is present
        r2 = e.run_sync("signals()")
        assert "v(ac_p)" not in r2["result"]
        assert "v(ac_p_renamed)" in r2["result"]

    def test_rename_with_active_trace_blocked(self):
        """Rename must fail if any panel has an active trace referencing old name."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        _add(e, "v(ac_p)")
        r = e.run_sync("rename_vector(0, 'v(ac_p)', 'v(ac_p_renamed)')")
        assert r["result"]["status"] == "error"
        assert "active trace" in r["result"]["message"].lower()

    def test_rename_nonexistent_vector(self):
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("rename_vector(0, 'nonexistent', 'newname')")
        assert r["result"]["status"] == "error"
        assert "not found" in r["result"]["message"].lower()

    def test_rename_duplicate_name(self):
        """Rename to an already-existing name must fail."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("rename_vector(0, 'v(ac_p)', 'v(ac_n)')")
        assert r["result"]["status"] == "error"
        assert "already exists" in r["result"]["message"].lower()

    def test_rename_bad_dataset_index(self):
        """Rename with out-of-range dataset index must fail."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("rename_vector(99, 'v(ac_p)', 'v(new)')")
        assert r["result"]["status"] == "error"
        assert "out of range" in r["result"]["message"].lower()

    def test_rename_propagates_to_expression(self):
        """After rename, expressions using new name must evaluate correctly."""
        e = _fresh_executor()
        _load(e, "pqwave/tests/bridge.raw")
        r = e.run_sync("rename_vector(0, 'v(ac_p)', 'v(ac_p_renamed)')")
        assert r["result"]["status"] == "ok"
        r2 = e.run_sync("add('v(ac_p_renamed) * 2')")
        assert r2["ok"] is True

    def test_command_registered(self):
        """rename_vector must be in the command registry."""
        from pqwave.session.api import get_command_registry
        registry = get_command_registry()
        assert "rename_vector" in registry
