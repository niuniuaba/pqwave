#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TraceManager - Handles trace lifecycle, color assignment, and legend management.

This module provides a class that manages the addition, removal, and updating
of traces in the plot, including color assignment and legend synchronization.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore
from PyQt6.QtGui import QColor
from typing import Optional, List, Tuple

from pqwave.models.state import ApplicationState
from pqwave.models.trace import Trace, AxisAssignment
from pqwave.models.expression import ExprEvaluator
from pqwave.utils.colors import ColorManager
from pqwave.logging_config import get_logger

# Pre-downsample target: 2x typical screen width.  This gives good visual
# quality for moderate zoom-in while keeping per-paint overhead low.
DOWNSAMPLE_TARGET = 1600


class _StaticCurveItem(pg.PlotCurveItem):
    """PlotCurveItem that caches its bounding rect between setData() calls.

    pyqtgraph's default behaviour is to call dataBounds(nanmin/nanmax) on
    every paint event because viewTransformChanged invalidates the bounds
    cache.  This subclass skips that invalidation during normal pan/zoom
    (data never changes), but clears the cache when setData() is called
    (e.g. during log mode toggle).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._boundingRect = None

    def viewTransformChanged(self):
        # Do NOT invalidate bounds cache during pan/zoom — data is stable.
        # The default calls invalidateBounds() which forces nanmin/nanmax
        # on every paint.  We skip it entirely.
        pass

    def setData(self, *args, **kwargs):
        # Clear cached bounds when data changes (e.g. log mode toggle)
        self._boundingRect = None
        super().setData(*args, **kwargs)

    def boundingRect(self):
        if self._boundingRect is None:
            # Compute once and cache until next setData()
            (xmn, xmx) = self.dataBounds(ax=0)
            if xmn is None or xmx is None:
                return QtCore.QRectF()
            (ymn, ymx) = self.dataBounds(ax=1)
            if ymn is None or ymx is None:
                return QtCore.QRectF()
            self._boundingRect = QtCore.QRectF(xmn, ymn, xmx - xmn, ymx - ymn)
        return self._boundingRect


from PyQt6 import QtCore


class TraceManager:
    """Manages trace lifecycle, color assignment, and legend updates."""

    logger = get_logger(__name__)

    def __init__(self,
                 plot_widget: pg.PlotWidget,
                 legend: pg.LegendItem,
                 application_state: ApplicationState,
                 color_manager: Optional[ColorManager] = None):
        """
        Initialize TraceManager.

        Args:
            plot_widget: The PlotWidget instance for visual representation
            legend: The LegendItem for trace labels
            application_state: ApplicationState singleton for data management
            color_manager: ColorManager instance for color assignment (creates default if None)
        """
        self.plot_widget = plot_widget
        self.legend = legend
        self.state = application_state
        self.color_manager = color_manager or ColorManager()

        # References to plot components for Y2 axis
        self.y2_viewbox = None  # Will be set when Y2 axis is enabled
        self.right_axis = None

        # Internal state
        self.traces: List[Tuple[str, pg.PlotCurveItem, str]] = []  # (var, plot_item, y_axis)
        self.raw_file = None
        self.current_dataset = 0

        # Log mode flags (should be synchronized with axis configuration)
        self.x_log = False
        self.y1_log = False
        self.y2_log = False

    # Public API

    def set_raw_file(self, raw_file) -> None:
        """Set the current raw file for trace evaluation."""
        self.raw_file = raw_file

    def set_current_dataset(self, dataset_idx: int) -> None:
        """Set the current dataset index."""
        self.current_dataset = dataset_idx

    def set_log_modes(self, x_log: bool, y1_log: bool, y2_log: bool) -> None:
        """Update log mode flags."""
        self.x_log = x_log
        self.y1_log = y1_log
        self.y2_log = y2_log

    def add_trace(self,
                  expression: str,
                  x_var_name: str,
                  y_axis: AxisAssignment = AxisAssignment.Y1,
                  custom_color: Optional[Tuple[int, int, int]] = None,
                  error_out: Optional[list] = None) -> Optional[Trace]:
        """Add a trace for the given expression.

        Args:
            expression: Expression string (e.g., 'v(out)' or 'v(out) v(in)')
            x_var_name: Name of X-axis variable
            y_axis: Which Y axis to plot on (Y1 or Y2)
            custom_color: Optional custom color as RGB tuple (0-255)
            error_out: Optional list to receive error messages if trace fails

        Returns:
            Trace object if successful, None otherwise.
        """
        self.logger.debug(f"add_trace called: expression={expression}, x_var_name={x_var_name}, y_axis={y_axis}")
        # Initialize error_out list if provided
        if error_out is not None:
            error_out.clear()

        if not self.raw_file:
            error_msg = "No raw file opened"
            self.logger.warning(error_msg)
            if error_out is not None:
                error_out.append(error_msg)
            return None

        expr = expression.strip()
        if not expr:
            error_msg = "Empty expression"
            self.logger.warning(error_msg)
            if error_out is not None:
                error_out.append(error_msg)
            return None

        try:
            self.logger.debug(f"Adding trace for expression: {expr}")
            var_names = self.raw_file.get_variable_names(self.current_dataset)
            self.logger.debug(f"Available variables: {var_names}")

            n_points = self.raw_file.get_num_points(self.current_dataset)
            self.logger.debug(f"Number of points: {n_points}")

            # Split the expression into individual variables/expressions
            variables = self.split_expressions(expr)
            self.logger.debug(f"Split expressions: {variables}")

            if not x_var_name:
                error_msg = "No X-axis variable selected"
                self.logger.warning(error_msg)
                if error_out is not None:
                    error_out.append(error_msg)
                return None
            x_var = x_var_name
            self.logger.debug(f"X-axis variable: {x_var}")

            x_data = self.raw_file.get_variable_data(x_var, self.current_dataset)
            if x_data is not None:
                self.logger.debug(f"X data length: {len(x_data)}")

                traces_added = []

                for var in variables:
                    evaluator = ExprEvaluator(self.raw_file, self.current_dataset)
                    self.logger.debug(f"Created evaluator for {var}")

                    y_data = evaluator.evaluate(var)
                    self.logger.debug(f"Evaluated expression {var}, result length: {len(y_data)}")

                    # Check if X and Y data have the same length
                    if len(x_data) != len(y_data):
                        self.logger.error(f"X and Y data length mismatch!")
                        self.logger.error(f"    X data length: {len(x_data)}")
                        self.logger.error(f"    Y data length: {len(y_data)}")
                        self.logger.warning(f"    Skipping trace for {var}")
                        continue

                    # Get color
                    if custom_color is not None:
                        color = custom_color
                        self.logger.debug(f"  Using custom color: {color}")
                    else:
                        color = self.color_manager.get_next_color()
                        self.logger.debug(f"  Using auto-assigned color: {color}")

                    # Create trace model
                    trace = Trace(
                        name=var,
                        expression=var,
                        x_data=x_data,
                        y_data=y_data,
                        y_axis=y_axis,
                        color=color,
                        line_width=1.0,
                        dataset_idx=self.current_dataset
                    )

                    # Add trace to application state
                    self.state.add_trace(trace)

                    # Create visual representation
                    plot_item = self._create_plot_item(trace)

                    # Store reference
                    self.traces.append((var, plot_item, y_axis.value))
                    traces_added.append(trace)

                    self.logger.info(f"Added trace: {var} on {y_axis.value}")

                # Auto-range the appropriate Y axis
                self._auto_range_y_axis(y_axis)

                # Also auto-range X axis to match the new data
                self._auto_range_x()

                # Clear the trace expression input box (should be done by caller)
                # Return the first trace if any were added
                if traces_added:
                    return traces_added[0]
                else:
                    error_msg = "No valid variables found in expression"
                    self.logger.warning(error_msg)
                    if error_out is not None:
                        error_out.append(error_msg)
                    return None

            else:
                error_msg = f"No data for X variable: {x_var}"
                self.logger.error(error_msg)
                if error_out is not None:
                    error_out.append(error_msg)
                return None

        except Exception as e:
            error_msg = f"Error adding trace: {e}"
            self.logger.error(error_msg)
            import traceback
            self.logger.exception("Error adding trace")
            if error_out is not None:
                error_out.append(error_msg)
            return None

    def add_trace_from_variable(self,
                                variable_name: str,
                                x_var_name: str,
                                y_axis: AxisAssignment = AxisAssignment.Y1,
                                custom_color: Optional[Tuple[int, int, int]] = None,
                                error_out: Optional[list] = None) -> Optional[Trace]:
        """Add a trace for a single variable name.

        Convenience method for adding traces from combo box selections.

        Args:
            variable_name: Name of variable to trace
            x_var_name: Name of X-axis variable
            y_axis: Which Y axis to plot on (Y1 or Y2)
            custom_color: Optional custom color as RGB tuple (0-255)
            error_out: Optional list to receive error messages if trace fails

        Returns:
            Trace object if successful, None otherwise.
        """
        # Quote the variable name to treat it as a literal
        self.logger.debug(f"add_trace_from_variable: variable_name={variable_name}, x_var_name={x_var_name}")
        quoted_var = f'"{variable_name}"'
        return self.add_trace(quoted_var, x_var_name, y_axis, custom_color, error_out)

    def clear_traces(self) -> None:
        """Clear all traces from plot and application state."""
        self.logger.debug(f"clear_traces called, current traces count: {len(self.traces)}")
        # import traceback
        # traceback.print_stack()  # Debug statement removed for test stability
        # Clear traces from viewboxes
        for _, plot_item, y_axis in self.traces:
            if y_axis == "Y2" and self.y2_viewbox:
                self.y2_viewbox.removeItem(plot_item)
            else:
                self.plot_widget.plotItem.vb.removeItem(plot_item)

        # Clear legend items
        if self.legend:
            items = list(self.legend.items)
            self.logger.debug(f"  Clearing {len(items)} items from legend")
            for item in items:
                try:
                    self.legend.removeItem(item)
                except Exception as e:
                    self.logger.error(f"    Error removing legend item: {e}")
            # Also try clear() method
            try:
                self.legend.clear()
            except Exception as e:
                self.logger.error(f"    Error clearing legend: {e}")

        # Reset traces list
        self.traces = []

        # Reset color manager
        self.color_manager.reset()

        # Clear traces from application state
        self.state.clear_traces()

        # Remove right axis and y2 viewbox references
        # Note: This should be handled by axis manager, but we clean up our references
        if self.right_axis:
            # Hide right axis
            self.plot_widget.hideAxis('right')
            self.right_axis = None
        if self.y2_viewbox:
            # Remove y2_viewbox from scene
            try:
                self.plot_widget.scene().removeItem(self.y2_viewbox)
            except Exception:
                pass
            self.y2_viewbox = None

        # Reset log mode flags for fresh start
        self.x_log = False
        self.y1_log = False
        self.y2_log = False

    def remove_trace_by_variable_name(self, variable_name: str) -> bool:
        """Remove a trace by variable name (unquoted or quoted).

        Args:
            variable_name: Variable name (e.g., 'v(out)') or quoted version.

        Returns:
            True if trace was removed, False if not found.
        """
        # Try to match variable name as-is (could be quoted or unquoted)
        target_var = variable_name.strip()
        # Also generate quoted version for matching
        quoted_var = f'"{target_var}"' if not (target_var.startswith('"') and target_var.endswith('"')) else target_var
        unquoted_var = target_var[1:-1] if (target_var.startswith('"') and target_var.endswith('"')) else target_var

        self.logger.debug(f"remove_trace_by_variable_name: looking for '{target_var}' (quoted='{quoted_var}', unquoted='{unquoted_var}')")

        # Search for matching trace in self.traces (var stored as expression string)
        found_index = -1
        for i, (var, plot_item, y_axis) in enumerate(self.traces):
            # var is expression string (could be quoted)
            if var == target_var or var == quoted_var or var == unquoted_var:
                found_index = i
                break
            # Also check if var matches after cleaning quotes (split_expressions logic)
            # The split_expressions method removes surrounding quotes
            # We'll do a simple check: remove quotes from var and compare
            cleaned_var = var
            if len(cleaned_var) >= 2 and cleaned_var[0] in ['"', "'"] and cleaned_var[-1] == cleaned_var[0]:
                cleaned_var = cleaned_var[1:-1]
            if cleaned_var == target_var or cleaned_var == unquoted_var:
                found_index = i
                break

        if found_index == -1:
            self.logger.debug(f"Trace not found for variable '{variable_name}'")
            return False

        # Remove from visual representation
        var, plot_item, y_axis = self.traces[found_index]
        if y_axis == "Y2" and self.y2_viewbox:
            self.y2_viewbox.removeItem(plot_item)
        else:
            self.plot_widget.plotItem.vb.removeItem(plot_item)

        # Remove from legend
        if self.legend:
            try:
                self.legend.removeItem(plot_item)
            except Exception as e:
                self.logger.error(f"Error removing trace from legend: {e}")

        # Remove from internal list
        self.traces.pop(found_index)

        # Remove from application state
        # Find corresponding trace in state.traces
        state_trace_idx = -1
        for i, trace in enumerate(self.state.traces):
            # Compare trace name (expression) with var
            if trace.name == var:
                state_trace_idx = i
                break
            # Also compare with cleaned version
            cleaned_name = trace.name
            if len(cleaned_name) >= 2 and cleaned_name[0] in ['"', "'"] and cleaned_name[-1] == cleaned_name[0]:
                cleaned_name = cleaned_name[1:-1]
            if cleaned_name == target_var or cleaned_name == unquoted_var:
                state_trace_idx = i
                break

        if state_trace_idx != -1:
            self.state.remove_trace(state_trace_idx)
            self.logger.info(f"Removed trace '{var}' from application state")
        else:
            self.logger.warning(f"Could not find matching trace in application state for '{var}'")

        # Return color to color manager? Not implemented currently.
        # Could implement color_manager.release_color(color) if needed.

        self.logger.info(f"Removed trace for variable '{variable_name}'")
        return True

    def update_traces_for_log_mode(self) -> None:
        """Update all existing traces for current log mode settings.

        PlotCurveItem has no setLogMode; we must transform the data ourselves.
        Always transforms from the ORIGINAL linear-space trace data, so
        toggling log mode on/off produces correct values.
        """
        self.logger.debug(f"\n=== update_traces_for_log_mode ===")
        self.logger.debug(f"  Current log modes: x_log={self.x_log}, y1_log={self.y1_log}, y2_log={self.y2_log}")

        if not self.traces:
            self.logger.debug(f"  No traces to update")
            return

        self.logger.debug(f"  Found {len(self.traces)} traces to update")

        state_traces = self.state.traces
        for i, (var, plot_item, y_axis) in enumerate(self.traces):
            y_log = self.y1_log if y_axis == "Y1" else self.y2_log

            # Get the ORIGINAL linear-space data from the Trace model
            if i < len(state_traces):
                trace = state_traces[i]
                x_orig = trace.x_data
                y_orig = trace.y_data
            else:
                # Fallback: use whatever is in the curve item
                x_orig, y_orig = plot_item.getData()
                if x_orig is None or y_orig is None:
                    continue

            # Apply log10 transform to original data
            x = np.log10(np.abs(x_orig) + 1e-300) if self.x_log else x_orig.copy()
            y = np.log10(np.abs(y_orig) + 1e-300) if y_log else y_orig.copy()

            # Re-downsample the transformed data
            x_ds, y_ds = self._downsample(x, y, DOWNSAMPLE_TARGET)

            plot_item.setData(x_ds, y_ds)
            self.logger.debug(f"  Updated log mode for {var}: x={self.x_log}, y={y_log}")

        self.logger.debug(f"  Trace update complete")

    def ensure_y2_axis(self) -> None:
        """Ensure Y2 axis and viewbox are created and configured."""
        if self.y2_viewbox is not None:
            return  # Already enabled

        # Enable Y2 axis via plot widget
        self.plot_widget.enable_y2_axis()

        # Get references from plot widget
        self.y2_viewbox = self.plot_widget.y2_viewbox
        self.right_axis = self.plot_widget.right_axis

    # Internal methods

    @staticmethod
    def _downsample(x: np.ndarray, y: np.ndarray, n_pts: int):
        """Downsample x,y data to ~n_pts using peak method (min/max per bin).

        This runs once at trace creation time.  The downsampled arrays are
        then passed to PlotCurveItem, avoiding all per-paint overhead of
        PlotDataItem (autoDownsample rebuild, dataBounds, updateItems).
        """
        n = len(x)
        if n <= n_pts:
            return x.copy(), y.copy()
        n_bins = n_pts // 2  # each bin produces 2 points (min+max)
        if n_bins < 1:
            n_bins = 1
        bin_size = n // n_bins
        if bin_size < 1:
            bin_size = 1

        x_ds = np.empty(n_bins * 2, dtype=x.dtype)
        y_ds = np.empty(n_bins * 2, dtype=y.dtype)

        for i in range(n_bins):
            start = i * bin_size
            end = min(start + bin_size, n)
            x_ds[2 * i] = x[start:end].mean()
            x_ds[2 * i + 1] = x[start:end].mean()
            y_ds[2 * i] = y[start:end].min()
            y_ds[2 * i + 1] = y[start:end].max()

        return x_ds, y_ds

    def _create_plot_item(self, trace: Trace) -> pg.PlotCurveItem:
        """Create a PlotCurveItem for the trace with pre-downsampled data.

        Uses PlotCurveItem (not PlotDataItem) to eliminate per-paint overhead:
        no autoDownsample rebuild, no dataBounds nanmin/max, no updateItems.
        Downsampling runs once at creation time.

        If the axis is already in log mode, data is log10-transformed before
        plotting so that the log-scale axis receives correct exponent values.
        """
        pen = pg.mkPen(color=trace.color, width=1)

        x_data = trace.x_data
        y_data = trace.y_data

        # Apply log10 transform if the corresponding axis is in log mode
        x = np.log10(np.abs(x_data) + 1e-300) if self.x_log else x_data
        y_log = self.y1_log if trace.y_axis == AxisAssignment.Y1 else self.y2_log
        y = np.log10(np.abs(y_data) + 1e-300) if y_log else y_data

        # Pre-downsample to fixed resolution
        x_ds, y_ds = self._downsample(x, y, DOWNSAMPLE_TARGET)

        plot_item = _StaticCurveItem(
            x_ds, y_ds,
            pen=pen,
        )
        # Segmented line mode is faster than path rendering for line plots.
        # Uses drawLines() instead of drawPath().
        plot_item.setSegmentedLineMode('on')

        if trace.y_axis == AxisAssignment.Y2:
            # Ensure Y2 axis exists
            self.ensure_y2_axis()
            # Add to Y2 viewbox
            self.y2_viewbox.addItem(plot_item)
            # Add to legend with Y2 prefix
            legend_name = f"{trace.name} @ Y2"
            self.legend.addItem(plot_item, legend_name)
        else:
            # Add to main viewbox (Y1)
            self.plot_widget.plotItem.vb.addItem(plot_item)
            # Add to legend with Y1 prefix
            legend_name = f"{trace.name} @ Y1"
            self.legend.addItem(plot_item, legend_name)

        return plot_item

    def _auto_range_y_axis(self, y_axis: AxisAssignment) -> None:
        """Auto-range the specified Y axis."""
        if y_axis == AxisAssignment.Y2:
            self._auto_range_y2()
        else:
            self._auto_range_y1()

    def _auto_range_x(self) -> None:
        """Auto-range X axis."""
        self.plot_widget.auto_range_axis('X')

    def _auto_range_y1(self) -> None:
        """Auto-range Y1 axis."""
        self.plot_widget.auto_range_axis('Y1')

    def _auto_range_y2(self) -> None:
        """Auto-range Y2 axis."""
        if self.y2_viewbox:
            self.plot_widget.auto_range_axis('Y2')

    def _get_current_x_var(self) -> Optional[str]:
        """Get the current X-axis variable name from application state."""
        return self.state.current_x_var

    @staticmethod
    def split_expressions(expr: str) -> List[str]:
        """Split expression into individual expressions, respecting quotes, parentheses and operators.

        Args:
            expr: Expression string (e.g., 'v(out) v(in)' or '"v(out)" "v(in)"')

        Returns:
            List of individual expression strings.
        """
        expressions = []
        current_expr = []
        paren_depth = 0
        in_quotes = False
        quote_char = None

        i = 0
        while i < len(expr):
            c = expr[i]

            if c in ['"', "'"] and paren_depth == 0:
                if not in_quotes:
                    # Start of quoted expression
                    in_quotes = True
                    quote_char = c
                elif c == quote_char:
                    # End of quoted expression
                    in_quotes = False
                    quote_char = None
                current_expr.append(c)
            elif c == '(' and not in_quotes:
                paren_depth += 1
                current_expr.append(c)
            elif c == ')' and not in_quotes:
                paren_depth -= 1
                current_expr.append(c)
            elif c == ' ' and paren_depth == 0 and not in_quotes:
                if current_expr:
                    # Split here
                    expressions.append(''.join(current_expr).strip())
                    current_expr = []
            else:
                current_expr.append(c)

            i += 1

        if current_expr:
            expressions.append(''.join(current_expr).strip())

        # Remove quotes from expressions
        cleaned_expressions = []
        for expr in expressions:
            if expr and expr[0] in ['"', "'"] and expr[-1] == expr[0]:
                cleaned_expressions.append(expr[1:-1])
            else:
                cleaned_expressions.append(expr)

        return cleaned_expressions