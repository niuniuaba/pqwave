#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AxisManager - Manages axis configuration, ranges, and log/linear mode.

This module provides a class that handles axis configuration including log/linear
mode, axis ranges, auto-ranging, and synchronization with plot widget and UI controls.
"""

import numpy as np
import pyqtgraph as pg
from typing import Optional, Tuple, Dict, Any
from PyQt6.QtCore import pyqtSignal, QObject

from pqwave.models.state import ApplicationState, AxisId, AxisConfig


class AxisManager(QObject):
    """Manages axis configuration and synchronization.

    Signals:
        axis_log_mode_changed(axis_id, log_mode): Emitted when axis log mode changes
        axis_range_changed(axis_id, min_val, max_val): Emitted when axis range changes
        axis_label_changed(axis_id, label): Emitted when axis label changes
    """

    axis_log_mode_changed = pyqtSignal(str, bool)  # axis_id, log_mode
    axis_range_changed = pyqtSignal(str, float, float)  # axis_id, min, max
    axis_label_changed = pyqtSignal(str, str)  # axis_id, label

    def __init__(self,
                 plot_widget: pg.PlotWidget,
                 application_state: ApplicationState):
        """
        Initialize AxisManager.

        Args:
            plot_widget: The PlotWidget instance to manage
            application_state: ApplicationState singleton for configuration storage
        """
        super().__init__()
        self.plot_widget = plot_widget
        self.state = application_state

        # Connect to plot widget signals
        self.plot_widget.axis_log_mode_changed.connect(self._on_axis_log_mode_changed)

        # Initialize axis configurations from application state
        self._initialize_axes()

    # Public API for axis configuration

    def set_axis_log_mode(self, axis_id: AxisId, log_mode: bool) -> None:
        """Set log mode for an axis.

        Args:
            axis_id: X, Y1, or Y2
            log_mode: True for log scale, False for linear
        """
        config = self.state.get_axis_config(axis_id)
        if config.log_mode == log_mode:
            return

        config.log_mode = log_mode

        # Update plot widget
        if axis_id == AxisId.X:
            self.plot_widget.set_axis_log_mode('X', log_mode)
        elif axis_id == AxisId.Y1:
            self.plot_widget.set_axis_log_mode('Y1', log_mode)
        elif axis_id == AxisId.Y2:
            self.plot_widget.set_axis_log_mode('Y2', log_mode)

        # Emit signal
        self.axis_log_mode_changed.emit(axis_id.value, log_mode)

    def set_axis_range(self,
                       axis_id: AxisId,
                       min_val: float,
                       max_val: float,
                       padding: float = 0.0) -> None:
        """Set range for an axis.

        Args:
            axis_id: X, Y1, or Y2
            min_val: Minimum value
            max_val: Maximum value
            padding: Padding factor (0-1) to add around data range
        """
        if min_val >= max_val:
            # Invalid range, use auto-range instead
            self.auto_range_axis(axis_id)
            return

        # Apply padding
        if padding > 0:
            range_padding = (max_val - min_val) * padding
            min_val -= range_padding
            max_val += range_padding

        # Update axis config
        config = self.state.get_axis_config(axis_id)
        config.range = (min_val, max_val)
        config.auto_range = False

        # Update plot widget
        if axis_id == AxisId.X:
            self.plot_widget.set_axis_range('X', min_val, max_val)
        elif axis_id == AxisId.Y1:
            self.plot_widget.set_axis_range('Y1', min_val, max_val)
        elif axis_id == AxisId.Y2:
            self.plot_widget.set_axis_range('Y2', min_val, max_val)

        # Emit signal
        self.axis_range_changed.emit(axis_id.value, min_val, max_val)

    def auto_range_axis(self, axis_id: AxisId) -> None:
        """Enable auto-ranging for an axis.

        Args:
            axis_id: X, Y1, or Y2
        """
        config = self.state.get_axis_config(axis_id)
        config.auto_range = True

        # Update plot widget
        if axis_id == AxisId.X:
            self.plot_widget.auto_range_axis('X')
        elif axis_id == AxisId.Y1:
            self.plot_widget.auto_range_axis('Y1')
        elif axis_id == AxisId.Y2:
            self.plot_widget.auto_range_axis('Y2')

        # Emit range changed signal with current range (plot widget will determine)
        # Note: We could get the actual range from plot widget, but for simplicity
        # we'll emit None values to indicate auto-range mode
        self.axis_range_changed.emit(axis_id.value, float('nan'), float('nan'))

    def set_axis_label(self, axis_id: AxisId, label: str) -> None:
        """Set label for an axis.

        Args:
            axis_id: X, Y1, or Y2
            label: Axis label text
        """
        config = self.state.get_axis_config(axis_id)
        config.label = label

        # Update plot widget
        if axis_id == AxisId.X:
            self.plot_widget.set_axis_label('X', label)
        elif axis_id == AxisId.Y1:
            self.plot_widget.set_axis_label('Y1', label)
        elif axis_id == AxisId.Y2:
            self.plot_widget.set_axis_label('Y2', label)

        # Emit signal
        self.axis_label_changed.emit(axis_id.value, label)

    def set_grid_visible(self, visible: bool) -> None:
        """Show/hide grid lines for all axes."""
        self.state.grid_visible = visible
        self.plot_widget.set_grid_visible(visible)

    def get_grid_visible(self) -> bool:
        """Get current grid visibility."""
        return self.state.grid_visible

    # Public API for data-driven auto-ranging

    def auto_range_x_from_data(self,
                               x_data: np.ndarray,
                               x_var_name: str = None) -> None:
        """Auto-range X-axis based on data.

        This method is called when new data is available (e.g., after loading
        a raw file or changing X-axis variable).

        Args:
            x_data: X-axis data array
            x_var_name: Optional variable name for logging
        """
        if x_data is None or len(x_data) == 0:
            return

        # Handle NaN values
        valid_data = x_data[~np.isnan(x_data)]
        if len(valid_data) == 0:
            return

        valid_data = np.real(valid_data)

        # Get current log mode
        config = self.state.get_axis_config(AxisId.X)
        log_mode = config.log_mode

        if log_mode:
            # Handle non-positive values for log scale
            mask = valid_data > 0
            if np.any(~mask):
                # Calculate a reasonable replacement value
                if np.any(mask):
                    min_positive = np.min(valid_data[mask])
                    replacement = min_positive * 1e-10
                else:
                    replacement = 1e-10
                valid_data = np.where(mask, valid_data, replacement)

            # Transform to log10 for log mode
            valid_data = np.log10(valid_data)

        min_val = np.min(valid_data)
        max_val = np.max(valid_data)

        # Add padding
        if log_mode:
            log_range = max_val - min_val
            log_padding = log_range * 0.05 if log_range > 0 else 0.1
            padded_min = min_val - log_padding
            padded_max = max_val + log_padding
        else:
            range_padding = (max_val - min_val) * 0.05 if max_val > min_val else 0.1
            padded_min = min_val - range_padding
            padded_max = max_val + range_padding

        # Update axis range
        self.set_axis_range(AxisId.X, padded_min, padded_max)

    def auto_range_y_from_traces(self,
                                 traces: list,
                                 axis_id: AxisId) -> None:
        """Auto-range Y-axis based on traces assigned to that axis.

        Args:
            traces: List of (var, plot_item, y_axis) tuples
            axis_id: Y1 or Y2 axis
        """
        if not traces:
            return

        y_min = float('inf')
        y_max = float('-inf')

        axis_str = axis_id.value
        for _, plot_item, y_axis in traces:
            if y_axis == axis_str:
                data = plot_item.getData()[1]
                if len(data) > 0:
                    # Handle NaN values
                    valid_data = data[~np.isnan(data)]
                    if len(valid_data) > 0:
                        # Get current log mode
                        config = self.state.get_axis_config(axis_id)
                        log_mode = config.log_mode

                        if log_mode:
                            # For logarithmic mode, use magnitude of complex data
                            valid_data = np.abs(valid_data)
                            # Handle non-positive values for log scale
                            mask = valid_data > 0
                            if np.any(~mask):
                                # Calculate a reasonable replacement value
                                if np.any(mask):
                                    min_positive = np.min(valid_data[mask])
                                    replacement = min_positive * 1e-10
                                else:
                                    replacement = 1e-10
                                valid_data = np.where(mask, valid_data, replacement)
                            # Transform to log10 for log mode
                            valid_data = np.log10(valid_data)

                        trace_min = np.min(valid_data)
                        trace_max = np.max(valid_data)

                        y_min = min(y_min, trace_min)
                        y_max = max(y_max, trace_max)

        if y_min == float('inf') or y_max == float('-inf'):
            return  # No traces on this axis

        # Add padding
        config = self.state.get_axis_config(axis_id)
        log_mode = config.log_mode

        if log_mode:
            log_range = y_max - y_min
            log_padding = log_range * 0.05 if log_range > 0 else 0.1
            padded_min = y_min - log_padding
            padded_max = y_max + log_padding
        else:
            range_padding = (y_max - y_min) * 0.05 if y_max > y_min else 0.1
            padded_min = y_min - range_padding
            padded_max = y_max + range_padding

        # Update axis range
        self.set_axis_range(axis_id, padded_min, padded_max)

    # Internal methods

    def _initialize_axes(self) -> None:
        """Initialize axes from application state."""
        for axis_id in AxisId:
            config = self.state.get_axis_config(axis_id)

            # Set log mode
            if axis_id == AxisId.X:
                self.plot_widget.set_axis_log_mode('X', config.log_mode)
            elif axis_id == AxisId.Y1:
                self.plot_widget.set_axis_log_mode('Y1', config.log_mode)
            elif axis_id == AxisId.Y2:
                self.plot_widget.set_axis_log_mode('Y2', config.log_mode)

            # Set label
            if config.label:
                if axis_id == AxisId.X:
                    self.plot_widget.set_axis_label('X', config.label)
                elif axis_id == AxisId.Y1:
                    self.plot_widget.set_axis_label('Y1', config.label)
                elif axis_id == AxisId.Y2:
                    self.plot_widget.set_axis_label('Y2', config.label)

            # Set range if specified
            if config.range and not config.auto_range:
                min_val, max_val = config.range
                if axis_id == AxisId.X:
                    self.plot_widget.set_axis_range('X', min_val, max_val)
                elif axis_id == AxisId.Y1:
                    self.plot_widget.set_axis_range('Y1', min_val, max_val)
                elif axis_id == AxisId.Y2:
                    self.plot_widget.set_axis_range('Y2', min_val, max_val)

        # Set grid visibility
        self.plot_widget.set_grid_visible(self.state.grid_visible)

    def _on_axis_log_mode_changed(self, orientation: str, log_mode: bool) -> None:
        """Handle log mode changes from LogAxisItem via PlotWidget.

        Args:
            orientation: 'bottom', 'left', or 'right'
            log_mode: True for log scale, False for linear
        """
        # Map orientation to axis ID
        if orientation == 'bottom':
            axis_id = AxisId.X
        elif orientation == 'left':
            axis_id = AxisId.Y1
        elif orientation == 'right':
            axis_id = AxisId.Y2
        else:
            return

        # Update application state
        config = self.state.get_axis_config(axis_id)
        config.log_mode = log_mode

        # Emit signal
        self.axis_log_mode_changed.emit(axis_id.value, log_mode)