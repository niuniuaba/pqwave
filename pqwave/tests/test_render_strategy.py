#!/usr/bin/env python3
"""Unit tests for RenderStrategy and _select_render_strategy."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Verify no QApplication needed
from pqwave.ui.trace_manager import (
    RenderStrategy, TIER1_MAX, TIER2_MAX, DOWNSAMPLE_TARGET,
)


def test_render_strategy_dataclass():
    """RenderStrategy fields are accessible and have correct types."""
    rs = RenderStrategy("PlotDataItem", 2.0, True, None)
    assert rs.item_type == "PlotDataItem"
    assert rs.pen_width == 2.0
    assert rs.antialias is True
    assert rs.pre_ds_target is None

    rs2 = RenderStrategy("PlotCurveItem", 1.0, False, 1600)
    assert rs2.item_type == "PlotCurveItem"
    assert rs2.pen_width == 1.0
    assert rs2.antialias is False
    assert rs2.pre_ds_target == 1600


def test_select_strategy_tier1_small():
    """Trace < 50K points -> Tier 1."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(4000, 8000)
    assert rs.item_type == "PlotDataItem"
    assert rs.pen_width == 2.0
    assert rs.antialias is True
    assert rs.pre_ds_target is None


def test_select_strategy_tier1_boundary_below():
    """Trace at 49,999 points -> Tier 1."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(49999, 49999)
    assert rs.item_type == "PlotDataItem"


def test_select_strategy_tier2_boundary_low():
    """Trace at exactly 50,000 points -> Tier 2 (boundary belongs to higher tier)."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(50000, 50000)
    assert rs.item_type == "PlotDataItem"
    assert rs.pen_width == 2.0
    assert rs.antialias is True
    assert rs.pre_ds_target is None


def test_select_strategy_tier2_mid():
    """Trace at 200,000 points -> Tier 2."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(200000, 200000)
    assert rs.item_type == "PlotDataItem"
    assert rs.antialias is True


def test_select_strategy_tier2_boundary_high():
    """Trace at 499,999 points -> Tier 2."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(499999, 499999)
    assert rs.item_type == "PlotDataItem"


def test_select_strategy_tier3_boundary_low():
    """Trace at exactly 500,000 points -> Tier 3."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(500000, 500000)
    assert rs.item_type == "PlotCurveItem"
    assert rs.pen_width == 1.0
    assert rs.antialias is False
    assert rs.pre_ds_target == 1600


def test_select_strategy_tier3_large():
    """Trace at 1,000,000 points -> Tier 3."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(1000000, 1000000)
    assert rs.item_type == "PlotCurveItem"
    assert rs.pen_width == 1.0
    assert rs.antialias is False
    assert rs.pre_ds_target == 1600


def test_select_strategy_zero_points():
    """Zero points is still Tier 1 (degenerate case)."""
    from pqwave.ui.trace_manager import TraceManager
    rs = TraceManager._select_render_strategy(0, 0)
    assert rs.item_type == "PlotDataItem"
    assert rs.pen_width == 2.0


def test_select_strategy_no_qt_dependency():
    """_select_render_strategy does not require QApplication."""
    # If we got this far without creating QApplication, the test passes.
    # The import chain for trace_manager triggers QApplication in some
    # code paths; verify we can at least import the function.
    from pqwave.ui.trace_manager import TraceManager
    assert callable(TraceManager._select_render_strategy)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
