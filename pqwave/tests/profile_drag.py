#!/usr/bin/env python3
"""
Profile what runs during mouse drag in the real pqwave app.

Loads rc_100M.raw, adds all traces via TraceManager, then simulates
a drag while cProfile captures where CPU time is spent.

Usage:
    .venv/bin/python pqwave/tests/profile_drag.py <raw_file>
"""

import sys
import os
import cProfile
import pstats
import io
import time

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile
from pqwave.models.state import ApplicationState
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.trace_manager import TraceManager
from pqwave.models.trace import AxisAssignment

from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg


def profile_drag(filepath: str):
    app = QApplication([])

    # Load data
    rf = RawFile(filepath)
    print(f"Loaded: {os.path.basename(filepath)}, {len(rf.datasets)} datasets")

    state = ApplicationState()
    pw = PlotWidget()
    pw.show()
    app.processEvents()

    # Create legend
    legend = pg.LegendItem()
    legend.setParentItem(pw.plotItem.vb)
    legend.anchor((1, 0), (1, 0), offset=(10, 10))

    tm = TraceManager(pw, legend, state)
    tm.set_raw_file(rf)
    tm.set_current_dataset(0)

    # Add all traces
    var_names = rf.get_variable_names(0)
    x_var = var_names[0]
    print(f"X variable: {x_var}")
    print(f"Adding {len(var_names) - 1} Y traces...")

    t0 = time.perf_counter()
    for vname in var_names[1:]:
        tm.add_trace(vname, x_var, AxisAssignment.Y1)
    app.processEvents()
    t1 = time.perf_counter()
    print(f"All traces added in {t1 - t0:.3f}s")
    print(f"Total traces in TraceManager: {len(tm.traces)}")

    # Zoom out 100x
    vb = pw.plotItem.vb
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    vb.enableAutoRange(x=False)  # re-enable clipToView
    app.processEvents()

    # Now zoom out 100x
    current_range = vb.viewRange()
    x_center = (current_range[0][0] + current_range[0][1]) / 2
    x_span = (current_range[0][1] - current_range[0][0]) * 50  # 100x zoom out
    vb.setXRange(x_center - x_span, x_center + x_span, padding=0)
    app.processEvents()

    print(f"View range after zoom out: {vb.viewRange()}")

    # Profile the drag: simulate 50 scaleBy calls (like a rapid drag)
    print("\n--- Profiling 50 scaleBy drag events ---")
    gc_collect = __import__('gc').collect

    gc_collect()
    pr = cProfile.Profile()
    pr.enable()

    drag_start = time.perf_counter()
    for i in range(50):
        vb.scaleBy(s=(1.01, 1.0))  # small horizontal shift like a drag
        app.processEvents()
    drag_end = time.perf_counter()
    pr.disable()

    total_wall = drag_end - drag_start
    print(f"Total wall time for 50 drags: {total_wall:.3f}s")
    print(f"Average per drag: {total_wall / 50 * 1000:.1f}ms")

    # Print cProfile results
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('tottime')
    ps.print_stats(40)
    print("\n--- Top 40 functions by total time ---")
    print(s.getvalue())

    # Also show callers of updateItems
    s2 = io.StringIO()
    ps2 = pstats.Stats(pr, stream=s2).sort_stats('cumtime')
    ps2.print_stats(40)
    print("\n--- Top 40 functions by cumulative time ---")
    print(s2.getvalue())

    # Check if throttling is actually working
    print("\n--- Throttle status ---")
    for var, plot_item, y_axis in tm.traces[:3]:
        print(f"  {var}: type={type(plot_item).__name__}, "
              f"pending={getattr(plot_item, '_update_pending', 'N/A')}, "
              f"clipToView={plot_item.opts.get('clipToView', 'N/A')}")

    pw.close()
    app.quit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: profile_drag.py <raw_file>")
        sys.exit(1)
    profile_drag(sys.argv[1])
