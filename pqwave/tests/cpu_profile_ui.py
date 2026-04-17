#!/usr/bin/env python3
"""
CPU profiler for pqwave UI rendering and interaction.

Profiles the hot paths during trace creation, auto-range, log mode toggle,
and simulated mouse zoom/pan events.

Usage:
    python pqwave/tests/cpu_profile_ui.py <raw_file>

    e.g.  python pqwave/tests/cpu_profile_ui.py tests/rc_100M.raw
          python pqwave/tests/cpu_profile_ui.py tests/rc_500M.raw
"""

import sys
import os
import gc
import time
import cProfile
import pstats
import io
import numpy as np

# Allow running as script or as module
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile
from pqwave.models.dataset import Dataset
from pqwave.models.expression import ExprEvaluator

from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg


def fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024**2:.1f} MB"
    else:
        return f"{n / 1024**3:.2f} GB"


def profile_ui_interactions(filepath: str):
    """Profile UI rendering path: trace creation, autoRange, log mode, zoom."""
    print(f"\n{'='*70}")
    print(f"CPU Profile (UI rendering): {filepath}")
    print(f"{'='*70}")

    file_size = os.path.getsize(filepath)
    print(f"File size: {fmt_bytes(file_size)}")
    print()

    app = QApplication([])

    timings = {}

    # ---- Stage 1: Load data ----
    print("--- Stage 1: Load raw file ---")
    t0 = time.perf_counter()
    rf = RawFile(filepath)
    t1 = time.perf_counter()
    timings['load_raw'] = t1 - t0
    print(f"  RawFile.parse(): {timings['load_raw']:.3f}s")

    dataset = Dataset(rf, dataset_idx=0)
    var_names = rf.get_variable_names(0)
    n_points = rf.get_num_points(0)
    print(f"  Variables: {len(var_names)}, Points: {n_points:,}")

    # Pick first non-frequency variable as Y trace
    x_var = var_names[0]
    y_var = var_names[1] if len(var_names) > 1 else var_names[0]

    x_data = rf.get_variable_data(x_var, 0)
    y_data = rf.get_variable_data(y_var, 0)
    print(f"  X variable: {x_var} (dtype={x_data.dtype})")
    print(f"  Y variable: {y_var} (dtype={y_data.dtype})")

    # ---- Stage 2: Create PlotWidget + PlotDataItem ----
    print(f"\n--- Stage 2: Create PlotWidget + PlotDataItem ---")
    gc.collect()

    pw = pg.PlotWidget()
    pw.show()
    app.processEvents()

    # 2a: PlotDataItem creation
    t0 = time.perf_counter()
    plot_item = pg.PlotDataItem(
        x_data, y_data,
        name=y_var,
        pen=pg.mkPen(color=(255, 0, 0), width=1),
        symbol=None,
        skipFiniteCheck=True,
        autoDownsample=True,
        downsampleMethod='peak',
    )
    t1 = time.perf_counter()
    timings['create_plotdataitem'] = t1 - t0
    print(f"  PlotDataItem creation: {timings['create_plotdataitem']:.3f}s")

    # 2b: Add to viewbox
    t0 = time.perf_counter()
    pw.plotItem.vb.addItem(plot_item)
    t1 = time.perf_counter()
    timings['add_to_viewbox'] = t1 - t0
    print(f"  addItem to viewbox:    {timings['add_to_viewbox']:.3f}s")

    # 2c: autoRange (this is the expensive one)
    t0 = time.perf_counter()
    pw.plotItem.vb.autoRange(padding=0.05)
    app.processEvents()
    t1 = time.perf_counter()
    timings['autoRange'] = t1 - t0
    print(f"  autoRange:             {timings['autoRange']:.3f}s")

    # ---- Stage 3: cProfile on autoRange ----
    print(f"\n--- Stage 3: cProfile autoRange ---")
    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    pw.plotItem.vb.autoRange(padding=0.05)
    app.processEvents()
    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('tottime')
    ps.print_stats(20)
    print(s.getvalue())

    # ---- Stage 4: Log mode toggle ----
    print(f"\n--- Stage 4: Log mode toggle ---")
    for log_mode in [(True, False), (False, False), (True, True), (False, True)]:
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(3):
            plot_item.setLogMode(*log_mode)
            app.processEvents()
        t1 = time.perf_counter()
        key = f'setLogMode x={log_mode[0]} y={log_mode[1]}'
        timings[key] = t1 - t0
        print(f"  {key} (3x): {timings[key]:.3f}s")

    # ---- Stage 5: cProfile on setLogMode ----
    print(f"\n--- Stage 5: cProfile setLogMode (x_log, y_log) = (True, False) ---")
    gc.collect()
    pr2 = cProfile.Profile()
    pr2.enable()
    plot_item.setLogMode(True, False)
    app.processEvents()
    pr2.disable()

    s2 = io.StringIO()
    ps2 = pstats.Stats(pr2, stream=s2).sort_stats('tottime')
    ps2.print_stats(15)
    print(s2.getvalue())

    # ---- Stage 6: Simulate zoom (scaleBy) ----
    print(f"\n--- Stage 6: Simulate zoom operations ---")
    vb = pw.plotItem.vb
    for label, scale in [("zoom_in 0.8x", (0.8, 0.8)), ("zoom_out 1.25x", (1.25, 1.25))]:
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(5):
            vb.scaleBy(s=scale)
            app.processEvents()
        t1 = time.perf_counter()
        timings[f'scaleBy {label}'] = t1 - t0
        print(f"  {label} (5x): {timings[f'scaleBy {label}']:.3f}s")

    # ---- Stage 7: setData (update data, like switching traces) ----
    print(f"\n--- Stage 7: setData (data update) ---")
    gc.collect()
    t0 = time.perf_counter()
    for _ in range(5):
        plot_item.setData(x_data, y_data)
        app.processEvents()
    t1 = time.perf_counter()
    timings['setData_5x'] = t1 - t0
    print(f"  setData 5x: {timings['setData_5x']:.3f}s")

    # ---- Stage 8: Add multiple traces ----
    print(f"\n--- Stage 8: Add multiple traces ---")
    evaluator = ExprEvaluator(rf, 0)
    all_items = [plot_item]
    t0 = time.perf_counter()
    for vname in var_names[1:min(6, len(var_names))]:
        y = evaluator.evaluate(vname)
        item = pg.PlotDataItem(
            x_data, y,
            name=vname,
            pen=pg.mkPen(width=1),
            symbol=None,
            skipFiniteCheck=True,
            autoDownsample=True,
            downsampleMethod='peak',
        )
        vb.addItem(item)
        all_items.append(item)
    app.processEvents()
    t1 = time.perf_counter()
    timings[f'add_{len(all_items)-1}_traces'] = t1 - t0
    print(f"  Add {len(all_items)-1} traces: {timings[f'add_{len(all_items)-1}_traces']:.3f}s")

    # autoRange after multiple traces
    t0 = time.perf_counter()
    vb.autoRange(padding=0.05)
    app.processEvents()
    t1 = time.perf_counter()
    timings['autoRange_after_multi'] = t1 - t0
    print(f"  autoRange after multi:   {timings['autoRange_after_multi']:.3f}s")

    # ---- Stage 9: cProfile on adding a trace + autoRange ----
    print(f"\n--- Stage 9: cProfile add trace + autoRange ---")
    gc.collect()
    if len(var_names) > 5:
        vname = var_names[5]
        y = evaluator.evaluate(vname)
        pr3 = cProfile.Profile()
        pr3.enable()
        item = pg.PlotDataItem(
            x_data, y,
            name=vname,
            pen=pg.mkPen(width=1),
            symbol=None,
            skipFiniteCheck=True,
            autoDownsample=True,
            downsampleMethod='peak',
        )
        vb.addItem(item)
        vb.autoRange(padding=0.05)
        app.processEvents()
        pr3.disable()

        s3 = io.StringIO()
        ps3 = pstats.Stats(pr3, stream=s3).sort_stats('tottime')
        ps3.print_stats(20)
        print(s3.getvalue())

    # ---- Summary ----
    print(f"\n{'='*70}")
    print("TIMING SUMMARY")
    print(f"{'='*70}")
    for name, t in timings.items():
        print(f"  {name:40s}  {t:.3f}s")

    # Cleanup
    pw.close()
    app.quit()

    return timings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cpu_profile_ui.py <raw_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    profile_ui_interactions(filepath)
