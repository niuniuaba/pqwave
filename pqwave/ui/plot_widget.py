#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PlotWidget - Enhanced pyqtgraph PlotWidget with cursor support.

This module provides a PlotWidget subclass that adds:
- Custom log axes with LogAxisItem
- Dual Y-axis support with separate viewbox
- Cross-hair cursor (vertical and horizontal lines)
- Draggable X and Y line cursors (InfiniteLine)
- Mouse coordinate tracking with support for dual Y axes
- Grid and styling with system theme colors
"""

from typing import Optional, Tuple, Callable
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal, Qt

from pqwave.utils.log_axis import LogAxisItem


class PlotWidget(pg.PlotWidget):
    """Enhanced PlotWidget with cursor support and dual Y-axis.

    Signals:
        mouse_moved(x, y1, y2): Emitted when mouse moves over plot
        mouse_left(): Emitted when mouse leaves plot
        cursor_x_changed(value): Emitted when X cursor position changes
        cursor_y1_changed(value): Emitted when Y1 cursor position changes
        cursor_y2_changed(value): Emitted when Y2 cursor position changes
    """

    mouse_moved = pyqtSignal(float, float, float)  # x, y1, y2
    mouse_left = pyqtSignal()
    cursor_x_changed = pyqtSignal(float)
    cursor_y1_changed = pyqtSignal(float)
    cursor_y2_changed = pyqtSignal(float)
    axis_log_mode_changed = pyqtSignal(str, bool)  # orientation, log_mode

    def __init__(self, parent=None):
        """Initialize the enhanced plot widget.

        Args:
            parent: Parent QWidget
        """
        # Create custom axis items with log mode change callbacks
        axis_items = {
            'bottom': LogAxisItem(orientation='bottom',
                                  log_mode_changed_callback=self._on_axis_log_mode_changed),
            'left': LogAxisItem(orientation='left',
                                log_mode_changed_callback=self._on_axis_log_mode_changed),
            'right': LogAxisItem(orientation='right',
                                 log_mode_changed_callback=self._on_axis_log_mode_changed)
        }
        super().__init__(axisItems=axis_items, parent=parent)

        # Enable mouse tracking for the widget
        self.setMouseTracking(True)

        # Initialize attributes
        self.y2_viewbox: Optional[pg.ViewBox] = None
        self.right_axis: Optional[pg.AxisItem] = None
        self.cross_hair_vline: Optional[pg.InfiniteLine] = None
        self.cross_hair_hline: Optional[pg.InfiniteLine] = None
        self.cursor_x_line: Optional[pg.InfiniteLine] = None
        self.cursor_y1_line: Optional[pg.InfiniteLine] = None
        self.cursor_y2_line: Optional[pg.InfiniteLine] = None

        # Cursor visibility and drag state
        self.cross_hair_visible = False
        self.cursor_x_visible = False
        self.cursor_y1_visible = False
        self.cursor_y2_visible = False

        # Mouse tracking state
        self._mouse_inside_viewbox = False

        # Apply system theme colors and styling
        self._apply_theme_colors()

        # Setup grid and axes
        self._setup_grid_and_axes()

        # Create viewbox border
        self._create_viewbox_border()

        # Initialize cursors
        self._create_cursors()

        # Connect mouse signals
        scene = self.plotItem.scene()
        print(f"DEBUG: Connecting sigMouseMoved from scene {scene}")
        scene.sigMouseMoved.connect(self._on_mouse_moved)
        # Note: sigMouseLeave not available, we'll use a timer or other method

    # Public API for cursor control

    def set_cross_hair_visible(self, visible: bool) -> None:
        """Show/hide cross-hair cursor."""
        self.cross_hair_visible = visible
        if self.cross_hair_vline:
            self.cross_hair_vline.setVisible(visible)
        if self.cross_hair_hline:
            self.cross_hair_hline.setVisible(visible)

    def set_cursor_x_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide X cursor line.

        Args:
            visible: Whether to show the cursor
            position: Initial position (uses current X range center if None)
        """
        self.cursor_x_visible = visible
        if self.cursor_x_line:
            self.cursor_x_line.setVisible(visible)
            if position is not None:
                self.cursor_x_line.setValue(position)
            elif visible:
                # Set to center of X range
                x_range = self.plotItem.vb.viewRange()[0]
                self.cursor_x_line.setValue(sum(x_range) / 2)

    def set_cursor_y1_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide Y1 cursor line."""
        self.cursor_y1_visible = visible
        if self.cursor_y1_line:
            self.cursor_y1_line.setVisible(visible)
            if position is not None:
                self.cursor_y1_line.setValue(position)
            elif visible:
                y_range = self.plotItem.vb.viewRange()[1]
                self.cursor_y1_line.setValue(sum(y_range) / 2)

    def set_cursor_y2_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide Y2 cursor line."""
        self.cursor_y2_visible = visible
        if self.cursor_y2_line:
            self.cursor_y2_line.setVisible(visible)
            if position is not None:
                self.cursor_y2_line.setValue(position)
            elif visible and self.y2_viewbox:
                y_range = self.y2_viewbox.viewRange()[1]
                self.cursor_y2_line.setValue(sum(y_range) / 2)

    def get_cursor_positions(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Get current cursor positions.

        Returns:
            Tuple of (x_cursor, y1_cursor, y2_cursor) positions
        """
        x_pos = self.cursor_x_line.value() if self.cursor_x_line else None
        y1_pos = self.cursor_y1_line.value() if self.cursor_y1_line else None
        y2_pos = self.cursor_y2_line.value() if self.cursor_y2_line else None
        return x_pos, y1_pos, y2_pos

    # Dual Y-axis support

    def enable_y2_axis(self) -> None:
        """Enable the right Y-axis with separate viewbox."""
        if self.y2_viewbox is not None:
            return  # Already enabled

        # Show right axis
        self.showAxis('right')
        self.right_axis = self.getAxis('right')

        # Create viewbox for Y2
        self.y2_viewbox = pg.ViewBox()
        self.scene().addItem(self.y2_viewbox)
        self.y2_viewbox.setXLink(self.plotItem)
        self.right_axis.linkToView(self.y2_viewbox)

        # Update geometry on resize
        def update_viewbox():
            rect = self.plotItem.vb.sceneBoundingRect()
            self.y2_viewbox.setGeometry(rect)
            self.y2_viewbox.linkedViewChanged(self.plotItem.vb, self.y2_viewbox.XAxis)

        update_viewbox()
        self.plotItem.vb.sigResized.connect(update_viewbox)

        # Apply theme colors to Y2 axis
        self._apply_theme_to_y2_axis()

        # Create Y2 cursor line if not exists
        if self.cursor_y2_line is None:
            self.cursor_y2_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen('magenta', width=2))
            self.cursor_y2_line.setVisible(False)
            self.y2_viewbox.addItem(self.cursor_y2_line)
            self.cursor_y2_line.sigPositionChanged.connect(
                lambda line: self.cursor_y2_changed.emit(line.value())
            )

    def disable_y2_axis(self) -> None:
        """Disable the right Y-axis and remove viewbox."""
        if self.y2_viewbox is None:
            return

        # Hide right axis
        self.hideAxis('right')

        # Remove Y2 cursor line
        if self.cursor_y2_line:
            self.y2_viewbox.removeItem(self.cursor_y2_line)
            self.cursor_y2_line = None

        # Remove viewbox from scene
        try:
            self.scene().removeItem(self.y2_viewbox)
        except Exception:
            pass

        self.y2_viewbox = None
        self.right_axis = None

    # Axis configuration

    def set_axis_log_mode(self, axis: str, log_mode: bool) -> None:
        """Set log mode for an axis.

        Args:
            axis: 'X', 'Y1', or 'Y2'
            log_mode: True for log scale, False for linear
        """
        if axis == 'X':
            self.plotItem.setLogMode(x=log_mode)
        elif axis == 'Y1':
            self.plotItem.setLogMode(y=log_mode)
        elif axis == 'Y2' and self.y2_viewbox:
            self.y2_viewbox.setLogMode(y=log_mode)
            if self.right_axis:
                self.right_axis.setLogMode(log_mode)

    def set_axis_label(self, axis: str, label: str) -> None:
        """Set label for an axis."""
        if axis == 'X':
            self.plotItem.setLabel('bottom', label)
        elif axis == 'Y1':
            self.plotItem.setLabel('left', label)
        elif axis == 'Y2' and self.right_axis:
            self.plotItem.setLabel('right', label)

    def set_axis_range(self, axis: str, min_val: float, max_val: float) -> None:
        """Set range for an axis."""
        if axis == 'X':
            self.plotItem.setXRange(min_val, max_val, padding=0)
        elif axis == 'Y1':
            self.plotItem.setYRange(min_val, max_val, padding=0)
        elif axis == 'Y2' and self.y2_viewbox:
            self.y2_viewbox.setYRange(min_val, max_val, padding=0)

    def auto_range_axis(self, axis: str) -> None:
        """Enable auto-ranging for an axis."""
        if axis == 'X':
            self.plotItem.enableAutoRange(axis='x')
        elif axis == 'Y1':
            self.plotItem.enableAutoRange(axis='y')
        elif axis == 'Y2' and self.y2_viewbox:
            self.y2_viewbox.enableAutoRange(axis='y')

    # Grid control

    def set_grid_visible(self, visible: bool) -> None:
        """Show/hide grid lines."""
        self.plotItem.showGrid(x=visible, y=visible, alpha=0.3)
        if self.right_axis:
            # Update Y2 grid visibility
            self.right_axis.gridPen = pg.mkPen(color=QColor(self.right_axis.pen.color()) if visible else None)

    # Internal methods

    def _apply_theme_colors(self) -> None:
        """Apply system theme colors to plot."""
        # Get system background color
        bg_color = QApplication.palette().window().color()
        hex_color = bg_color.name()
        self.setBackground(hex_color)

        # Get system text color
        text_color = QApplication.palette().windowText().color()

        # Set axis label colors
        for axis_name in ['bottom', 'left', 'right']:
            axis = self.getAxis(axis_name)
            if axis:
                axis.setPen(text_color)

    def _apply_theme_to_y2_axis(self) -> None:
        """Apply system theme colors to Y2 axis."""
        if not self.right_axis:
            return

        text_color = QApplication.palette().windowText().color()
        self.right_axis.setPen(text_color)

        # Set grid color (semi-transparent)
        grid_color = QColor(text_color)
        grid_color.setAlpha(100)
        self.right_axis.gridPen = pg.mkPen(color=grid_color)

    def _setup_grid_and_axes(self) -> None:
        """Setup grid and axis styling."""
        # Show grid with default alpha
        self.showGrid(x=True, y=True, alpha=0.3)

        # Set grid colors
        text_color = QApplication.palette().windowText().color()
        grid_color = QColor(text_color)
        grid_color.setAlpha(100)

        self.getAxis('bottom').gridPen = pg.mkPen(color=grid_color)
        self.getAxis('left').gridPen = pg.mkPen(color=grid_color)
        if self.right_axis:
            self.right_axis.gridPen = pg.mkPen(color=grid_color)

    def _create_viewbox_border(self) -> None:
        """Create border around the viewbox."""
        text_color = QApplication.palette().windowText().color()
        self.plotItem.vb.setBorder(pg.mkPen(color=text_color, width=1))

    def _create_cursors(self) -> None:
        """Create cursor lines."""
        # Cross-hair lines (non-interactive)
        self.cross_hair_vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', width=1, style=Qt.PenStyle.DashLine))
        self.cross_hair_hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('gray', width=1, style=Qt.PenStyle.DashLine))
        self.cross_hair_vline.setVisible(False)
        self.cross_hair_hline.setVisible(False)
        self.plotItem.addItem(self.cross_hair_vline)
        self.plotItem.addItem(self.cross_hair_hline)

        # X cursor line (draggable)
        self.cursor_x_line = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen('cyan', width=2))
        self.cursor_x_line.setVisible(False)
        self.plotItem.addItem(self.cursor_x_line)
        self.cursor_x_line.sigPositionChanged.connect(
            lambda line: self.cursor_x_changed.emit(line.value())
        )

        # Y1 cursor line (draggable)
        self.cursor_y1_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen('yellow', width=2))
        self.cursor_y1_line.setVisible(False)
        self.plotItem.addItem(self.cursor_y1_line)
        self.cursor_y1_line.sigPositionChanged.connect(
            lambda line: self.cursor_y1_changed.emit(line.value())
        )

        # Y2 cursor line will be created when Y2 axis is enabled

    def _on_mouse_moved(self, pos) -> None:
        """Handle mouse movement for coordinate display and cross-hair."""
        import math

        # Check if viewbox is available
        if not hasattr(self, 'plotItem') or not hasattr(self.plotItem, 'vb') or self.plotItem.vb is None:
            print(f"DEBUG: Viewbox not available. plotItem: {hasattr(self, 'plotItem')}, vb: {hasattr(self.plotItem, 'vb') if hasattr(self, 'plotItem') else 'N/A'}")
            return

        # Check if mouse is inside the main viewbox
        vb_rect = self.plotItem.vb.sceneBoundingRect()
        if vb_rect.isNull() or not vb_rect.isValid():
            # Viewbox not properly initialized yet
            print(f"DEBUG: Viewbox rect invalid: null={vb_rect.isNull()}, valid={vb_rect.isValid()}, rect={vb_rect}")
            if self._mouse_inside_viewbox:
                self._mouse_inside_viewbox = False
                self.mouse_left.emit()
            return

        mouse_inside = vb_rect.contains(pos)
        print(f"DEBUG: Mouse pos={pos}, vb_rect={vb_rect}, mouse_inside={mouse_inside}")

        # Handle state change
        if mouse_inside != self._mouse_inside_viewbox:
            self._mouse_inside_viewbox = mouse_inside
            if not mouse_inside:
                # Mouse left the viewbox
                self.mouse_left.emit()
                return

        # If mouse is outside viewbox, don't emit coordinates
        if not mouse_inside:
            return

        # Mouse is inside viewbox, try to map coordinates
        try:
            # Debug view range
            view_range = self.plotItem.vb.viewRange()
            print(f"DEBUG: View range: {view_range}")
            # Map scene coordinates to main viewbox (Y1 axis)
            view_pos = self.plotItem.vb.mapSceneToView(pos)
            x_val = view_pos.x()
            y1_val = view_pos.y()

            # Get Y2 value if y2_viewbox exists
            y2_val = float('nan')  # Default to NaN if Y2 axis not available
            if self.y2_viewbox:
                try:
                    y2_view_pos = self.y2_viewbox.mapSceneToView(pos)
                    y2_val = y2_view_pos.y()
                except Exception:
                    # If Y2 mapping fails, keep NaN
                    print(f"DEBUG: Y2 mapping failed")
                    pass

            print(f"DEBUG: Mapped coordinates: x={x_val}, y1={y1_val}, y2={y2_val}")

            # Update cross-hair positions
            if self.cross_hair_visible:
                self.cross_hair_vline.setValue(x_val)
                self.cross_hair_hline.setValue(y1_val)

            # Emit signal with coordinates
            self.mouse_moved.emit(x_val, y1_val, y2_val)

        except Exception as e:
            print(f"DEBUG: Exception in mapSceneToView: {e}")
            # If mapping fails, emit NaN values
            self.mouse_moved.emit(float('nan'), float('nan'), float('nan'))

    def _on_axis_log_mode_changed(self, orientation: str, log_mode: bool) -> None:
        """Handle log mode changes from LogAxisItem."""
        # Emit signal for external handling
        self.axis_log_mode_changed.emit(orientation, log_mode)
        # This can be used to update trace visibility or other state
        pass

    # Zoom box mode

    def enable_zoom_box(self, enabled: bool) -> None:
        """Enable or disable rectangle zoom mode."""
        if enabled:
            self.plotItem.vb.setMouseMode(pg.ViewBox.RectMode)
        else:
            self.plotItem.vb.setMouseMode(pg.ViewBox.PanMode)

    def set_plot_title(self, title: str) -> None:
        """Set the plot title."""
        self.plotItem.setTitle(title)

    def get_plot_title(self) -> str:
        """Get the current plot title."""
        return self.plotItem.titleLabel.text if self.plotItem.titleLabel else ''