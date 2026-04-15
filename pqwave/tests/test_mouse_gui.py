#!/usr/bin/env python3
"""
Test mouse tracking in the full GUI.
"""
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QPoint

def test_mouse_tracking_in_gui():
    """Test mouse tracking in MainWindow with loaded file."""
    app = QApplication([])

    from pqwave.ui.main_window import MainWindow
    window = MainWindow('tests/bridge.raw')
    window.show()

    # Wait for loading
    app.processEvents()

    # Get plot widget
    plot_widget = window.plot_widget
    # Ensure it has data
    if not window.trace_manager.traces:
        print("No traces, adding one...")
        # Simulate adding a trace
        window.control_panel.trace_expr.setText('v(ac_p)')
        window.trace_manager.add_trace('v(ac_p)', window.state.current_x_var, 'Y1')
        app.processEvents()

    # Get viewbox scene bounding rect
    viewbox = plot_widget.plotItem.vb
    rect = viewbox.sceneBoundingRect()
    print(f"Scene bounding rect: {rect}")
    print(f"View range: {viewbox.viewRange()}")

    # Compute center of viewbox in widget coordinates
    # Need to map from scene to widget
    scene_center = rect.center()
    print(f"Scene center: {scene_center}")

    # Convert to global? We'll simulate mouse move to plot widget
    # Actually, we can call _on_mouse_moved directly with scene position
    print("Calling _on_mouse_moved with scene center...")
    plot_widget._on_mouse_moved(scene_center)

    # Check status bar label
    label_text = window.menu_manager.coord_label.text()
    print(f"Status bar label: {label_text}")

    # Expect not all dashes
    if label_text == "X: -, Y1: -, Y2: -":
        print("✗ Mouse tracking failed - all dashes")
        # Debug further
        # Connect to mouse_moved signal
        def on_mouse_moved(x, y1, y2):
            print(f"Signal received: x={x}, y1={y1}, y2={y2}")
        plot_widget.mouse_moved.connect(on_mouse_moved)
        plot_widget._on_mouse_moved(scene_center)
        return False
    else:
        print("✓ Mouse tracking shows coordinates")
        return True

if __name__ == "__main__":
    print("=" * 60)
    print("Testing mouse tracking in GUI")
    print("=" * 60)

    try:
        success = test_mouse_tracking_in_gui()
        print("\n" + "=" * 60)
        if success:
            print("Test passed!")
        else:
            print("Test failed!")
        print("=" * 60)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)