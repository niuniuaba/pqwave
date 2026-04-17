#!/usr/bin/env python3
"""
Profile what happens during ACTUAL mouse drag (not scaleBy).

Simulates real mouse drag by sending mouse events through the scene.

Usage:
    venv/bin/python pqwave/tests/profile_mouse_drag.py tests/rc_100M.raw
"""

import sys
import os
import time
import gc
import cProfile
import pstats
import io

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile
from pqwave.models.expression import ExprEvaluator

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
import pyqtgraph as pg
import numpy as np


def main(filepath):
    rf = RawFile(filepath)
    var_names = rf.get_variable_names(0)
    x_var = var_names[0]
    x_data = rf.get_variable_data(x_var, 0)
    evaluator = ExprEvaluator(rf, 0)

    app = QApplication([])
    n_traces = len(var_names) - 1
    n_pts = len(x_data)

    print(f"\nFile: {os.path.basename(filepath)}, {n_traces} traces, {n_pts:,} points each")
    print()

    # Pre-compute all y data
    y_data_list = []
    for vname in var_names[1:]:
        y_data_list.append(evaluator.evaluate(vname))

    # Create PlotWidget + PlotCurveItems
    pw = pg.PlotWidget()
    pw.show()
    pw.resize(800, 600)
    app.processEvents()

    items = []
    t0 = time.perf_counter()
    for y_data in y_data_list:
        x_ds, y_ds = downsample_peak(x_data, y_data, 1600)
        item = pg.PlotCurveItem(x_ds, y_ds, pen=pg.mkPen(width=1))
        pw.plotItem.vb.addItem(item)
        items.append(item)
    t_create = time.perf_counter() - t0
    print(f"Create traces: {t_create:.3f}s")

    # Auto-range
    vb = pw.plotItem.vb
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    app.processEvents()

    # === Test 1: Zoom out 100x, then simulate mouse drag ===
    print("\n--- Test 1: Zoom out 100x + mouse drag ---")
    cr = vb.viewRange()
    xc = (cr[0][0] + cr[0][1]) / 2
    xs = (cr[0][1] - cr[0][0]) * 50
    vb.setXRange(xc - xs, xc + xs, padding=0)
    app.processEvents()
    print(f"  View range: {vb.viewRange()}")

    # Get center of viewbox in scene coords
    vb_rect = vb.sceneBoundingRect()
    center = QPointF(vb_rect.center())
    pw_center = pw.mapFromScene(center)

    # Simulate mouse drag: press, move, release
    N_MOVES = 100

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for _ in range(N_MOVES):
        # Send mouse press
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(pw_center.x(), pw_center.y()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(pw, press)

        # Send mouse move with slight offset
        for i in range(5):
            dx = i * 2
            move = QMouseEvent(
                QMouseEvent.Type.MouseMove,
                QPointF(pw_center.x() + dx, pw_center.y()),
                Qt.MouseButton.LeftButton,  # buttons pressed
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(pw, move)
            app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"  {N_MOVES} drag cycles ({N_MOVES*5} moves): {total:.3f}s")
    print(f"  Average per cycle: {total/N_MOVES*1000:.1f}ms")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(20)
    print("\nTop 20 functions by total time:")
    print(s.getvalue())

    # === Test 2: Zoom in 100x, then simulate mouse drag ===
    print("\n--- Test 2: Zoom in 100x + mouse drag ---")
    cr = vb.viewRange()
    xc = (cr[0][0] + cr[0][1]) / 2
    xs = (cr[0][1] - cr[0][0]) / 100
    vb.setXRange(xc - xs, xc + xs, padding=0)
    app.processEvents()
    print(f"  View range: {vb.viewRange()}")

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for _ in range(N_MOVES):
        # Send mouse press
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(pw_center.x(), pw_center.y()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(pw, press)

        # Send mouse move with slight offset
        for i in range(5):
            dx = i * 2
            move = QMouseEvent(
                QMouseEvent.Type.MouseMove,
                QPointF(pw_center.x() + dx, pw_center.y()),
                Qt.MouseButton.LeftButton,  # buttons pressed
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(pw, move)
            app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"  {N_MOVES} drag cycles ({N_MOVES*5} moves): {total:.3f}s")
    print(f"  Average per cycle: {total/N_MOVES*1000:.1f}ms")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(20)
    print("\nTop 20 functions by total time:")
    print(s.getvalue())

    pw.close()
    app.quit()


def downsample_peak(x, y, n_pts):
    """Downsample x,y data to ~n_pts using peak method (min/max per bin)."""
    n = len(x)
    if n <= n_pts:
        return x.copy(), y.copy()
    n_bins = n_pts // 2  # each bin produces 2 points (min+max)
    if n_bins < 1:
        n_bins = 1
    bin_size = n // n_bins
    if bin_size < 1:
        bin_size = 1

    x_ds = np.empty(n_bins * 2, dtype=x.dtype)
    y_ds = np.empty(n_bins * 2, dtype=y.dtype)

    for i in range(n_bins):
        start = i * bin_size
        end = min(start + bin_size, n)
        x_ds[2 * i] = x[start:end].mean()
        x_ds[2 * i + 1] = x[start:end].mean()
        y_ds[2 * i] = y[start:end].min()
        y_ds[2 * i + 1] = y[start:end].max()

    return x_ds, y_ds


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: profile_mouse_drag.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
