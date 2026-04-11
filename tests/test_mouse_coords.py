#!/usr/bin/env python3
"""
Test mouse coordinate tracking in modular pqwave architecture.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtWidgets import QApplication
from pqwave.ui.main_window import MainWindow

def test_menu_manager_coordinate_label():
    """Test MenuManager's coordinate label updates."""
    app = QApplication([])

    # Create MainWindow
    print("Creating MainWindow...")
    window = MainWindow()
    print("MainWindow created")

    # Get menu manager
    menu_manager = window.menu_manager

    # Test initial label
    initial_text = menu_manager.coord_label.text()
    print(f"Initial coord_label: {initial_text}")
    assert initial_text == "X: -, Y1: -, Y2: -", f"Expected 'X: -, Y1: -, Y2: -', got '{initial_text}'"

    # Test update_coordinate_label with values
    print("\nTesting update_coordinate_label with values...")
    menu_manager.update_coordinate_label(1.2345, 2.3456, 3.4567)
    updated_text = menu_manager.coord_label.text()
    print(f"After update: {updated_text}")
    # Check formatting (should show 6 significant figures)
    assert "1.2345" in updated_text, f"Expected X value ~1.2345 in {updated_text}"
    assert "2.3456" in updated_text, f"Expected Y1 value ~2.3456 in {updated_text}"
    assert "3.4567" in updated_text, f"Expected Y2 value ~3.4567 in {updated_text}"

    # Test update_coordinate_label with None values (mouse left)
    print("\nTesting update_coordinate_label with None values...")
    menu_manager.update_coordinate_label(None, None, None)
    cleared_text = menu_manager.coord_label.text()
    print(f"After clear: {cleared_text}")
    assert cleared_text == "X: -, Y1: -, Y2: -", f"Expected 'X: -, Y1: -, Y2: -', got '{cleared_text}'"

    # Test with partial values
    print("\nTesting update_coordinate_label with partial values...")
    menu_manager.update_coordinate_label(5.0, None, 7.0)
    partial_text = menu_manager.coord_label.text()
    print(f"Partial update: {partial_text}")
    assert "5" in partial_text, f"Expected X value 5 in {partial_text}"
    assert "Y1: -" in partial_text, f"Expected Y1 placeholder in {partial_text}"
    assert "7" in partial_text, f"Expected Y2 value 7 in {partial_text}"

    print("✓ MenuManager coordinate label tests passed")

    # Clean up
    window.close()
    app.quit()
    return True

def test_signal_connections():
    """Test that mouse signals from PlotWidget update coordinate label."""
    app = QApplication([])

    print("\nTesting signal connections...")
    window = MainWindow()

    # Get references
    plot_widget = window.plot_widget
    menu_manager = window.menu_manager

    # Emit mouse_moved signal
    print("Emitting mouse_moved signal...")
    plot_widget.mouse_moved.emit(10.5, 20.5, 30.5)

    # Check label updated
    text = menu_manager.coord_label.text()
    print(f"Label after signal: {text}")
    assert "10.5" in text, f"Expected X value 10.5 in {text}"
    assert "20.5" in text, f"Expected Y1 value 20.5 in {text}"
    assert "30.5" in text, f"Expected Y2 value 30.5 in {text}"

    # Emit mouse_left signal
    print("Emitting mouse_left signal...")
    plot_widget.mouse_left.emit()

    text = menu_manager.coord_label.text()
    print(f"Label after mouse_left: {text}")
    assert text == "X: -, Y1: -, Y2: -", f"Expected cleared label, got {text}"

    print("✓ Signal connection tests passed")

    window.close()
    app.quit()
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Testing mouse coordinate tracking in modular pqwave")
    print("=" * 60)

    try:
        # Test MenuManager directly
        test_menu_manager_coordinate_label()

        # Test signal connections
        test_signal_connections()

        print("\n" + "=" * 60)
        print("All mouse coordinate tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)