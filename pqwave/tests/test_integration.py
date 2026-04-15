#!/usr/bin/env python3
"""Integration test for pqwave modular application."""

import sys
import os
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def test_full_workflow():
    """Test loading a file and adding traces."""
    app = QApplication(sys.argv)

    from pqwave.ui.main_window import MainWindow
    window = MainWindow('tests/bridge.raw')
    window.show()

    # Wait for window to initialize and load file
    def step1():
        print("Step 1: Window loaded, checking components...")

        # Check that raw file is loaded
        if window.raw_file:
            print(f"✓ Raw file loaded: {len(window.raw_file.datasets)} datasets")
            var_names = window.raw_file.get_variable_names(0)
            print(f"✓ Variables: {var_names}")

            # Check that X variable is auto-set
            if window.state.current_x_var:
                print(f"✓ X variable auto-set to: {window.state.current_x_var}")
            else:
                print("✗ X variable not set")

            # Check control panel
            if window.control_panel:
                print("✓ Control panel initialized")

            # Check trace manager
            if window.trace_manager:
                print("✓ Trace manager initialized")

            # Check axis manager
            if window.axis_manager:
                print("✓ Axis manager initialized")

            # Now test adding a trace
            print("\nStep 2: Testing trace addition...")

            # Simulate setting expression to v(ac_p)
            window.control_panel.trace_expr.setText('v(ac_p)')

            # Get current X variable
            x_var = window.state.current_x_var
            print(f"Current X variable: {x_var}")

            # Simulate clicking Y1 button
            print("Simulating Y1 button click...")
            try:
                from pqwave.models.trace import AxisAssignment
                trace = window.trace_manager.add_trace('v(ac_p)', x_var, AxisAssignment.Y1)
                if trace:
                    print(f"✓ Trace added: {trace.name}")
                    print(f"  X data shape: {trace.x_data.shape}")
                    print(f"  Y data shape: {trace.y_data.shape}")
                else:
                    print("✗ Failed to add trace")
            except Exception as e:
                print(f"✗ Error adding trace: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("✗ Raw file not loaded")

        # Schedule quit
        QTimer.singleShot(1000, app.quit)

    # Wait 1000ms for window to initialize, then run step1
    QTimer.singleShot(1000, step1)

    # Run the app
    sys.exit(app.exec())

if __name__ == "__main__":
    test_full_workflow()