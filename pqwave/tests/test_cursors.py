#!/usr/bin/env python3
"""
Tests for independent X/Y cursor system (individual toggle per cursor).
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import sys
import math
import numpy as np
from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg

from pqwave.ui.plot_widget import PlotWidget


def test_cursor_creation():
    """Verify all cursor lines are created after _create_cursors()."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()

    assert pw.cursor_xa_line is not None
    assert pw.cursor_xb_line is not None
    assert pw.cursor_yA_line is not None
    assert pw.cursor_yB_line is not None
    # cursor_y2_line is created lazily when Y2 axis is enabled
    assert pw.cursor_y2_line is None

    # All X/Y cursors start hidden
    assert not pw.cursor_xa_line.isVisible()
    assert not pw.cursor_xb_line.isVisible()
    assert not pw.cursor_yA_line.isVisible()
    assert not pw.cursor_yB_line.isVisible()


def test_x_cursor_individual_toggle():
    """Each X cursor can be toggled independently."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    # Both start hidden
    assert not pw.cursor_xa_line.isVisible()
    assert not pw.cursor_xb_line.isVisible()

    # Toggle Xa on
    pw.set_cursor_xa_visible(True)
    assert pw.cursor_xa_line.isVisible()
    assert not pw.cursor_xb_line.isVisible()

    # Toggle Xb on (Xa remains on)
    pw.set_cursor_xb_visible(True)
    assert pw.cursor_xa_line.isVisible()
    assert pw.cursor_xb_line.isVisible()

    # Toggle Xa off (Xb remains on)
    pw.set_cursor_xa_visible(False)
    assert not pw.cursor_xa_line.isVisible()
    assert pw.cursor_xb_line.isVisible()

    # Toggle Xb off
    pw.set_cursor_xb_visible(False)
    assert not pw.cursor_xa_line.isVisible()
    assert not pw.cursor_xb_line.isVisible()


def test_y_cursor_individual_toggle():
    """Each Y cursor can be toggled independently."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    # Toggle YA on
    pw.set_cursor_yA_visible(True)
    assert pw.cursor_yA_line.isVisible()
    assert not pw.cursor_yB_line.isVisible()

    # Toggle YB on (YA remains on)
    pw.set_cursor_yB_visible(True)
    assert pw.cursor_yA_line.isVisible()
    assert pw.cursor_yB_line.isVisible()

    # Toggle YA off (YB remains on)
    pw.set_cursor_yA_visible(False)
    assert not pw.cursor_yA_line.isVisible()
    assert pw.cursor_yB_line.isVisible()

    # Toggle YB off
    pw.set_cursor_yB_visible(False)
    assert not pw.cursor_yA_line.isVisible()
    assert not pw.cursor_yB_line.isVisible()


def test_x_cursor_delta():
    """Place Xa and Xb at known positions, verify get_cursor_deltas()['dx']."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    pw.set_cursor_xa_visible(True)
    pw.set_cursor_xb_visible(True)
    pw.cursor_xa_line.setValue(10.0)
    pw.cursor_xb_line.setValue(30.0)

    deltas = pw.get_cursor_deltas()
    assert deltas['dx'] is not None
    assert abs(deltas['dx'] - 20.0) < 1e-9


def test_y_cursor_delta():
    """Place YA and YB at known positions, verify get_cursor_deltas()['dy1']."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    pw.set_cursor_yA_visible(True)
    pw.set_cursor_yB_visible(True)
    pw.cursor_yA_line.setValue(5.0)
    pw.cursor_yB_line.setValue(15.0)

    deltas = pw.get_cursor_deltas()
    assert deltas['dy1'] is not None
    assert abs(deltas['dy1'] - 10.0) < 1e-9


def test_cursor_independent_from_crosshair():
    """Toggle cross-hair ON then OFF: cursor lines unchanged."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    # Enable X cursor a
    pw.set_cursor_xa_visible(True)
    assert pw.cursor_xa_line.isVisible()

    # Toggle cross-hair ON
    pw.set_cross_hair_visible(True)
    assert pw.cross_hair_vline.isVisible()
    # X cursor should still be visible
    assert pw.cursor_xa_line.isVisible()

    # Toggle cross-hair OFF
    pw.set_cross_hair_visible(False)
    assert not pw.cross_hair_vline.isVisible()
    # X cursor should still be visible
    assert pw.cursor_xa_line.isVisible()


def test_signal_emission():
    """Move lines: verify correct typed signals are emitted."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    received = []

    def capture_x1(val):
        received.append(('xa', val))

    def capture_x2(val):
        received.append(('xb', val))

    def capture_ya(val):
        received.append(('yA', val))

    def capture_yb(val):
        received.append(('yB', val))

    pw.cursor_xa_changed.connect(capture_x1)
    pw.cursor_xb_changed.connect(capture_x2)
    pw.cursor_yA_changed.connect(capture_ya)
    pw.cursor_yB_changed.connect(capture_yb)

    pw.set_cursor_xa_visible(True)
    pw.set_cursor_xb_visible(True)
    pw.set_cursor_yA_visible(True)
    pw.set_cursor_yB_visible(True)

    # Move lines programmatically (InfiniteLine.setValue emits sigPositionChanged)
    pw.cursor_xa_line.setValue(100.0)
    pw.cursor_xb_line.setValue(200.0)
    pw.cursor_yA_line.setValue(300.0)
    pw.cursor_yB_line.setValue(400.0)

    # Check captured signals
    assert ('xa', 100.0) in received, f"Received: {received}"
    assert ('xb', 200.0) in received, f"Received: {received}"
    assert ('yA', 300.0) in received, f"Received: {received}"
    assert ('yB', 400.0) in received, f"Received: {received}"


