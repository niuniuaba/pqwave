#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test that ThrottledPlotDataItem debounces viewRangeChanged calls.

Usage:
    python pqwave/tests/test_throttled_plot_item.py
"""

import sys
import os

# Allow running from project root
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

from pqwave.utils.throttled_plot_item import ThrottledPlotDataItem, DEBOUNCE_MS


def test_throttled_item_is_plot_data_item():
    """ThrottledPlotDataItem should be a subclass of PlotDataItem."""
    assert issubclass(ThrottledPlotDataItem, pg.PlotDataItem)
    print("PASS: ThrottledPlotDataItem is a subclass of PlotDataItem")


def test_throttled_item_has_timer():
    """ThrottledPlotDataItem should have a QTimer for debouncing."""
    item = ThrottledPlotDataItem()
    assert hasattr(item, '_update_timer')
    assert hasattr(item, '_update_pending')
    assert item._update_pending is False
    assert item._update_timer.isSingleShot()
    print("PASS: ThrottledPlotDataItem has QTimer for debouncing")


def test_throttled_item_produces_display_data():
    """ThrottledPlotDataItem should produce display data like regular PlotDataItem."""
    app = QApplication.instance() or QApplication([])
    N = 10_000
    x = np.linspace(0, 1, N)
    y = np.sin(x * 50)

    item = ThrottledPlotDataItem(
        x, y, symbol=None,
        skipFiniteCheck=True,
        autoDownsample=True,
        downsampleMethod='peak',
    )
    pw = pg.PlotWidget()
    pw.plotItem.vb.addItem(item)
    pw.resize(800, 600)
    app.processEvents()

    # After processEvents, the deferred update should have fired
    dataset = item._getDisplayDataset()
    assert dataset is not None, "_getDisplayDataset should return data"
    assert len(dataset.x) < N, f"autoDownsample should reduce points: {len(dataset.x)} < {N}"

    print(f"PASS: ThrottledPlotDataItem produces display data ({len(dataset.x):,} / {N:,} points)")

    pw.close()


def test_view_range_changed_is_throttled():
    """Multiple rapid viewRangeChanged calls should be coalesced."""
    app = QApplication.instance() or QApplication([])
    N = 100_000
    x = np.linspace(0, 1, N)
    y = np.sin(x * 50)

    item = ThrottledPlotDataItem(
        x, y, symbol=None,
        skipFiniteCheck=True,
        autoDownsample=True,
        downsampleMethod='peak',
    )
    pw = pg.PlotWidget()
    pw.plotItem.vb.addItem(item)
    pw.resize(800, 600)
    app.processEvents()

    # After addItem, an update is pending (timer started by initial viewRangeChanged).
    # The QTimer hasn't fired yet (50ms delay), so we simulate it.
    assert item._update_pending is True
    item._do_throttled_update()
    assert item._update_pending is False

    # Rapid-fire viewRangeChanged calls (simulating mouse drag)
    vb = pw.plotItem.vb
    for _ in range(20):
        item.viewRangeChanged(vb, ranges=None, changed=(True, False))

    # Should have only one pending update (all 20 calls coalesced)
    assert item._update_pending is True

    # Manually trigger the throttled update (in real usage, QTimer fires after DEBOUNCE_MS)
    item._do_throttled_update()

    # After processing, should be back to idle
    assert item._update_pending is False

    print("PASS: Rapid viewRangeChanged calls are coalesced into single update")

    pw.close()


if __name__ == '__main__':
    test_throttled_item_is_plot_data_item()
    test_throttled_item_has_timer()
    test_throttled_item_produces_display_data()
    test_view_range_changed_is_throttled()
    print("All throttled plot item tests passed.")
