#!/usr/bin/env python3
"""
Test trace property editor dialog.
"""
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QTimer

def test_trace_property_editor():
    """Test trace property editor dialog."""
    app = QApplication([])

    from pqwave.ui.main_window import MainWindow
    window = MainWindow('tests/bridge.raw')
    window.show()

    # Wait for loading
    app.processEvents()

    # Ensure we have at least one trace
    if not window.trace_manager.traces:
        print("Adding a trace...")
        # Add a trace directly
        trace = window.trace_manager.add_trace('v(ac_p)', window.state.current_x_var, 'Y1')
        if trace:
            print(f"Added trace: {trace.name}")
        else:
            print("Failed to add trace")
            return False

    print(f"Number of traces: {len(window.trace_manager.traces)}")

    # Store original values
    original_var, original_plot_item, original_y_axis = window.trace_manager.traces[0]
    original_color = original_plot_item.opts['pen'].color()
    original_width = original_plot_item.opts['pen'].width()
    print(f"Original trace: var={original_var}, color={original_color}, width={original_width}")

    # Open trace property editor dialog
    print("Opening trace property editor...")
    # Use a timer to close the dialog after a short delay
    def close_dialog():
        # Find the dialog (should be the active modal widget)
        dialog = app.activeModalWidget()
        if dialog:
            print(f"Found dialog: {dialog.windowTitle()}")
            # Simulate clicking Close button
            close_btn = dialog.findChild(QPushButton, "Close")
            if close_btn:
                QTest.mouseClick(close_btn, Qt.MouseButton.LeftButton)
            else:
                dialog.reject()
        else:
            print("No dialog found")

    QTimer.singleShot(500, close_dialog)

    # Call the method (this will block until dialog closes)
    window.edit_trace_properties()

    print("Dialog closed")

    # Verify nothing changed (since we clicked Close)
    var, plot_item, y_axis = window.trace_manager.traces[0]
    if var != original_var:
        print(f"ERROR: var changed to {var}")
        return False
    if plot_item.opts['pen'].color() != original_color:
        print(f"ERROR: color changed")
        return False
    if plot_item.opts['pen'].width() != original_width:
        print(f"ERROR: width changed")
        return False

    print("✓ Dialog opens and closes without changing trace properties (Close button)")

    # Now test Apply button
    # We'll need to simulate selecting a trace, editing fields, and clicking Apply
    # For simplicity, we'll directly call the helper methods
    print("\nTesting apply functionality via helper methods...")
    # Mock list widget (we need a QListWidget)
    from PyQt6.QtWidgets import QListWidget
    list_widget = QListWidget()
    list_widget.addItem(f"1. {var} @ {y_axis}")
    list_widget.setCurrentRow(0)

    # Update alias edit and color combo via the instance variables
    window.alias_edit.setText("NewAlias")
    window.color_combo.setCurrentIndex(1)  # Red
    window.width_combo.setCurrentIndex(2)  # 3

    # Call apply method
    window._apply_trace_properties(0, list_widget)

    # Check updates
    new_var, new_plot_item, new_y_axis = window.trace_manager.traces[0]
    if new_var != "NewAlias":
        print(f"ERROR: alias not updated, got {new_var}")
        return False
    new_color = new_plot_item.opts['pen'].color()
    expected_color = Qt.GlobalColor.red  # Red color
    # Compare RGB
    if new_color.red() != 255 or new_color.green() != 0 or new_color.blue() != 0:
        print(f"ERROR: color not red, got {new_color.red()}, {new_color.green()}, {new_color.blue()}")
        return False
    new_width = new_plot_item.opts['pen'].width()
    if new_width != 3:
        print(f"ERROR: width not 3, got {new_width}")
        return False

    print("✓ Apply functionality works")

    # Clean up
    window.close()
    app.quit()
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Testing trace property editor")
    print("=" * 60)

    try:
        success = test_trace_property_editor()
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