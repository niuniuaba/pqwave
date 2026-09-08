#!/usr/bin/env python3
"""Trace property editor: opening and closing the dialog must not mutate a trace.

Rewritten from a `__main__`-only script whose checks never actually ran:
  * it dismissed the dialog from a QTimer.singleShot, but the dialog is shown
    non-blocking, so the callback was never reached before the assertions;
  * `QPushButton` was used but never imported, so the dismissal helper would have
    raised NameError even if it had run;
  * MainWindow('tests/bridge.raw') defers its load onto a QTimer, so one
    processEvents() left the window with "No raw file opened";
  * it asserted `traces[0][0] == "NewAlias"`, but that tuple slot holds the source
    *expression*, which an alias rename must never change.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from pqwave.models.trace import AxisAssignment  # noqa: E402
from pqwave.ui.main_window import MainWindow  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURE = os.path.join(_ROOT, "tests", "bridge.raw")

# The palette starts at red, so tests that assert a colour change must pick a
# non-default index (0 is "Default (auto)", 1 is red, 2 is green).
_GREEN = 2
_GREEN_RGB = (0, 255, 0, 255)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def window(app):
    """MainWindow with one trace plotted and the raw file actually loaded."""
    assert os.path.exists(_FIXTURE), f"missing fixture file {_FIXTURE}"
    w = MainWindow(_FIXTURE)
    # Construction only *schedules* the load on a QTimer(100); run it directly so
    # the test does not depend on the event loop reaching that timeout.
    w._load_initial_files()
    w.show()
    app.processEvents()
    if not w.trace_manager.traces:
        assert w.trace_manager.add_trace(
            "v(ac_p)", w.state.current_x_var, AxisAssignment.Y1), \
            "could not add a trace to the freshly loaded file"
    app.processEvents()
    yield w
    w.close()
    app.processEvents()


def open_dialog(window, app):
    """Open the trace-property dialog and hand it back.

    edit_trace_properties() ends in a non-blocking dialog.show(), so the dialog is
    reachable immediately -- but that also means a QTimer.singleShot dismissal is
    never reached before the assertions run, which is precisely how the original
    version of these tests managed to verify nothing. Drive the buttons directly.
    """
    window.edit_trace_properties()
    app.processEvents()
    dialog = window._trace_props_dialog
    assert dialog is not None and dialog.isVisible(), "dialog did not open"
    return dialog


def button(dialog, text):
    for btn in dialog.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    raise AssertionError(
        f"no {text!r} button in {[b.text() for b in dialog.findChildren(QPushButton)]}")


def test_dialog_lists_the_plotted_trace(window, app):
    dialog = open_dialog(window, app)
    labels = [dialog.findChild(__import__("PyQt6.QtWidgets", fromlist=["QListWidget"])
                               .QListWidget).item(i).text()
              for i in range(dialog.findChild(__import__("PyQt6.QtWidgets", fromlist=["QListWidget"])
                                              .QListWidget).count())]
    assert any("v(ac_p)" in text for text in labels), \
        f"trace missing from the dialog list: {labels}"
    button(dialog, "Close").click()


def test_close_button_leaves_everything_untouched(window, app):
    _var, item, _axis = window.trace_manager.traces[0]
    before = (item.opts["pen"].color().getRgb(), item.opts["pen"].width(),
              item.opts.get("name"), [t.name for t in window.state.traces])

    dialog = open_dialog(window, app)

    # Change every field, then Close: none of it may be committed.
    dialog.alias_edit.setText("ShouldNotStick")
    dialog.color_combo.setCurrentIndex(_GREEN)
    dialog.width_combo.setCurrentIndex(4)
    button(dialog, "Close").click()
    app.processEvents()

    _var2, item2, _axis2 = window.trace_manager.traces[0]
    after = (item2.opts["pen"].color().getRgb(), item2.opts["pen"].width(),
             item2.opts.get("name"), [t.name for t in window.state.traces])
    assert after == before, (
        f"Close committed edits\n  before: {before}\n  after:  {after}")


def test_close_does_not_rename_the_model_trace(window, app):
    dialog = open_dialog(window, app)
    dialog.alias_edit.setText("Ghost")
    button(dialog, "Close").click()
    app.processEvents()
    assert [t.name for t in window.state.traces] == ["v(ac_p)"], \
        "closing the dialog renamed the trace"


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    ok = True
    for fn in (test_dialog_lists_the_plotted_trace,
               test_close_button_leaves_everything_untouched,
               test_close_does_not_rename_the_model_trace):
        w = MainWindow(_FIXTURE)
        w._load_initial_files()
        w.show()
        app.processEvents()
        if not w.trace_manager.traces:
            w.trace_manager.add_trace("v(ac_p)", w.state.current_x_var,
                                      AxisAssignment.Y1)
        app.processEvents()
        try:
            fn(w, app)
            print(f"PASS: {fn.__name__}")
        except Exception as exc:
            print(f"FAIL: {fn.__name__}: {exc}")
            ok = False
        finally:
            w.close()
            app.processEvents()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