def test_get_cursor_positions():
    """Verify dict returned by get_cursor_positions has correct keys and values."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    pw.set_cursor_xa_visible(True)
    pw.set_cursor_yA_visible(True)
    pw.cursor_xa_line.setValue(42.0)
    pw.cursor_yA_line.setValue(3.14)

    pos = pw.get_cursor_positions()
    assert isinstance(pos, dict)
    assert set(pos.keys()) == {'xa', 'xb', 'yA', 'yB', 'y2'}
    assert abs(pos['xa'] - 42.0) < 1e-9
    assert pos['xb'] is None  # not visible
    assert abs(pos['yA'] - 3.14) < 1e-9
    assert pos['yB'] is None  # not visible
    assert pos['y2'] is None  # Y2 axis not enabled


def test_single_cursor_no_delta():
    """With only 1 cursor of each type, deltas should be None."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    pw.set_cursor_xa_visible(True)
    pw.set_cursor_yA_visible(True)

    deltas = pw.get_cursor_deltas()
    assert deltas['dx'] is None
    assert deltas['dy1'] is None
    assert deltas['dy2'] is None


def test_xb_only_no_delta():
    """With only Xb visible (no Xa), dx should be None."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    pw.set_cursor_xb_visible(True)
    pw.cursor_xb_line.setValue(25.0)

    deltas = pw.get_cursor_deltas()
    assert deltas['dx'] is None  # Xa not visible


def test_x_cursor_initial_position():
    """When enabling Xa cursor, it should be placed at center of X range."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    pw.plot(x, y, pen='r')
    pw.plotItem.autoRange()

    pw.set_cursor_xa_visible(True)
    x_range = pw.plotItem.vb.viewRange()[0]
    expected_center = sum(x_range) / 2
    # Cursor should be near center
    assert abs(pw.cursor_xa_line.value() - expected_center) < abs(x_range[1] - x_range[0]) * 0.01


def test_log_mode_delta():
    """In log mode, delta should be computed in linear space."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    # Simulate log mode (data already log10 transformed in viewbox)
    pw._x_log_mode = True
    pw._y1_log_mode = True

    # Place cursors at log10 positions (3.0 = 1000, 4.0 = 10000)
    pw.set_cursor_xa_visible(True)
    pw.set_cursor_xb_visible(True)
    pw.cursor_xa_line.setValue(3.0)
    pw.cursor_xb_line.setValue(4.0)

    pw.set_cursor_yA_visible(True)
    pw.set_cursor_yB_visible(True)
    pw.cursor_yA_line.setValue(1.0)
    pw.cursor_yB_line.setValue(2.0)

    deltas = pw.get_cursor_deltas()
    # dx should be 10000 - 1000 = 9000
    assert deltas['dx'] is not None
    assert abs(deltas['dx'] - 9000.0) < 0.1
    # dy1 should be 100 - 10 = 90
    assert deltas['dy1'] is not None
    assert abs(deltas['dy1'] - 90.0) < 0.1


def test_x_cursor_state_preserved_after_crosshair():
    """X cursor state should remain after toggling cross-hair."""
    app = QApplication.instance() or QApplication([])
    pw = PlotWidget()
    pw.plotItem.autoRange()

    pw.set_cursor_xa_visible(True)
    pw.set_cursor_xb_visible(True)
    assert pw.cursor_xa_line.isVisible()
    assert pw.cursor_xb_line.isVisible()

    # Toggle cross-hair
    pw.set_cross_hair_visible(True)
    pw.set_cross_hair_visible(False)

    # X cursor state should still be the same
    assert pw.cursor_xa_line.isVisible()
    assert pw.cursor_xb_line.isVisible()


if __name__ == '__main__':
    test_cursor_creation()
    test_x_cursor_individual_toggle()
    test_y_cursor_individual_toggle()
    test_x_cursor_delta()
    test_y_cursor_delta()
    test_cursor_independent_from_crosshair()
    test_signal_emission()
    test_get_cursor_positions()
    test_single_cursor_no_delta()
    test_xb_only_no_delta()
    test_x_cursor_initial_position()
    test_log_mode_delta()
    test_x_cursor_state_preserved_after_crosshair()
    print("All cursor tests passed!")
