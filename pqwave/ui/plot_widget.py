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
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtCore import pyqtSignal, Qt, QTimer

from pqwave.utils.log_axis import LogAxisItem
from pqwave.logging_config import get_logger
from pqwave.models.state import ViewboxTheme, THEME_COLORS

# ViewBox update throttle interval (ms).  Coalesces rapid pan/zoom events
# into fewer paint cycles.  30ms = ~30fps, which is visually smooth while
# cutting CPU from ~200+ paint/sec to ~30 paint/sec during mouse drag.
_VB_THROTTLE_MS = 30


class PlotWidget(pg.PlotWidget):
    """Enhanced PlotWidget with cursor support and dual Y-axis.

    Signals:
        mouse_moved(x, y1, y2): Emitted when mouse moves over plot
        mouse_left(): Emitted when mouse leaves plot
        cursor_x_changed(value): Emitted when X cursor position changes
        cursor_y1_changed(value): Emitted when Y1 cursor position changes
        cursor_y2_changed(value): Emitted when Y2 cursor position changes
        mark_clicked(x, y1, y2): Emitted when user clicks to place a mark
    """

    logger = get_logger(__name__)

    mouse_moved = pyqtSignal(float, float, float)  # x, y1, y2
    mouse_left = pyqtSignal()
    cursor_x_changed = pyqtSignal(float)
    cursor_y1_changed = pyqtSignal(float)
    cursor_y2_changed = pyqtSignal(float)
    axis_log_mode_changed = pyqtSignal(str, bool)  # orientation, log_mode
    mark_clicked = pyqtSignal(float, float, float, float, float)  # x_vb, y1_vb, x_linear, y1_linear, y2_linear

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

        # Mark tracking state (only active when cross-hair is ON)
        self._mark_scatter: Optional[pg.ScatterPlotItem] = None
        self._mark_positions: list = []  # list of (x, y1) tuples
        self._mark_label: Optional[pg.TextItem] = None  # hover tooltip
        self._mark_label_visible = False

        # Log mode tracking per axis
        self._x_log_mode = False
        self._y1_log_mode = False
        self._y2_log_mode = False

        # Apply viewbox theme and styling
        self._apply_viewbox_theme(ViewboxTheme.DARK)

        # Initialize cursors
        self._create_cursors()

        # Connect mouse signals
        scene = self.plotItem.scene()
        scene.sigMouseMoved.connect(self._on_mouse_moved)
        scene.sigMouseClicked.connect(self._on_mouse_clicked)

        # Optimize ViewBox rendering for performance with large datasets.
        # Throttle view range updates during mouse drag/pan/zoom to ~30fps
        # instead of painting every event (~200+ Hz).
        vb = self.plotItem.vb
        self._vb_update_timer = QTimer()
        self._vb_update_timer.setSingleShot(True)
        self._vb_update_timer.setInterval(_VB_THROTTLE_MS)
        self._vb_update_timer.timeout.connect(self._flush_vb_updates)
        self._vb_update_pending = False
        self._vb_queued_translate = None  # accumulated (dx, dy)
        self._vb_queued_call = None  # ('scaleBy', args, kwargs) or None
        # Wrap ViewBox.translateBy and scaleBy to go through throttle
        self._orig_vb_translateBy = vb.translateBy
        self._orig_vb_scaleBy = vb.scaleBy
        vb.translateBy = self._throttled_vb_translateBy
        vb.scaleBy = self._throttled_vb_scaleBy

    # Public API for cursor control

    def set_cross_hair_visible(self, visible: bool) -> None:
        """Show/hide cross-hair cursor."""
        self.cross_hair_visible = visible
        if self.cross_hair_vline:
            self.cross_hair_vline.setVisible(visible)
        if self.cross_hair_hline:
            self.cross_hair_hline.setVisible(visible)

    def add_mark_at_position(self, x: float, y1: float) -> None:
        """Add a visual mark at the given plot coordinates.

        Args:
            x: X coordinate in plot space
            y1: Y1 coordinate in plot space
        """
        self._mark_positions.append((x, y1))
        self._update_mark_scatter()

    def remove_last_mark(self) -> bool:
        """Remove the most recently placed visual mark.

        Returns:
            True if a mark was removed, False if no marks exist.
        """
        if not self._mark_positions:
            return False
        self._mark_positions.pop()
        self._update_mark_scatter()
        return True

    def clear_marks(self) -> None:
        """Remove all visual marks."""
        self._mark_positions.clear()
        self._update_mark_scatter()
        self._hide_mark_label()

    def _update_mark_scatter(self) -> None:
        """Update the scatter plot item with current mark positions."""
        if self._mark_positions:
            if self._mark_scatter is None:
                # Use the current theme's foreground color (semi-transparent)
                fg_color = THEME_COLORS[self._current_theme]['foreground']
                mark_color = QColor(fg_color)
                mark_color.setAlpha(160)

                self._mark_scatter = pg.ScatterPlotItem(
                    size=8,
                    pen=pg.mkPen(color=mark_color, width=1),
                    brush=pg.mkBrush(mark_color),
                    symbol='x',
                    hoverable=True,
                    hoverSize=12,
                    hoverPen=pg.mkPen(color=mark_color, width=1),
                    hoverBrush=pg.mkBrush(mark_color),
                )
                self.plotItem.addItem(self._mark_scatter)
            xs, ys = zip(*self._mark_positions)
            self._mark_scatter.setData(list(xs), list(ys))
        else:
            if self._mark_scatter is not None:
                self.plotItem.removeItem(self._mark_scatter)
                self._mark_scatter = None
            # Also clean up the hover label
            if self._mark_label is not None:
                try:
                    self.plotItem.removeItem(self._mark_label)
                except Exception:
                    pass
                self._mark_label = None
            self._mark_label_visible = False

    def _check_mark_hover(self, x_vb: float, y1_vb: float) -> None:
        """Check if mouse is near any mark and show/hide the tooltip.

        Called from _on_mouse_moved to detect proximity to marks.
        Uses pixel (scene) distance for accurate hit detection regardless
        of zoom level or log mode.
        """
        if not self._mark_positions:
            self._hide_mark_label()
            return

        from PyQt6.QtCore import QPointF

        # Map mouse position to scene (pixel) coordinates
        try:
            mouse_scene = self.plotItem.vb.mapViewToScene(QPointF(x_vb, y1_vb))
        except Exception:
            self._hide_mark_label()
            return

        # Check distance in pixel space (20 pixel radius)
        threshold_px = 20.0

        for i, (mx, my) in enumerate(self._mark_positions):
            try:
                mark_scene = self.plotItem.vb.mapViewToScene(QPointF(mx, my))
                dx = mouse_scene.x() - mark_scene.x()
                dy = mouse_scene.y() - mark_scene.y()
                if dx * dx + dy * dy < threshold_px * threshold_px:
                    self._show_mark_label(mx, my, i + 1)
                    return
            except Exception:
                continue

        self._hide_mark_label()

    def _show_mark_label(self, x_vb: float, y_vb: float, index: int) -> None:
        """Show the hover tooltip for a mark.

        Args:
            x_vb: X coordinate in viewbox space
            y_vb: Y coordinate in viewbox space
            index: 1-based mark index
        """
        if self._mark_label is None:
            colors = THEME_COLORS[self._current_theme]
            self._mark_label = pg.TextItem(
                text='',
                anchor=(0, 1),
                color=colors['foreground'],
                fill=pg.mkBrush(colors['background']),
            )
            self.plotItem.addItem(self._mark_label)

        self._mark_label.setText(f"#{index}")
        self._mark_label.setPos(x_vb, y_vb)
        self._mark_label.setVisible(True)
        self._mark_label_visible = True

    def _hide_mark_label(self) -> None:
        """Hide the hover tooltip."""
        if self._mark_label is not None:
            self._mark_label.setVisible(False)
            self._mark_label_visible = False

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

        # Apply current theme to Y2 axis
        self._apply_viewbox_theme(self._current_theme)

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

        Data is pre-transformed to log10 space by TraceManager.
        We set the AXIS to log mode (for tick generation) but keep the
        ViewBox in LINEAR mode — otherwise viewRange() applies log10
        to the range, causing double-log corruption.
        """
        if axis == 'X':
            self._x_log_mode = log_mode
            self.getAxis('bottom').setLogMode(x=log_mode)
        elif axis == 'Y1':
            self._y1_log_mode = log_mode
            self.getAxis('left').setLogMode(y=log_mode)
        elif axis == 'Y2' and self.y2_viewbox:
            self._y2_log_mode = log_mode
            if self.right_axis:
                self.right_axis.setLogMode(log_mode)

    @staticmethod
    def _log_to_linear(value: float) -> float:
        """Convert log-space coordinate back to linear space for display.

        TraceManager pre-transforms data to log10 space, so the ViewBox
        coordinates are exponent values (e.g., 3.0 for actual value 1000).
        This converts back to 10^3 = 1000 for user display.
        """
        import math
        try:
            return 10.0 ** value
        except OverflowError:
            return float('inf') if value > 0 else float('-inf')
        except (ValueError, ZeroDivisionError):
            return float('nan')

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
        """Auto-range an axis based on current data and immediately update the view.

        For X axis: after auto-ranging, autoRange is disabled so that
        clipToView on PlotDataItem can work (pyqtgraph skips clipping
        when autoRange is enabled). This matches xschem's behavior where
        the view only changes on explicit user action.
        """
        vb = self.plotItem.vb
        if axis == 'X':
            vb.enableAutoRange(x=True)
            vb.autoRange(padding=0.05)
            # Disable X autoRange so clipToView works during pan/zoom
            vb.enableAutoRange(x=False)
        elif axis == 'Y1':
            vb.enableAutoRange(y=True)
            vb.autoRange(padding=0.05)
        elif axis == 'Y2' and self.y2_viewbox:
            self.y2_viewbox.enableAutoRange(y=True)
            self.y2_viewbox.autoRange(padding=0.05)

    # Grid control

    def set_grid_visible(self, visible: bool) -> None:
        """Show/hide grid lines."""
        self.plotItem.showGrid(x=visible, y=visible, alpha=0.3)
        if self.right_axis:
            # Update Y2 grid visibility
            fg_color = THEME_COLORS[self._current_theme]['foreground']
            grid_color = QColor(fg_color)
            grid_color.setAlpha(100)
            self.right_axis.gridPen = pg.mkPen(color=grid_color) if visible else pg.mkPen(None)

    # Internal methods

    def _apply_viewbox_theme(self, theme: ViewboxTheme) -> None:
        """Apply the specified theme to the plot viewbox, axes, and title."""
        colors = THEME_COLORS[theme]
        bg_color = colors['background']
        fg_color = colors['foreground']

        self._current_theme = theme

        # Set viewbox background
        self.setBackground(bg_color)

        # Set axis pens (bottom, left, right) and their label colors
        for axis_name in ['bottom', 'left', 'right']:
            axis = self.getAxis(axis_name)
            if axis:
                axis.setPen(fg_color)
                axis.labelStyle['color'] = fg_color
                axis._updateLabel()

        # Set grid colors
        grid_color = QColor(fg_color)
        grid_color.setAlpha(100)
        self.getAxis('bottom').gridPen = pg.mkPen(color=grid_color)
        self.getAxis('left').gridPen = pg.mkPen(color=grid_color)
        if self.right_axis:
            self.right_axis.gridPen = pg.mkPen(color=grid_color)

        # Set viewbox border
        self.plotItem.vb.setBorder(pg.mkPen(color=fg_color, width=1))

        # Set title label color
        if self.plotItem.titleLabel:
            self.plotItem.titleLabel.opts['color'] = fg_color
            title_text = self.plotItem.titleLabel.text
            if title_text:
                self.plotItem.titleLabel.setText(title_text)

        # Update existing mark scatter colors
        if self._mark_scatter is not None:
            mark_color = QColor(fg_color)
            mark_color.setAlpha(160)
            self._mark_scatter.setPen(pg.mkPen(color=mark_color, width=1))
            self._mark_scatter.setBrush(pg.mkBrush(mark_color))
            self._mark_scatter.setHoverPen(pg.mkPen(color=mark_color, width=1))
            self._mark_scatter.setHoverBrush(pg.mkBrush(mark_color))

        # Update existing mark label colors
        if self._mark_label is not None:
            self._mark_label.setColor(fg_color)
            self._mark_label.fill = pg.mkBrush(bg_color)

    def set_viewbox_theme(self, theme: ViewboxTheme) -> None:
        """Apply a viewbox theme and update all visual elements."""
        self._apply_viewbox_theme(theme)

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

        # Check if viewbox is available
        if not hasattr(self, 'plotItem') or not hasattr(self.plotItem, 'vb') or self.plotItem.vb is None:
            return

        # Check if mouse is inside the main viewbox
        vb_rect = self.plotItem.vb.sceneBoundingRect()
        if vb_rect.isNull() or not vb_rect.isValid():
            if self._mouse_inside_viewbox:
                self._mouse_inside_viewbox = False
                self.mouse_left.emit()
            return

        mouse_inside = vb_rect.contains(pos)

        # Handle state change
        if mouse_inside != self._mouse_inside_viewbox:
            self._mouse_inside_viewbox = mouse_inside
            if not mouse_inside:
                # Mouse left the viewbox
                self.mouse_left.emit()
                self._hide_mark_label()
                return

        # If mouse is outside viewbox, don't emit coordinates
        if not mouse_inside:
            return

        # Mouse is inside viewbox, try to map coordinates
        try:
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
                    pass

            # Update cross-hair positions (always in viewbox coordinates)
            if self.cross_hair_visible:
                self.cross_hair_vline.setValue(x_val)
                self.cross_hair_hline.setValue(y1_val)

            # Check if mouse is near any mark for hover tooltip
            self._check_mark_hover(x_val, y1_val)

            # Convert to linear space for display before emitting
            display_x = self._log_to_linear(x_val) if self._x_log_mode else x_val
            display_y1 = self._log_to_linear(y1_val) if self._y1_log_mode else y1_val
            display_y2 = self._log_to_linear(y2_val) if self._y2_log_mode else y2_val

            # Emit signal with linear display coordinates
            self.mouse_moved.emit(display_x, display_y1, display_y2)

        except Exception:
            # If mapping fails, emit NaN values
            self.mouse_moved.emit(float('nan'), float('nan'), float('nan'))

    def _on_mouse_clicked(self, event) -> None:
        """Handle mouse clicks for mark placement.

        Only places a mark when cross-hair is visible and the click
        is inside the main viewbox with the left button.
        """
        if not self.cross_hair_visible:
            return
        if not event.button() == Qt.MouseButton.LeftButton:
            return

        if not hasattr(self, 'plotItem') or not hasattr(self.plotItem, 'vb') or self.plotItem.vb is None:
            return

        vb_rect = self.plotItem.vb.sceneBoundingRect()
        if vb_rect.isNull() or not vb_rect.isValid():
            return

        pos = event.scenePos()
        if not vb_rect.contains(pos):
            return

        try:
            view_pos = self.plotItem.vb.mapSceneToView(pos)
            x_val = view_pos.x()
            y1_val = view_pos.y()

            # Get Y2 value if available
            y2_val = float('nan')
            if self.y2_viewbox:
                try:
                    y2_view_pos = self.y2_viewbox.mapSceneToView(pos)
                    y2_val = y2_view_pos.y()
                except Exception:
                    pass

            # Convert to linear space for display before emitting
            display_x = self._log_to_linear(x_val) if self._x_log_mode else x_val
            display_y1 = self._log_to_linear(y1_val) if self._y1_log_mode else y1_val
            display_y2 = self._log_to_linear(y2_val) if self._y2_log_mode else y2_val

            # Emit signal: viewbox coords for mark rendering, linear for display
            self.mark_clicked.emit(x_val, y1_val, display_x, display_y1, display_y2)

        except Exception as e:
            self.logger.debug(f"Exception in _on_mouse_clicked: {e}")

    def _on_axis_log_mode_changed(self, orientation: str, log_mode: bool) -> None:
        """Handle log mode changes from LogAxisItem.

        Updates local log mode flags so that coordinate conversion in
        _on_mouse_moved and _on_mouse_clicked produces correct linear values.
        """
        if orientation == 'bottom':
            self._x_log_mode = log_mode
        elif orientation == 'left':
            self._y1_log_mode = log_mode
        elif orientation == 'right':
            self._y2_log_mode = log_mode

        self.axis_log_mode_changed.emit(orientation, log_mode)

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

    # --- ViewBox throttle: coalesce rapid pan/zoom into fewer paints ---

    def _throttled_vb_translateBy(self, *args, **kwargs):
        """Intercept ViewBox.translateBy and accumulate deltas."""
        # Extract dx, dy from any calling convention:
        # translateBy(t=(dx,dy)) / translateBy(x=dx, y=dy) / translateBy(dx, dy)
        t = kwargs.get('t', None)
        x = kwargs.get('x', None)
        y = kwargs.get('y', None)

        if not kwargs and args:
            # Pure positional: translateBy(dx, dy) or translateBy(Point)
            a0 = args[0]
            if isinstance(a0, (tuple, list)):
                t = a0
            elif hasattr(a0, 'x'):  # Point
                t = (a0.x(), a0.y())
            elif len(args) >= 2:
                x, y = args[0], args[1]
            else:
                x = args[0]

        dx = t[0] if t is not None else (x if x is not None else 0.0)
        dy = t[1] if t is not None else (y if y is not None else 0.0)

        if not self._vb_update_pending:
            self._vb_update_pending = True
            self._vb_queued_translate = (dx, dy)
            self._vb_update_timer.start()
        else:
            ox, oy = self._vb_queued_translate
            self._vb_queued_translate = (ox + dx, oy + dy)

    def _throttled_vb_scaleBy(self, *args, **kwargs):
        """Intercept ViewBox.scaleBy and coalesce rapid calls."""
        # Forward the last call's args as-is.  ScaleBy is only called by
        # mouse-wheel/zoom-box which fires far fewer events than pan-drag,
        # so accumulation matters much less.
        if not self._vb_update_pending:
            self._vb_update_pending = True
            self._vb_queued_call = ('scaleBy', args, kwargs)
            self._vb_update_timer.start()
        else:
            self._vb_queued_call = ('scaleBy', args, kwargs)

    def _flush_vb_updates(self):
        """Apply the accumulated view transform."""
        self._vb_update_pending = False

        # Apply accumulated translation
        if self._vb_queued_translate is not None:
            dx, dy = self._vb_queued_translate
            self._vb_queued_translate = None
            self._orig_vb_translateBy(x=dx, y=dy)

        # Apply queued scaleBy (if that was the last operation)
        if self._vb_queued_call is not None:
            name, args, kwargs = self._vb_queued_call
            self._vb_queued_call = None
            if name == 'translateBy':
                # Already handled via _vb_queued_translate above; ignore
                pass
            elif name == 'scaleBy':
                self._orig_vb_scaleBy(*args, **kwargs)