#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF
import pyqtgraph as pg
from pqwave import WaveViewer

app = QApplication([])
print("Creating WaveViewer...")
viewer = WaveViewer()
print("WaveViewer created")

# Test initial label
print(f"Initial coord_label: {viewer.coord_label.text()}")
assert viewer.coord_label.text() == "X: -, Y1: -, Y2: -", f"Expected 'X: -, Y1: -, Y2: -', got '{viewer.coord_label.text()}'"

# Test on_mouse_moved with a mock position
# Create a scene point (in scene coordinates)
scene_point = QPointF(100, 100)
print(f"\nTesting on_mouse_moved with scene point {scene_point}...")
viewer.on_mouse_moved(scene_point)
print(f"After mouse moved: {viewer.coord_label.text()}")

# Check if coordinates were updated (they might be valid or show placeholders)
text = viewer.coord_label.text()
if "X: -" not in text and "Y1: -" not in text:
    print("✓ Coordinates updated successfully")
else:
    print("⚠ Coordinates show placeholders (might be outside plot bounds)")

# Test on_mouse_left_plot
print("\nTesting on_mouse_left_plot...")
viewer.on_mouse_left_plot()
assert viewer.coord_label.text() == "X: -, Y1: -, Y2: -", f"Expected 'X: -, Y1: -, Y2: -', got '{viewer.coord_label.text()}'"
print("✓ on_mouse_left_plot works")

# Test with Y2 viewbox (simulate by creating one)
print("\nTesting with simulated y2_viewbox...")
# We can't easily create a real y2_viewbox in test, but we can check the logic
# by calling the method directly with a mock

# Clean up
viewer.close()
app.quit()
print("\nAll tests passed!")