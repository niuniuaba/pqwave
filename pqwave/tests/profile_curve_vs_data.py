#!/usr/bin/env python3
"""
Compare CPU: pg.PlotDataItem vs PlotCurveItem with pre-downsampled data.

Usage:
    venv/bin/python pqwave/tests/profile_curve_vs_data.py tests/rc_100M.raw
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
import pyqtgraph as pg
import numpy as np


def downsample_subsample(x, y, n_pts):
    """Downsample by taking every Nth point."""
    n = len(x)
    if n <= n_pts:
        return x.copy(), y.copy()
    step = max(1, n // n_pts)
    return x[::step].copy(), y[::step].copy()


def downsample_peak(x, y, n_pts):
    """Downsample using peak method (min/max per bin)."""
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
        x_ds[2*i] = x[start:end].mean()
        x_ds[2*i+1] = x[start:end].mean()
        y_ds[2*i] = y[start:end].min()
        y_ds[2*i+1] = y[start:end].max()

    return x_ds, y_ds


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

    N_DRAGS = 50

    # === Config 1: PlotDataItem with autoDownsample ===
    print("--- Config 1: PlotDataItem (autoDownsample=True, clipToView=True) ---")
    gc.collect()
    pw = pg.PlotWidget()
    pw.show()
    app.processEvents()

    pdi_items = []
    t0 = time.perf_counter()
    for y_data in y_data_list:
        item = pg.PlotDataItem(
            x_data, y_data,
            pen=pg.mkPen(width=1), symbol=None,
            skipFiniteCheck=True, autoDownsample=True,
            downsampleMethod='peak', clipToView=True,
        )
        pw.plotItem.vb.addItem(item)
        pdi_items.append(item)
    t_create = time.perf_counter() - t0
    print(f"  Create: {t_create:.3f}s")

    vb = pw.plotItem.vb
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    vb.enableAutoRange(x=False)
    app.processEvents()

    # Zoom out 100x
    cr = vb.viewRange()
    xc = (cr[0][0] + cr[0][1]) / 2
    xs = (cr[0][1] - cr[0][0]) * 50
    vb.setXRange(xc - xs, xc + xs, padding=0)
    app.processEvents()

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    for _ in range(N_DRAGS):
        vb.scaleBy(s=(1.01, 1.0))
        app.processEvents()
    t1 = time.perf_counter()
    pr.disable()

    t_pdi = t1 - t0
    print(f"  {N_DRAGS} drags: {t_pdi:.3f}s  ({t_pdi/N_DRAGS*1000:.1f}ms/drag)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(15)
    print(s.getvalue())

    pw.close()

    # === Config 2: PlotCurveItem with pre-downsampled peak data (1600 pts) ===
    print("--- Config 2: PlotCurveItem (peak downsampled to 1600 pts) ---")
    gc.collect()
    pw = pg.PlotWidget()
    pw.show()
    app.processEvents()

    curve_items = []
    t0 = time.perf_counter()
    for y_data in y_data_list:
        x_ds, y_ds = downsample_peak(x_data, y_data, 1600)
        item = pg.PlotCurveItem(x_ds, y_ds, pen=pg.mkPen(width=1))
        pw.plotItem.vb.addItem(item)
        curve_items.append(item)
    t_create = time.perf_counter() - t0
    print(f"  Create: {t_create:.3f}s")

    vb = pw.plotItem.vb
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    app.processEvents()

    # Zoom out 100x
    cr = vb.viewRange()
    xc = (cr[0][0] + cr[0][1]) / 2
    xs = (cr[0][1] - cr[0][0]) * 50
    vb.setXRange(xc - xs, xc + xs, padding=0)
    app.processEvents()

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    for _ in range(N_DRAGS):
        vb.scaleBy(s=(1.01, 1.0))
        app.processEvents()
    t1 = time.perf_counter()
    pr.disable()

    t_curve_peak = t1 - t0
    print(f"  {N_DRAGS} drags: {t_curve_peak:.3f}s  ({t_curve_peak/N_DRAGS*1000:.1f}ms/drag)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(15)
    print(s.getvalue())

    pw.close()

    # === Config 3: PlotCurveItem with subsampled data (8000 pts) ===
    print("--- Config 3: PlotCurveItem (subsampled to 8000 pts) ---")
    gc.collect()
    pw = pg.PlotWidget()
    pw.show()
    app.processEvents()

    curve_items = []
    t0 = time.perf_counter()
    for y_data in y_data_list:
        x_ds, y_ds = downsample_subsample(x_data, y_data, 8000)
        item = pg.PlotCurveItem(x_ds, y_ds, pen=pg.mkPen(width=1))
        pw.plotItem.vb.addItem(item)
        curve_items.append(item)
    t_create = time.perf_counter() - t0
    print(f"  Create: {t_create:.3f}s")

    vb = pw.plotItem.vb
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    app.processEvents()

    # Zoom out 100x
    cr = vb.viewRange()
    xc = (cr[0][0] + cr[0][1]) / 2
    xs = (cr[0][1] - cr[0][0]) * 50
    vb.setXRange(xc - xs, xc + xs, padding=0)
    app.processEvents()

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    for _ in range(N_DRAGS):
        vb.scaleBy(s=(1.01, 1.0))
        app.processEvents()
    t1 = time.perf_counter()
    pr.disable()

    t_curve_sub = t1 - t0
    print(f"  {N_DRAGS} drags: {t_curve_sub:.3f}s  ({t_curve_sub/N_DRAGS*1000:.1f}ms/drag)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(15)
    print(s.getvalue())

    pw.close()

    # === Summary ===
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  {'PlotDataItem autoDownsample':40s}  {t_pdi:.3f}s  (baseline)")
    print(f"  {'PlotCurveItem peak 1600':40s}  {t_curve_peak:.3f}s  ({t_curve_peak/t_pdi*100:.0f}%)")
    print(f"  {'PlotCurveItem subsample 8000':40s}  {t_curve_sub:.3f}s  ({t_curve_sub/t_pdi*100:.0f}%)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: profile_curve_vs_data.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
