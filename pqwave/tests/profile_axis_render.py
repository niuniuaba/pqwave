#!/usr/bin/env python3
"""
Profile axis rendering cost - the remaining biggest hotspot after PlotCurveItem optimization.

Usage:
    venv/bin/python pqwave/tests/profile_axis_render.py tests/rc_100M.raw
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
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    vb.enableAutoRange(x=False)
    app.processEvents()

    # === Test 1: Baseline with current optimizations ===
    N_EVENTS = 200
    print(f"\n--- Test 1: translateBy baseline ({N_EVENTS} events) ---")

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
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(25)
    print(s.getvalue())

    # === Test 2: With axis tick caching (disable axis update during drag) ===
    print(f"\n--- Test 2: translateBy with hidden axes ({N_EVENTS} events) ---")

    # Hide axes to measure trace-only rendering cost
    pw.getAxis('bottom').setVisible(False)
    pw.getAxis('left').setVisible(False)

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
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(25)
    print(s.getvalue())

    # Restore axes
    pw.getAxis('bottom').setVisible(True)
    pw.getAxis('left').setVisible(True)

    # === Test 3: Without legend ===
    print(f"\n--- Test 3: translateBy without legend ({N_EVENTS} events) ---")

    legend.setParentItem(None)

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
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(25)
    print(s.getvalue())

    pw.close()
    app.quit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: profile_axis_render.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
