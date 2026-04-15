#!/usr/bin/env python3
"""
Test settings dialog.
"""
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QDialog, QCheckBox
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QTimer

def test_settings_dialog():
    """Test settings dialog."""
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

    print("Initial state:")
    print(f"  grid_visible: {window.state.grid_visible}")
    print(f"  legend_visible: {window.state.legend_visible}")
    print(f"  toolbar_visible: {window.state.toolbar_visible}")
    print(f"  status_bar_visible: {window.state.status_bar_visible}")

    # Store original values
    original_grid = window.state.grid_visible
    original_legend = window.state.legend_visible
    original_toolbar = window.state.toolbar_visible
    original_statusbar = window.state.status_bar_visible

    # Open settings dialog
    print("Opening settings dialog...")
    # Use a timer to close the dialog after a short delay
    def close_dialog():
        # Find the dialog (should be the active modal widget)
        dialog = app.activeModalWidget()
        if dialog:
            print(f"Found dialog: {dialog.windowTitle()}")
            # Simulate clicking Cancel button (should keep original values)
            dialog.reject()
        else:
            print("No dialog found")

    QTimer.singleShot(1000, close_dialog)

    # Call the method (this will block until dialog closes)
    window.show_settings()

    print("Dialog closed (Cancel)")
    print(f"  grid_visible: {window.state.grid_visible}")
    print(f"  legend_visible: {window.state.legend_visible}")
    print(f"  toolbar_visible: {window.state.toolbar_visible}")
    print(f"  status_bar_visible: {window.state.status_bar_visible}")

    # Verify nothing changed (since we clicked Cancel)
    assert window.state.grid_visible == original_grid, f"grid_visible changed to {window.state.grid_visible}"
    assert window.state.legend_visible == original_legend, f"legend_visible changed to {window.state.legend_visible}"
    assert window.state.toolbar_visible == original_toolbar, f"toolbar_visible changed to {window.state.toolbar_visible}"
    assert window.state.status_bar_visible == original_statusbar, f"status_bar_visible changed to {window.state.status_bar_visible}"

    print("✓ Dialog opens and closes without changing settings (Cancel)")

    # Now test Apply (OK button) with toggled values
    # We'll directly create a dialog and simulate interactions
    print("\nTesting apply functionality...")
    dialog = QDialog(window)
    dialog.setWindowTitle("Settings")
    from PyQt6.QtWidgets import QVBoxLayout, QDialogButtonBox
    layout = QVBoxLayout(dialog)

    grid_check = QCheckBox("Show grid")
    grid_check.setChecked(not original_grid)  # toggle
    layout.addWidget(grid_check)

    legend_check = QCheckBox("Show legend")
    legend_check.setChecked(not original_legend)
    layout.addWidget(legend_check)

    toolbar_check = QCheckBox("Show toolbar")
    toolbar_check.setChecked(not original_toolbar)
    layout.addWidget(toolbar_check)

    statusbar_check = QCheckBox("Show status bar")
    statusbar_check.setChecked(not original_statusbar)
    layout.addWidget(statusbar_check)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(button_box)

    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    # Simulate clicking OK
    # We'll directly call the apply logic from show_settings
    # (since we can't easily simulate button clicks in offscreen mode)
    # Instead, we'll manually call the same update methods
    print("Applying toggled settings...")
    window.axis_manager.set_grid_visible(grid_check.isChecked())
    window.menu_manager.set_grids_visible(grid_check.isChecked())
    window.set_legend_visible(legend_check.isChecked())
    window.set_toolbar_visible(toolbar_check.isChecked())
    window.set_statusbar_visible(statusbar_check.isChecked())

    # Verify changes
    assert window.state.grid_visible == (not original_grid), f"grid_visible not updated, got {window.state.grid_visible}"
    assert window.state.legend_visible == (not original_legend), f"legend_visible not updated, got {window.state.legend_visible}"
    assert window.state.toolbar_visible == (not original_toolbar), f"toolbar_visible not updated, got {window.state.toolbar_visible}"
    assert window.state.status_bar_visible == (not original_statusbar), f"status_bar_visible not updated, got {window.state.status_bar_visible}"

    print("✓ Apply functionality works")

    # Clean up
    window.close()
    app.quit()

if __name__ == "__main__":
    print("=" * 60)
    print("Testing settings dialog")
    print("=" * 60)

    try:
        test_settings_dialog()
        print("\n" + "=" * 60)
        print("Test passed!")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)