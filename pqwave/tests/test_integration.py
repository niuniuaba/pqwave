#!/usr/bin/env python3
"""End-to-end workflow: open a raw file, inspect it, plot traces, clear.

Rewritten from a `__main__`-style script. The previous version drove everything
from nested QTimer.singleShot callbacks inside a local `app.exec()` and ended with
`sys.exit(app.exec())`, which meant:

  * `sys.exit()` inside a test aborted the whole pytest process;
  * the reported result came from Qt's event loop return code, not from any check,
    so a failed load or a refused add_trace still printed and then "passed".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from pqwave.models.trace import AxisAssignment  # noqa: E402
from pqwave.ui.main_window import MainWindow  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURE = os.path.join(_ROOT, "tests", "bridge.raw")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def window(app):
    assert os.path.exists(_FIXTURE), f"missing fixture file {_FIXTURE}"
    w = MainWindow(_FIXTURE)
    w._load_initial_files()   # construction only schedules this on a QTimer
    w.show()
    app.processEvents()
    yield w
    w.close()
    app.processEvents()


def test_main_window_components_are_built(window):
    for component in ("menu_manager", "panel_grid", "control_panel",
                      "trace_manager", "axis_manager", "state"):
        assert getattr(window, component, None) is not None, \
            f"MainWindow.{component} was never constructed"


def test_fixture_file_is_loaded_with_variables(window):
    assert window.raw_file is not None, "MainWindow did not load the raw file"
    assert window.raw_file.datasets, "parsed file has no datasets"
    names = window.raw_file.get_variable_names(0)
    assert names, "dataset 0 exposes no variables"
    assert window.state.datasets, "loaded dataset never reached ApplicationState"


def test_x_axis_is_assigned_from_the_time_variable(window):
    x_var = window.state.current_x_var
    assert x_var, "no X variable was selected"
    assert "time" in str(x_var).lower(), f"unexpected default X variable {x_var!r}"


def test_add_trace_populates_model_and_plot(window, app):
    x_var = window.state.current_x_var
    trace = window.trace_manager.add_trace("v(ac_p)", x_var, AxisAssignment.Y1)
    app.processEvents()

    assert trace is not None, "add_trace returned None"
    assert trace.n_points > 0, "trace has zero points"
    assert len(trace.x_data) == len(trace.y_data) == trace.n_points, \
        "x/y data lengths disagree with the reported point count"
    assert len(window.trace_manager.traces) == 1
    assert trace.name in [t.name for t in window.state.traces], \
        "trace was plotted but never recorded in ApplicationState"


def test_add_trace_to_second_axis(window, app):
    x_var = window.state.current_x_var
    first = window.trace_manager.add_trace("v(ac_p)", x_var, AxisAssignment.Y1)
    second = window.trace_manager.add_trace("v(ac_n)", x_var, AxisAssignment.Y2)
    app.processEvents()
    assert first is not None and second is not None, "a trace was refused"
    assert second.y_axis is AxisAssignment.Y2, "Y2 assignment did not stick"
    assert len(window.trace_manager.traces) == 2


def test_clear_traces_empties_model_and_view(window, app):
    window.trace_manager.add_trace("v(ac_p)", window.state.current_x_var,
                                   AxisAssignment.Y1)
    app.processEvents()
    assert window.trace_manager.traces, "precondition: no trace to clear"

    window.trace_manager.clear_traces()
    app.processEvents()
    assert not window.trace_manager.traces, "clear_traces left curves behind"
    assert not window.state.traces, "clear_traces left traces in ApplicationState"


def main():
    """Run the workflow checks sequentially for `python test_integration.py`."""
    from pqwave.models.state import ApplicationState

    app = QApplication.instance() or QApplication(sys.argv)
    checks = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    ok = True
    for name, fn in checks:
        # Fresh window *and* fresh singleton per check: ApplicationState is a
        # process-wide singleton, so without clearing it each check inherits the
        # traces of the one before and duplicate add_trace calls get refused.
        state = ApplicationState()
        state.clear_traces()
        state.clear_datasets()
        w = MainWindow(_FIXTURE)
        w._load_initial_files()
        w.show()
        app.processEvents()
        try:
            wants_app = "app" in fn.__code__.co_varnames[:fn.__code__.co_argcount]
            fn(w, app) if wants_app else fn(w)
            print(f"PASS: {name}")
        except Exception as exc:
            print(f"FAIL: {name}: {exc}")
            ok = False
        finally:
            w.close()
            app.processEvents()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
