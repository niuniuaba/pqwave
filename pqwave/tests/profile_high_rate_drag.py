#!/usr/bin/env python3
"""
High-rate mouse drag simulation - tests realistic event rates.

Real mouse drag at 60Hz+ generates many events per second.

Usage:
    venv/bin/python pqwave/tests/profile_high_rate_drag.py tests/rc_100M.raw
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
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
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
    print(f"Added in {t1-t0:.3f}s")

    vb = pw.plotItem.vb
    vb_rect = vb.sceneBoundingRect()
    center = QPointF(vb_rect.center())
    pw_center = pw.mapFromScene(center)

    # Zoom out 100x
    vb.enableAutoRange(x=True, y=True)
    vb.autoRange(padding=0.05)
    vb.enableAutoRange(x=False)
    app.processEvents()

    cr = vb.viewRange()
    xc = (cr[0][0] + cr[0][1]) / 2
    xs = (cr[0][1] - cr[0][0]) * 50
    vb.setXRange(xc - xs, xc + xs, padding=0)
    app.processEvents()
    print(f"  View range: {vb.viewRange()}")

    # Profile 500 rapid mouse drag events
    N_EVENTS = 500

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()

    for i in range(N_EVENTS):
        # Mouse press (first event only)
        if i == 0:
            press = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(pw_center.x(), pw_center.y()),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(pw, press)

        # Mouse move (like dragging)
        dx = i * 2
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(pw_center.x() + dx, pw_center.y()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(pw, move)
        app.processEvents()

    t1 = time.perf_counter()
    pr.disable()

    total = t1 - t0
    print(f"\n  {N_EVENTS} drag events: {total:.3f}s  ({total/N_EVENTS*1000:.1f}ms/event)")

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(25)
    print("\nTop 25 functions by total time:")
    print(s.getvalue())

    pw.close()
    app.quit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: profile_high_rate_drag.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
