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
from PyQt6.QtWidgets import QApplication, QGraphicsTextItem, QInputDialog
from PyQt6.QtGui import QColor, QPainter, QFont
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QEvent

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
        cursor_xa_changed(value): Emitted when XA cursor position changes
        cursor_xb_changed(value): Emitted when XB cursor position changes
        cursor_yA_changed(value): Emitted when YA cursor position changes
        cursor_yB_changed(value): Emitted when YB cursor position changes
        cursor_y2_changed(value): Emitted when Y2 axis cursor position changes
        mark_clicked(x, y1, y2): Emitted when user clicks to place a mark
    """

    logger = get_logger(__name__)

    mouse_moved = pyqtSignal(float, float, float)  # x, y1, y2
    mouse_left = pyqtSignal()
    cursor_xa_changed = pyqtSignal(float)
    cursor_xb_changed = pyqtSignal(float)
    cursor_yA_changed = pyqtSignal(float)
    cursor_yB_changed = pyqtSignal(float)
    cursor_y2_changed = pyqtSignal(float)
    axis_log_mode_changed = pyqtSignal(str, bool)  # orientation, log_mode
    mark_clicked = pyqtSignal(float, float, float, float, float)  # x_vb, y1_vb, x_linear, y1_linear, y2_linear
    title_changed = pyqtSignal(str)

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

        # Disable pyqtgraph built-in context menus ("Plot Options" and
        # "ViewBox options").  These expose generic transforms (FFT, dy/dx,
        # subtract mean, log axes, etc.) that clash with pqwave's custom
        # log-mode architecture and confuse EDA users expecting LTspice/QSPICE
        # behaviour.  pqwave will provide its own EDA-appropriate analysis
        # features later.
        self.getPlotItem().setMenuEnabled(False)
        self.getPlotItem().vb.setMenuEnabled(False)

        # Enable mouse tracking for the widget
        self.setMouseTracking(True)

        # Initialize attributes
        self.y2_viewbox: Optional[pg.ViewBox] = None
        self.right_axis: Optional[pg.AxisItem] = None
        self.cross_hair_vline: Optional[pg.InfiniteLine] = None
        self.cross_hair_hline: Optional[pg.InfiniteLine] = None
        self.cursor_xa_line: Optional[pg.InfiniteLine] = None
        self.cursor_xb_line: Optional[pg.InfiniteLine] = None
        self.cursor_yA_line: Optional[pg.InfiniteLine] = None
        self.cursor_yB_line: Optional[pg.InfiniteLine] = None
        self.cursor_y2_line: Optional[pg.InfiniteLine] = None

        # Cursor visibility and drag state
        self.cross_hair_visible = False
        self.cursor_xa_visible = False
        self.cursor_xb_visible = False
        self.cursor_yA_visible = False
        self.cursor_yB_visible = False
        self.cursor_y2_visible = False

        # Cursor selection for keyboard movement
        self._selected_x_cursor: Optional[str] = None  # 'xa' or 'xb'
        self._selected_y_cursor: Optional[str] = None  # 'yA' or 'yB'

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

        # Set default plot title (reminds users they can customize it)
        self.plotItem.setTitle("Title")

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

    # --- X/Y Cursor line visibility ---

    def set_cursor_xa_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide XA cursor line."""
        self.cursor_xa_visible = visible
        if self.cursor_xa_line:
            self.cursor_xa_line.setVisible(visible)
            if position is not None:
                self.cursor_xa_line.setValue(position)
            elif visible:
                x_range = self.plotItem.vb.viewRange()[0]
                self.cursor_xa_line.setValue(sum(x_range) / 2)

    def set_cursor_xb_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide XB cursor line (offset from center if no position given)."""
        self.cursor_xb_visible = visible
        if self.cursor_xb_line:
            self.cursor_xb_line.setVisible(visible)
            if position is not None:
                self.cursor_xb_line.setValue(position)
            elif visible:
                x_range = self.plotItem.vb.viewRange()[0]
                center = sum(x_range) / 2
                offset = (x_range[1] - x_range[0]) * 0.1
                self.cursor_xb_line.setValue(center + offset)

    def set_cursor_yA_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide YA cursor line."""
        self.cursor_yA_visible = visible
        if self.cursor_yA_line:
            self.cursor_yA_line.setVisible(visible)
            if position is not None:
                self.cursor_yA_line.setValue(position)
            elif visible:
                y_range = self.plotItem.vb.viewRange()[1]
                self.cursor_yA_line.setValue(sum(y_range) / 2)

    def set_cursor_yB_visible(self, visible: bool, position: Optional[float] = None) -> None:
        """Show/hide YB cursor line (offset from center if no position given)."""
        self.cursor_yB_visible = visible
        if self.cursor_yB_line:
            self.cursor_yB_line.setVisible(visible)
            if position is not None:
                self.cursor_yB_line.setValue(position)
            elif visible:
                y_range = self.plotItem.vb.viewRange()[1]
                center = sum(y_range) / 2
                offset = (y_range[1] - y_range[0]) * 0.1
                self.cursor_yB_line.setValue(center + offset)

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

    # --- Cursor position and delta queries ---

    def get_cursor_positions(self) -> dict:
        """Get all cursor positions.

        Returns:
            dict with keys: x1, x2, ya, yb, y2 (None if invisible/not created)
        """
        def _val(line, visible):
            return line.value() if line is not None and visible else None
        return {
            'xa': _val(self.cursor_xa_line, self.cursor_xa_visible),
            'xb': _val(self.cursor_xb_line, self.cursor_xb_visible),
            'yA': _val(self.cursor_yA_line, self.cursor_yA_visible),
            'yB': _val(self.cursor_yB_line, self.cursor_yB_visible),
            'y2': _val(self.cursor_y2_line, self.cursor_y2_visible),
        }

    def set_xa_cursor_position(self, value: float) -> None:
        """Set XA cursor line position without emitting signals (for cross-panel sync)."""
        if self.cursor_xa_line is not None:
            self.cursor_xa_line.blockSignals(True)
            self.cursor_xa_line.setValue(value)
            self.cursor_xa_line.blockSignals(False)

    def set_xb_cursor_position(self, value: float) -> None:
        """Set XB cursor line position without emitting signals (for cross-panel sync)."""
        if self.cursor_xb_line is not None:
            self.cursor_xb_line.blockSignals(True)
            self.cursor_xb_line.setValue(value)
            self.cursor_xb_line.blockSignals(False)

    def get_cursor_deltas(self) -> dict:
        """Compute delta values between paired cursors.

        For Y cursors, also compute Y2-space deltas when Y2 viewbox exists.
        Returns dict with keys: dx, dy1, dy2 (None if pair not active).
        """
        positions = self.get_cursor_positions()
        result = {'dx': None, 'dy1': None, 'dy2': None}

        # Helper: convert viewbox coord to linear if axis in log mode
        def _lin(val, log_mode):
            return self._log_to_linear(val) if log_mode else val

        # Delta X (always linear space for display)
        if positions['xa'] is not None and positions['xb'] is not None:
            x1_lin = _lin(positions['xa'], self._x_log_mode)
            x2_lin = _lin(positions['xb'], self._x_log_mode)
            result['dx'] = abs(x2_lin - x1_lin)

        # Delta Y1
        if positions['yA'] is not None and positions['yB'] is not None:
            ya_lin = _lin(positions['yA'], self._y1_log_mode)
            yb_lin = _lin(positions['yB'], self._y1_log_mode)
            result['dy1'] = abs(yb_lin - ya_lin)

        # Delta Y2 — map YA/YB through scene coords to Y2 viewbox
        if (result['dy1'] is not None and self.y2_viewbox is not None
                and positions['yA'] is not None and positions['yB'] is not None):
            try:
                from PyQt6.QtCore import QPointF
                vb = self.plotItem.vb
                scene_ya = vb.mapViewToScene(QPointF(0, positions['yA']))
                scene_yb = vb.mapViewToScene(QPointF(0, positions['yB']))
                y2_ya = self.y2_viewbox.mapSceneToView(scene_ya).y()
                y2_yb = self.y2_viewbox.mapSceneToView(scene_yb).y()
                y2_ya_lin = _lin(y2_ya, self._y2_log_mode)
                y2_yb_lin = _lin(y2_yb, self._y2_log_mode)
                result['dy2'] = abs(y2_yb_lin - y2_ya_lin)
            except Exception:
                pass

        return result

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
        self.right_axis.setLogMode(y=self._y2_log_mode)

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
        elif axis == 'Y2':
            self._y2_log_mode = log_mode
            if self.right_axis:
                self.right_axis.setLogMode(y=log_mode)

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

    def get_axis_log_mode(self, axis: str) -> bool:
        """Get log mode for an axis.

        Args:
            axis: 'X', 'Y1', or 'Y2'

        Returns:
            True if axis is in log mode, False otherwise
        """
        if axis == 'X':
            return self._x_log_mode
        elif axis == 'Y1':
            return self._y1_log_mode
        elif axis == 'Y2':
            return self._y2_log_mode
        else:
            raise ValueError(f"Invalid axis: {axis}")

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
        """Auto-range a single axis while preserving the other axis range.

        For X axis: after auto-ranging, autoRange is disabled so that
        clipToView on PlotDataItem can work (pyqtgraph skips clipping
        when autoRange is enabled). This matches xschem's behavior where
        the view only changes on explicit user action.

        Note: InfiniteLine cursors (Xa/Xb, Ya/Yb, cross-hair) are excluded
        from range calculation so cursor placement before traces are loaded
        doesn't corrupt auto-range.

        Uses vb.autoRange() directly (same mechanism as pyqtgraph's context
        menu), but explicitly disables auto-range on the non-target axis
        so only the target axis is adjusted.
        """
        vb = self.plotItem.vb
        if axis == 'X':
            items = [it for it in vb.addedItems
                     if not isinstance(it, pg.InfiniteLine)]
            if not items:
                return
            vb.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            vb.enableAutoRange(x=True, y=False)
            vb.autoRange(padding=0.05, items=items)
            vb.enableAutoRange(x=False)
        elif axis == 'Y1':
            items = [it for it in vb.addedItems
                     if not isinstance(it, pg.InfiniteLine)]
            if not items:
                return
            vb.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            vb.enableAutoRange(x=False, y=True)
            vb.autoRange(padding=0.05, items=items)
        elif axis == 'Y2' and self.y2_viewbox:
            y2vb = self.y2_viewbox
            items = [it for it in y2vb.addedItems
                     if not isinstance(it, pg.InfiniteLine)]
            if not items:
                return
            y2vb.setLimits(xMin=None, xMax=None, yMin=None, yMax=None)
            y2vb.enableAutoRange(y=True)
            y2vb.autoRange(padding=0.05, items=items)

    # Grid control

    def set_grid_visible(self, visible: bool) -> None:
        """Show/hide grid lines with dot-line style."""
        # Grid line style (DashLine) is handled by LogAxisItem.generateDrawSpecs.
        # Here we only toggle visibility via setGrid(), which properly
        # invalidates the QPicture cache.  Directly setting axis.grid would
        # bypass the cache-invalidation logic and the toggle would appear
        # broken until the next resize/repaint.
        grid_val = 76 if visible else False  # 76 ≈ 0.3 * 255

        for axis_name in ('bottom', 'left'):
            axis = self.getAxis(axis_name)
            if axis:
                axis.setGrid(grid_val)

        if self.right_axis:
            self.right_axis.setGrid(grid_val)

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

    # --- Font application ---

    def apply_fonts(self, state: 'ApplicationState') -> None:
        """Apply all font configurations from ApplicationState to plot elements."""
        colors = THEME_COLORS[self._current_theme]
        fg_color = colors['foreground']

        def _resolve(fc) -> str:
            return fc.color if fc.color else fg_color

        # -- Plot Title (pyqtgraph LabelItem) --
        if self.plotItem.titleLabel:
            opts = self.plotItem.titleLabel.opts
            opts['color'] = _resolve(state.title_font)
            if state.title_font.family:
                opts['family'] = state.title_font.family
            else:
                opts.pop('family', None)
            if state.title_font.size > 0:
                opts['size'] = f'{state.title_font.size}pt'
            else:
                opts.pop('size', None)
            title_text = self.plotItem.titleLabel.text
            if title_text:
                self.plotItem.titleLabel.setText(title_text)

        # -- Axis Labels (QGraphicsTextItem + labelStyle color) --
        for axis_name in ('bottom', 'left', 'right'):
            axis = self.getAxis(axis_name)
            if axis and hasattr(axis, 'label') and axis.label:
                color = _resolve(state.label_font)
                axis.labelStyle['color'] = color

                font = QFont()
                default_font = QFont()
                if state.label_font.family:
                    font.setFamily(state.label_font.family)
                else:
                    font.setFamily(default_font.family())
                if state.label_font.size > 0:
                    font.setPointSize(state.label_font.size)
                else:
                    font.setPointSize(default_font.pointSize())
                axis.label.setFont(font)
                axis._updateLabel()

        # -- Tick Labels --
        tick_color = _resolve(state.tick_font)
        for axis_name in ('bottom', 'left', 'right'):
            axis = self.getAxis(axis_name)
            if axis:
                if state.tick_font.family or state.tick_font.size > 0:
                    tick_font = QFont()
                    if state.tick_font.family:
                        tick_font.setFamily(state.tick_font.family)
                    if state.tick_font.size > 0:
                        tick_font.setPointSize(state.tick_font.size)
                    axis.setTickFont(tick_font)
                else:
                    axis.setTickFont(None)
                axis.setTextPen(tick_color)

    def _create_cursors(self) -> None:
        """Create cursor lines."""
        # Cross-hair lines (non-interactive)
        self.cross_hair_vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', width=1, style=Qt.PenStyle.DashLine))
        self.cross_hair_hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('gray', width=1, style=Qt.PenStyle.DashLine))
        self.cross_hair_vline.setVisible(False)
        self.cross_hair_hline.setVisible(False)
        self.plotItem.addItem(self.cross_hair_vline)
        self.plotItem.addItem(self.cross_hair_hline)

        # XA cursor line (draggable, vertical, cyan solid)
        self.cursor_xa_line = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen('cyan', width=2))
        self.cursor_xa_line.setVisible(False)
        self.plotItem.addItem(self.cursor_xa_line)
        self.cursor_xa_line.sigPositionChanged.connect(
            lambda line: self._on_cursor_dragged('xa', line)
        )

        # XB cursor line (draggable, vertical, orange dash)
        self.cursor_xb_line = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen('orange', width=2, style=Qt.PenStyle.DashLine))
        self.cursor_xb_line.setVisible(False)
        self.plotItem.addItem(self.cursor_xb_line)
        self.cursor_xb_line.sigPositionChanged.connect(
            lambda line: self._on_cursor_dragged('xb', line)
        )

        # YA cursor line (draggable, horizontal, yellow solid)
        self.cursor_yA_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen('yellow', width=2))
        self.cursor_yA_line.setVisible(False)
        self.plotItem.addItem(self.cursor_yA_line)
        self.cursor_yA_line.sigPositionChanged.connect(
            lambda line: self._on_cursor_dragged('yA', line)
        )

        # YB cursor line (draggable, horizontal, lime dash)
        self.cursor_yB_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen('lime', width=2, style=Qt.PenStyle.DashLine))
        self.cursor_yB_line.setVisible(False)
        self.plotItem.addItem(self.cursor_yB_line)
        self.cursor_yB_line.sigPositionChanged.connect(
            lambda line: self._on_cursor_dragged('yB', line)
        )

        # Y2 cursor line will be created when Y2 axis is enabled

    def _on_cursor_dragged(self, cursor_name: str, line: pg.InfiniteLine) -> None:
        """Called when a cursor is dragged by the user.

        Updates the selected-cursor tracking and emits the appropriate signal.
        """
        value = line.value()
        if cursor_name == 'xa':
            self._selected_x_cursor = 'xa'
            self.cursor_xa_changed.emit(value)
        elif cursor_name == 'xb':
            self._selected_x_cursor = 'xb'
            self.cursor_xb_changed.emit(value)
        elif cursor_name == 'yA':
            self._selected_y_cursor = 'yA'
            self.cursor_yA_changed.emit(value)
        elif cursor_name == 'yB':
            self._selected_y_cursor = 'yB'
            self.cursor_yB_changed.emit(value)

    def _check_cursor_click(self, scene_pos) -> None:
        """Check if a mouse click is near a visible cursor line and select it.

        Uses pixel-space distance so hit detection works regardless of zoom level.
        """
        from PyQt6.QtCore import QPointF

        threshold_px = 10.0
        vb = self.plotItem.vb

        # Check X cursors (vertical lines) — use horizontal distance
        for name, line, visible in [
            ('xa', self.cursor_xa_line, self.cursor_xa_visible),
            ('xb', self.cursor_xb_line, self.cursor_xb_visible),
        ]:
            if line is not None and visible:
                try:
                    line_scene = vb.mapViewToScene(QPointF(line.value(), 0))
                    if abs(scene_pos.x() - line_scene.x()) < threshold_px:
                        self._selected_x_cursor = name
                        return
                except Exception:
                    continue

        # Check Y cursors (horizontal lines) — use vertical distance
        for name, line, visible in [
            ('yA', self.cursor_yA_line, self.cursor_yA_visible),
            ('yB', self.cursor_yB_line, self.cursor_yB_visible),
        ]:
            if line is not None and visible:
                try:
                    line_scene = vb.mapViewToScene(QPointF(0, line.value()))
                    if abs(scene_pos.y() - line_scene.y()) < threshold_px:
                        self._selected_y_cursor = name
                        return
                except Exception:
                    continue

    def select_x_cursor(self, name: str) -> None:
        """Set which X cursor is selected for keyboard movement."""
        self._selected_x_cursor = name

    def select_y_cursor(self, name: str) -> None:
        """Set which Y cursor is selected for keyboard movement."""
        self._selected_y_cursor = name

    def move_selected_cursor(self, direction: str) -> None:
        """Move the selected cursor by one screen pixel.

        Args:
            direction: 'left', 'right', 'up', or 'down'

        The step size = view_range / viewport_pixel_size, giving pixel-level
        precision regardless of zoom level.  Works correctly in log mode
        since the ViewBox coordinate space is linear (data is pre-transformed
        by TraceManager).
        """
        vb = self.plotItem.vb
        view_rect = vb.sceneBoundingRect()
        if view_rect.isNull() or not view_rect.isValid():
            return
        pixel_width = view_rect.width()
        pixel_height = view_rect.height()
        if pixel_width < 1 or pixel_height < 1:
            return

        x_range = vb.viewRange()[0]
        y_range = vb.viewRange()[1]

        dx = (x_range[1] - x_range[0]) / pixel_width if pixel_width > 0 else 0
        dy = (y_range[1] - y_range[0]) / pixel_height if pixel_height > 0 else 0

        if direction in ('left', 'right'):
            if self._selected_x_cursor == 'xa' and self.cursor_xa_line and self.cursor_xa_visible:
                cur = self.cursor_xa_line.value()
                step = -dx if direction == 'left' else dx
                self.cursor_xa_line.setValue(cur + step)
                self.cursor_xa_changed.emit(cur + step)
            elif self._selected_x_cursor == 'xb' and self.cursor_xb_line and self.cursor_xb_visible:
                cur = self.cursor_xb_line.value()
                step = -dx if direction == 'left' else dx
                self.cursor_xb_line.setValue(cur + step)
                self.cursor_xb_changed.emit(cur + step)
            else:
                # No X cursor selected — see if exactly one is visible and auto-select
                self._auto_select_x_cursor()
                if self._selected_x_cursor:
                    self.move_selected_cursor(direction)
        elif direction in ('up', 'down'):
            target = self._selected_y_cursor
            if self._selected_y_cursor == 'yA' and self.cursor_yA_line and self.cursor_yA_visible:
                cur = self.cursor_yA_line.value()
                step = dy if direction == 'up' else -dy  # up → increase Y
                self.cursor_yA_line.setValue(cur + step)
                self.cursor_yA_changed.emit(cur + step)
            elif self._selected_y_cursor == 'yB' and self.cursor_yB_line and self.cursor_yB_visible:
                cur = self.cursor_yB_line.value()
                step = dy if direction == 'up' else -dy
                self.cursor_yB_line.setValue(cur + step)
                self.cursor_yB_changed.emit(cur + step)
            else:
                self._auto_select_y_cursor()
                if self._selected_y_cursor:
                    self.move_selected_cursor(direction)

    def _auto_select_x_cursor(self) -> None:
        """Auto-select the sole visible X cursor (or do nothing if ambiguous)."""
        xa_vis = self.cursor_xa_line is not None and self.cursor_xa_visible
        xb_vis = self.cursor_xb_line is not None and self.cursor_xb_visible
        if xa_vis and not xb_vis:
            self._selected_x_cursor = 'xa'
        elif xb_vis and not xa_vis:
            self._selected_x_cursor = 'xb'
        # If both visible or neither visible, leave current selection

    def _auto_select_y_cursor(self) -> None:
        """Auto-select the sole visible Y cursor (or do nothing if ambiguous)."""
        yA_vis = self.cursor_yA_line is not None and self.cursor_yA_visible
        yB_vis = self.cursor_yB_line is not None and self.cursor_yB_visible
        if yA_vis and not yB_vis:
            self._selected_y_cursor = 'yA'
        elif yB_vis and not yA_vis:
            self._selected_y_cursor = 'yB'

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
        """Handle mouse clicks for cursor selection and mark placement.

        Left-clicking near a cursor line selects it for keyboard movement.
        When cross-hair is visible, left-click inside the viewbox also
        places a measurement mark.
        """
        # Always check for cursor line clicks first (selection)
        if event.button() == Qt.MouseButton.LeftButton:
            self._check_cursor_click(event.scenePos())

        # Then handle mark placement (only when cross-hair is visible)
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

    # --- Double-click title / axis labels to edit ---

    def mouseDoubleClickEvent(self, event):
        """Detect double-clicks on plot title and axis labels for in-place editing."""
        scene_pos = self.mapToScene(event.pos())
        items = self.scene().items(scene_pos)

        for item in items:
            # Title label
            if item is self.plotItem.titleLabel:
                self._edit_title()
                return

            # Axis labels
            if isinstance(item, QGraphicsTextItem):
                for axis_name in ('bottom', 'left'):
                    axis = self.getAxis(axis_name)
                    if item is getattr(axis, 'label', None):
                        self._edit_axis_label(axis_name)
                        return
                if self.right_axis and item is getattr(self.right_axis, 'label', None):
                    self._edit_axis_label('right')
                    return

        super().mouseDoubleClickEvent(event)

    def _edit_title(self) -> None:
        """Show a dialog to edit the plot title."""
        current = self.get_plot_title()
        new_title, ok = QInputDialog.getText(
            self, "Edit Title", "Plot title:",
            text=current if current != "Title" else ""
        )
        if ok:
            final = new_title.strip()
            self.set_plot_title(final)
            self.title_changed.emit(final)

    def _edit_axis_label(self, axis_name: str) -> None:
        """Show a dialog to edit an axis label."""
        axis = self.getAxis(axis_name)
        if not axis:
            return
        current = axis.labelText or ""
        axis_title = {'bottom': 'X Axis', 'left': 'Y1 Axis', 'right': 'Y2 Axis'}.get(axis_name, axis_name)
        axis_id = {'bottom': 'X', 'left': 'Y1', 'right': 'Y2'}[axis_name]
        new_label, ok = QInputDialog.getText(
            self, f"Edit {axis_title} Label", f"{axis_title} label:",
            text=current
        )
        if ok:
            final = new_label.strip()
            self.set_axis_label(axis_id, final)

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