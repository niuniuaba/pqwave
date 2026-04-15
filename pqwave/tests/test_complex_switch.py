#!/usr/bin/env python3
"""Test auto-ranging after switching from complex to real data files."""

import sys
import os
import numpy as np
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def test_complex_to_real_switch():
    """Test that auto-ranging works after switching from complex to real data."""
    app = QApplication(sys.argv)

    from pqwave.ui.main_window import MainWindow
    from pqwave.models.trace import AxisAssignment

    # First load complex data file (cdg.raw)
    print("Step 1: Loading complex data file (cdg.raw)...")
    window = MainWindow('tests/cdg.raw')
    window.show()

    def step1():
        if not window.raw_file:
            print("✗ Failed to load cdg.raw")
            QTimer.singleShot(100, app.quit)
            return

        print(f"✓ Loaded cdg.raw, datasets: {len(window.raw_file.datasets)}")
        var_names = window.raw_file.get_variable_names(0)
        print(f"✓ Variables: {var_names[:5]}...")

        # Add a complex expression
        print("\nStep 2: Adding complex expression...")
        x_var = window.state.current_x_var
        trace = window.trace_manager.add_trace('-imag(ac_data)/2/np.pi/250000*1E12', x_var, AxisAssignment.Y1)
        if trace:
            print(f"✓ Added complex trace: {trace.name}")
            # Enable log mode for Y1 (as per issue reproduction steps)
            window.axis_manager.set_axis_log_mode(AxisAssignment.Y1, True)
            print("✓ Enabled log mode for Y1")
        else:
            print("✗ Failed to add complex trace")

        # Now switch to real data file (bridge.raw)
        print("\nStep 3: Switching to real data file (bridge.raw)...")
        window._load_raw_file('tests/bridge.raw')

        if not window.raw_file:
            print("✗ Failed to load bridge.raw")
            QTimer.singleShot(100, app.quit)
            return

        print(f"✓ Loaded bridge.raw, datasets: {len(window.raw_file.datasets)}")
        var_names = window.raw_file.get_variable_names(0)
        print(f"✓ Variables: {var_names[:5]}...")

        # Disable log mode (as per issue reproduction steps)
        window.axis_manager.set_axis_log_mode(AxisAssignment.Y1, False)
        print("✓ Disabled log mode for Y1")

        # Add a real trace
        print("\nStep 4: Adding real trace...")
        x_var = window.state.current_x_var
        trace = window.trace_manager.add_trace('v(r1)', x_var, AxisAssignment.Y1)
        if trace:
            print(f"✓ Added real trace: {trace.name}")

            # Test auto-ranging
            print("\nStep 5: Testing auto-ranging...")

            # Get current Y1 range before auto-range
            config = window.state.get_axis_config(AxisAssignment.Y1)
            print(f"  Current Y1 range: [{config.min:.6g}, {config.max:.6g}]")

            # Perform auto-range
            window.axis_manager.auto_range_axis(AxisAssignment.Y1)

            # Get new Y1 range after auto-range
            config = window.state.get_axis_config(AxisAssignment.Y1)
            print(f"  After auto-range Y1: [{config.min:.6g}, {config.max:.6g}]")

            # Check that range is reasonable (not NaN or infinite)
            if not np.isfinite(config.min) or not np.isfinite(config.max):
                print("✗ Auto-range failed: range is NaN or infinite")
            elif config.max <= config.min:
                print("✗ Auto-range failed: max <= min")
            else:
                print("✓ Auto-range appears to work correctly")

            # Also test X auto-range
            print("\nStep 6: Testing X auto-ranging...")
            config_x = window.state.get_axis_config(AxisAssignment.X)
            print(f"  Current X range: [{config_x.min:.6g}, {config_x.max:.6g}]")

            window.axis_manager.auto_range_axis(AxisAssignment.X)

            config_x = window.state.get_axis_config(AxisAssignment.X)
            print(f"  After auto-range X: [{config_x.min:.6g}, {config_x.max:.6g}]")

            if not np.isfinite(config_x.min) or not np.isfinite(config_x.max):
                print("✗ X auto-range failed: range is NaN or infinite")
            elif config_x.max <= config_x.min:
                print("✗ X auto-range failed: max <= min")
            else:
                print("✓ X auto-range appears to work correctly")
        else:
            print("✗ Failed to add real trace")

        # Schedule quit
        QTimer.singleShot(100, app.quit)

    # Wait for window to initialize
    QTimer.singleShot(1000, step1)

    # Run the app
    result = app.exec()
    print("\n" + "="*60)
    print("Test completed.")
    return result == 0

if __name__ == "__main__":
    success = test_complex_to_real_switch()
    sys.exit(0 if success else 1)