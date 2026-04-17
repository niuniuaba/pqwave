#!/usr/bin/env python3
"""
Profile the real drag path: ViewBox.translateBy and ViewBox.scaleBy
with app.processEvents() and paint.

Usage:
    venv/bin/python pqwave/tests/profile_viewbox_drag.py tests/rc_100M.raw
"""

import sys
import os
import time
import gc
import cProfile
import pstats
import io
import numpy as np

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile
from pqwave.models.state import ApplicationState
from pqwave.models.trace import AxisAssignment
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.trace_manager import TraceManager

from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg


def main(filepath):
    rf = RawFile(filepath)
    var_names = rf.get_variable_names(0)
    x_var = var_names[0]

    app = QApplication([])

    state = ApplicationState()
    pw = PlotWidget()
    pw.show()
    pw.resize(800, 600)
    app.processEvents()

    legend = pg.LegendItem()
    legend.setParentItem(pw.plotItem.vb)
    legend.anchor((1, 0), (1, 0), offset=(10, 10))

    tm = TraceManager(pw, legend, state)
    tm.set_raw_file(rf)
    tm.set_current_dataset(0)

    print(f"File: {os.path.basename(filepath)}")
    print(f"Adding {len(var_names)-1} traces...")

    t0 = time.perf_counter()
    for vname in var_names[1:]:
        tm.add_trace(vname, x_var, AxisAssignment.Y1)
    app.processEvents()
    t1 = time.perf_counter()
    print(f"Added in {t1 - t0:.3f}s")

    vb = pw.plotItem.vb

    # Auto-range
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    app.processEvents()

    # === Test 1: translateBy (pan) ===
    print("\n--- Test 1: translateBy (pan) - 200 events ---")
    N_EVENTS = 200

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for i in range(N_EVENTS):
        vb.translateBy(x=2.0, y=0)
        app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"  {N_EVENTS} events: {total:.3f}s  ({total / N_EVENTS * 1000:.1f}ms/event)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(30)
    print(s.getvalue())

    # === Test 2: scaleBy (zoom) ===
    print("\n--- Test 2: scaleBy (zoom) - 200 events ---")

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for i in range(N_EVENTS):
        vb.scaleBy(s=(1.005, 1.005))
        app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"  {N_EVENTS} events: {total:.3f}s  ({total / N_EVENTS * 1000:.1f}ms/event)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(30)
    print(s.getvalue())

    # === Test 3: WITHOUT legend ===
    print("\n--- Test 3: translateBy WITHOUT legend - 200 events ---")

    pw2 = pg.PlotWidget()
    pw2.show()
    pw2.resize(800, 600)
    app.processEvents()

    vb2 = pw2.plotItem.vb
    for vname in var_names[1:]:
        y_data = rf.get_variable_data(vname, 0)
        x_data = rf.get_variable_data(x_var, 0)
        x_ds, y_ds = downsample_peak(x_data, y_data, 1600)
        item = pg.PlotCurveItem(x_ds, y_ds, pen=pg.mkPen(width=1))
        vb2.addItem(item)
    vb2.enableAutoRange(x=True, y=True)
    vb2.autoRange(padding=0.05)
    app.processEvents()

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for i in range(N_EVENTS):
        vb2.translateBy(x=2.0, y=0)
        app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"  {N_EVENTS} events: {total:.3f}s  ({total / N_EVENTS * 1000:.1f}ms/event)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(30)
    print(s.getvalue())

    # === Test 4: WITH legend but only 1 trace ===
    print("\n--- Test 4: WITH legend, 1 trace - 200 events ---")

    pw3 = pg.PlotWidget()
    pw3.show()
    pw3.resize(800, 600)
    app.processEvents()

    legend3 = pg.LegendItem()
    legend3.setParentItem(pw3.plotItem.vb)
    legend3.anchor((1, 0), (1, 0), offset=(10, 10))

    vb3 = pw3.plotItem.vb
    y_data = rf.get_variable_data(var_names[1], 0)
    x_data = rf.get_variable_data(x_var, 0)
    x_ds, y_ds = downsample_peak(x_data, y_data, 1600)
    item = pg.PlotCurveItem(x_ds, y_ds, pen=pg.mkPen(width=1))
    vb3.addItem(item)
    legend3.addItem(item, var_names[1])
    vb3.enableAutoRange(x=True, y=True)
    vb3.autoRange(padding=0.05)
    app.processEvents()

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for i in range(N_EVENTS):
        vb3.translateBy(x=2.0, y=0)
        app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"  {N_EVENTS} events: {total:.3f}s  ({total / N_EVENTS * 1000:.1f}ms/event)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(30)
    print(s.getvalue())

    pw.close()
    pw2.close()
    pw3.close()
    app.quit()


def downsample_peak(x, y, n_pts):
    n = len(x)
    if n <= n_pts:
        return x.copy(), y.copy()
    n_bins = n_pts // 2
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
        print("Usage: profile_viewbox_drag.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
