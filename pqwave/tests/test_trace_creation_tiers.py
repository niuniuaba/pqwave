#!/usr/bin/env python3
"""Integration tests for tiered trace creation."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)


def test_trace_creation_tier1_uses_plotdataitem():
    """Trace with 4000 points creates PlotDataItem (Tier 1)."""
    import pyqtgraph as pg
    from pqwave.models.trace import Trace, AxisAssignment

    x = np.linspace(0, 1, 4000, dtype=np.float64)
    y = np.sin(x * 2 * np.pi * 10)
    trace = Trace(
        name="V(out)",
        expression="V(out)",
        x_data=x,
        y_data=y,
        y_axis=AxisAssignment.Y1,
        color=(0, 255, 255),
    )
    # Verify trace uses default width 2.0
    assert trace.line_width == 2.0

    # The item_type is determined at plot-item creation time by
    # _select_render_strategy. For 4000 points (< 50K), expect Tier 1.
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(4000, 4000)
    assert rs.item_type == "PlotDataItem"
    assert rs.pen_width == 2.0
    assert rs.antialias is True
    assert rs.pre_ds_target is None


def test_trace_creation_tier3_uses_plotcurveitem():
    """Trace with 1M points creates PlotCurveItem (Tier 3)."""
    from pqwave.models.trace import Trace, AxisAssignment
    from pqwave.ui.trace_manager import TraceManager

    rs = TraceManager._select_render_strategy(1000000, 1000000)
    assert rs.item_type == "PlotCurveItem"
    assert rs.pen_width == 1.0
    assert rs.antialias is False
    assert rs.pre_ds_target == 1600
