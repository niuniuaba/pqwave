#!/usr/bin/env python3
"""Trace property editor: the Apply button must commit alias, colour and width.

Companion to test_trace_prop.py (which covers the Close/no-op path).

Rewritten to drive the real dialog instead of a hand-built mock. The mock had
drifted away from the implementation: `_apply_trace_properties` now reads the
dialog from `self._trace_props_dialog` rather than taking it as a third
positional argument. Two of its assertions were also unsound:

  * it expected `trace_manager.traces[0][0]` to become "NewAlias", but that slot
    holds the source *expression*, which an alias must never rewrite;
  * it selected "Red" and asserted red -- red is the palette's *first* colour, so
    the trace was already red and the check could never fail.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget, QPushButton  # noqa: E402

from pqwave.models.trace import AxisAssignment  # noqa: E402
from pqwave.ui.main_window import MainWindow  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURE = os.path.join(_ROOT, "tests", "bridge.raw")

# Index 1 is red, which is already the default colour for the first trace, so use
# green (index 2) to make the colour assertion meaningful.
_GREEN_INDEX = 2
_GREEN_RGB = (0, 255, 0, 255)
_WIDTH_INDEX = 3          # items are 1,2,3,4,5 -> data 4


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
    if not w.trace_manager.traces:
        assert w.trace_manager.add_trace(
            "v(ac_p)", w.state.current_x_var, AxisAssignment.Y1), "add_trace failed"
    app.processEvents()
    yield w
    w.close()
    app.processEvents()


def _button(dialog, text):
    for btn in dialog.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    raise AssertionError(f"no {text!r} button found")


def apply_edits(window, app, alias=None, color_index=None, width_index=None):
    """Open the dialog, edit its real fields, click Apply. Returns the dialog."""
    window.edit_trace_properties()
    app.processEvents()
    dialog = window._trace_props_dialog
    assert dialog is not None and dialog.isVisible(), "dialog did not open"
    if alias is not None:
        dialog.alias_edit.setText(alias)
    if color_index is not None:
        dialog.color_combo.setCurrentIndex(color_index)
    if width_index is not None:
        dialog.width_combo.setCurrentIndex(width_index)
    _button(dialog, "Apply").click()
    app.processEvents()
    return dialog


def test_apply_changes_colour_and_width(window, app):
    _var, item, _axis = window.trace_manager.traces[0]
    assert item.opts["pen"].color().getRgb() != _GREEN_RGB, \
        "test is not discriminating: trace already green"

    apply_edits(window, app, color_index=_GREEN_INDEX, width_index=_WIDTH_INDEX)

    _var, item, _axis = window.trace_manager.traces[0]
    pen = item.opts["pen"]
    assert pen.color().getRgb() == _GREEN_RGB, \
        f"green not applied: {pen.color().getRgb()}"
    assert pen.width() == 4, f"width 4 not applied: {pen.width()}"


def test_apply_renames_the_legend_but_not_the_source_expression(window, app):
    apply_edits(window, app, alias="NewAlias")

    var, item, _axis = window.trace_manager.traces[0]
    # `var` is the expression used to look data up in the dataset: it must stay put.
    assert var == "v(ac_p)", f"source expression was rewritten to {var!r}"
    assert item.opts.get("name") == "NewAlias", \
        f"legend not renamed: {item.opts.get('name')!r}"


def test_apply_updates_the_model_trace_name(window, app):
    apply_edits(window, app, alias="Renamed")
    names = [t.name for t in window.state.traces]
    assert "Renamed" in names, f"state.traces not updated: {names}"
    assert "v(ac_p)" not in names, \
        f"old name still present, rename duplicated instead of replaced: {names}"


def test_apply_updates_the_dialog_list_label(window, app):
    dialog = apply_edits(window, app, alias="Listed")
    labels = [dialog.findChild(QListWidget).item(i).text()
              for i in range(dialog.findChild(QListWidget).count())]
    assert any("Listed" in text for text in labels), \
        f"list row not relabelled: {labels}"


def test_apply_with_blank_alias_keeps_the_existing_name(window, app):
    """A blank alias means 'no rename', not 'rename to the empty string'."""
    apply_edits(window, app, alias="")
    _var, item, _axis = window.trace_manager.traces[0]
    assert item.opts.get("name", "v(ac_p)") == "v(ac_p)", \
        f"blank alias clobbered the name: {item.opts.get('name')!r}"


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    tests = [test_apply_changes_colour_and_width,
             test_apply_renames_the_legend_but_not_the_source_expression,
             test_apply_updates_the_model_trace_name,
             test_apply_updates_the_dialog_list_label,
             test_apply_with_blank_alias_keeps_the_existing_name]
    failures = []
    for fn in tests:
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
            failures.append(fn.__name__)
        finally:
            w.close()
            app.processEvents()
        st = __import__("pqwave.models.state", fromlist=["ApplicationState"]).ApplicationState()
        st.clear_traces()
        st.clear_datasets()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
