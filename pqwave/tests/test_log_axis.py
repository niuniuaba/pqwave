#!/usr/bin/env python3
"""LogAxisItem behaviour.

The original script printed class metadata and never constructed an instance, so
it asserted nothing. Construction, mode toggling and tick generation are tested
properly here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pqwave.utils.log_axis import LogAxisItem  # noqa: E402


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def test_class_is_axis_item_subclass():
    from pyqtgraph import AxisItem
    assert issubclass(LogAxisItem, AxisItem), "LogAxisItem must extend AxisItem"


def test_construction_both_orientations():
    _app()
    left = LogAxisItem(orientation="left")
    bottom = LogAxisItem(orientation="bottom")
    assert left.orientation == "left"
    assert bottom.orientation == "bottom"


def test_log_mode_toggles_both_axes():
    _app()
    axis = LogAxisItem(orientation="left")
    axis.setLogMode(x=True, y=True)
    assert axis.logMode == 1, "setLogMode should enable log mode"
    axis.setLogMode(y=False)
    assert axis.logMode == 0, "setLogMode(y=False) should clear log mode"


def test_dB_mode_roundtrip():
    _app()
    axis = LogAxisItem(orientation="left")
    assert axis.isDbMode() is False, "should start with dB mode off"
    axis.setDbMode(True)
    assert axis.isDbMode() is True
    axis.setDbMode(False)
    assert axis.isDbMode() is False


def test_log_tick_values_are_exponents():
    """Decade ticks are generated at integer *exponent* positions.

    The ViewBox holds log10-transformed values, so a decade at 1000 is
    labelled from the exponent 3.0 -- see the coordinate-system notes in
    AGENTS.md.
    """
    _app()
    axis = LogAxisItem(orientation="left")
    step, major = axis.logTickValues(0.0, 6.0, 400, [])[0]
    assert step >= 1, f"unexpected decade step {step}"
    assert major, "no decade ticks generated"
    assert major[0] == 0.0 and major[-1] == 6.0, (
        f"expected exponents spanning 0..6, got {major}")
    assert all(float(v).is_integer() for v in major), (
        f"decade ticks must sit on integer exponents: {major}")


def test_clamps_very_wide_ranges_to_exponent_bounds():
    """Unbounded linear ranges must not generate unbounded tick lists."""
    _app()
    axis = LogAxisItem(orientation="left")
    _step, major = axis.logTickValues(-1e9, 1e9, 400, [])[0]
    assert min(major) >= axis._MIN_EXPONENT
    assert max(major) <= axis._MAX_EXPONENT
    assert len(major) <= 13, f"expected <= ~12 labelled decades, got {len(major)}"


def test_callback_receives_orientation_and_new_mode():
    """The callback fires only on an actual change, with (orientation, mode)."""
    _app()
    seen = []
    axis = LogAxisItem(orientation="left",
                       log_mode_changed_callback=lambda *a: seen.append(a))
    axis.setLogMode(y=True)
    assert seen == [("left", True)], f"unexpected callback payload: {seen}"
    axis.setLogMode(y=True)          # no change -> must not fire again
    assert len(seen) == 1, f"callback re-fired on an unchanged mode: {seen}"
    axis.setLogMode(y=False)
    assert seen[-1] == ("left", False), f"unexpected callback payload: {seen}"


def test_pqwave_and_pyqtgraph_log_flags_stay_in_sync():
    """`log_mode` (pqwave) and `logMode` (AxisItem) must not diverge."""
    _app()
    axis = LogAxisItem(orientation="left")
    axis.setLogMode(y=True)
    assert axis.log_mode is True
    assert axis.logMode == 1, (
        "AxisItem.logMode out of sync with LogAxisItem.log_mode")
    axis.setLogMode(y=False)
    assert axis.log_mode is False
    assert axis.logMode == 0


def test_linked_viewbox_is_never_put_into_log_mode():
    """Regression: a linked ViewBox must stay linear (double-log corruption).

    Data is pre-transformed to log10 by TraceManager, so if setLogMode let
    AxisItem propagate log mode to the linked ViewBox the plot would be
    log-transformed twice and its range would oscillate.
    """
    import pyqtgraph as pg
    _app()
    pw = pg.PlotWidget()
    axis = LogAxisItem(orientation="left")
    pw.plotItem.setAxisItems({"left": axis})
    vb = pw.plotItem.vb
    assert vb.state["logMode"][1] is False, "ViewBox should start linear"
    axis.setLogMode(y=True)
    assert axis.logMode == 1, "axis itself must be in log mode"
    assert vb.state["logMode"][1] is False, (
        "LogAxisItem leaked log mode into the linked ViewBox -> double-log")
    assert axis._linkedView() is vb, (  # _linkedView is a weakref
        "the guard must restore the ViewBox link after super().setLogMode()")
    pw.close()


def main():
    tests = [
        test_class_is_axis_item_subclass,
        test_construction_both_orientations,
        test_log_mode_toggles_both_axes,
        test_dB_mode_roundtrip,
        test_log_tick_values_are_exponents,
        test_clamps_very_wide_ranges_to_exponent_bounds,
        test_callback_receives_orientation_and_new_mode,
        test_pqwave_and_pyqtgraph_log_flags_stay_in_sync,
        test_linked_viewbox_is_never_put_into_log_mode,
    ]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"✓ {fn.__name__}")
        except Exception as exc:
            print(f"✗ {fn.__name__}: {exc}")
            failures.append(fn.__name__)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
