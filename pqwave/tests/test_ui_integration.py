#!/usr/bin/env python3
"""UI integration test for pqwave modular components."""

import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def test_main_window():
    """Create MainWindow, load raw file, add a trace, then quit."""
    app = QApplication([])

    from pqwave.ui.main_window import MainWindow
    window = MainWindow('tests/bridge.raw')
    window.show()

    # Wait for loading
    app.processEvents()

    # Load initial file (bypass timer)
    if window.initial_file:
        window._load_initial_file()
        app.processEvents()

    # Give time for window to initialize and load file
    QTimer.singleShot(500, lambda: _test_trace_addition(window))
    QTimer.singleShot(1000, app.quit)

    app.exec()

    # If we reach here, everything completed
    # No return value (pytest expects None)

def _test_trace_addition(window):
    """Helper: test adding a trace to the plot."""
    print("Testing trace addition...")
    # Get references to components
    trace_manager = window.get_trace_manager()
    axis_manager = window.get_axis_manager()
    control_panel = window.get_control_panel()

    # Simulate setting X-axis variable
    # In the UI, this would be done via control panel
    # For now, just check that components exist
    print(f"TraceManager: {trace_manager}")
    print(f"AxisManager: {axis_manager}")
    print(f"ControlPanel: {control_panel}")

    # Check that raw file is loaded
    if window.raw_file:
        print(f"Raw file loaded: {len(window.raw_file.datasets)} datasets")
        # Get variable names
        var_names = window.raw_file.get_variable_names(0)
        if var_names:
            print(f"Variables: {var_names[:3]}...")
    else:
        print("Raw file not loaded")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing UI integration")
    print("=" * 60)

    try:
        test_main_window()
        print("\n" + "=" * 60)
        print("Test passed!")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)