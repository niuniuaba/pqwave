#!/usr/bin/env python3
"""
Test PlotWidget mouse tracking functionality.
"""
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF
import pyqtgraph as pg
import numpy as np

from pqwave.ui.plot_widget import PlotWidget

def test_mouse_mapping():
    """Test mouse coordinate mapping."""
    app = QApplication([])

    print("Creating PlotWidget...")
    plot_widget = PlotWidget()

    # Add some data so viewbox has a range
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    plot_widget.plot(x, y, pen='r')

    # Auto-range to fit data
    plot_widget.plotItem.autoRange()

    # Force scene creation and layout
    plot_widget.show()  # Not needed for offscreen, but triggers layout

    # Get the viewbox
    viewbox = plot_widget.plotItem.vb
    print(f"Viewbox: {viewbox}")

    # Get scene bounding rect
    rect = viewbox.sceneBoundingRect()
    print(f"Scene bounding rect: {rect}")

    # Check view range
    view_range = viewbox.viewRange()
    print(f"View range: {view_range}")

    # Create a scene position inside the viewbox
    # Use view coordinates that are within view range
    x_range = view_range[0]
    y_range = view_range[1]
    view_x = (x_range[0] + x_range[1]) / 2
    view_y = (y_range[0] + y_range[1]) / 2
    view_pos = pg.Point(view_x, view_y)  # middle of view
    scene_pos = viewbox.mapViewToScene(view_pos)
    print(f"View pos {view_pos} -> scene pos {scene_pos}")

    # Now simulate mouse move with that scene position
    print("Calling _on_mouse_moved directly...")
    plot_widget._on_mouse_moved(scene_pos)

    # Check if signal was emitted (we could connect a slot)
    emitted_coords = []
    def capture_coords(x, y1, y2):
        emitted_coords.append((x, y1, y2))

    plot_widget.mouse_moved.connect(capture_coords)

    # Call again
    plot_widget._on_mouse_moved(scene_pos)

    if emitted_coords:
        x, y1, y2 = emitted_coords[0]
        print(f"Emitted coordinates: x={x}, y1={y1}, y2={y2}")
        # Check that coordinates are close to original view pos
        assert abs(x - 5.0) < 0.1, f"X coordinate mismatch: {x} vs 5.0"
        assert abs(y1 - 0.5) < 0.1, f"Y1 coordinate mismatch: {y1} vs 0.5"
        print("✓ Mouse mapping works")
    else:
        print("✗ No coordinates emitted")

    plot_widget.close()
    app.quit()
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Testing PlotWidget mouse tracking")
    print("=" * 60)

    try:
        test_mouse_mapping()
        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)