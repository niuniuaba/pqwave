#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TraceManager - Handles trace lifecycle, color assignment, and legend management.

This module provides a class that manages the addition, removal, and updating
of traces in the plot, including color assignment and legend synchronization.
"""

import numpy as np
import pyqtgraph as pg
from typing import Optional, List, Tuple, Dict, Any
from PyQt6.QtGui import QColor

from pqwave.models.state import ApplicationState, AxisId
from pqwave.models.trace import Trace, AxisAssignment
from pqwave.models.expression import ExprEvaluator
from pqwave.utils.colors import ColorManager


class TraceManager:
    """Manages trace lifecycle, color assignment, and legend updates."""

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
                  custom_color: Optional[Tuple[int, int, int]] = None) -> Optional[Trace]:
        """Add a trace for the given expression.

        Args:
            expression: Expression string (e.g., 'v(out)' or 'v(out) v(in)')
            x_var_name: Name of X-axis variable
            y_axis: Which Y axis to plot on (Y1 or Y2)
            custom_color: Optional custom color as RGB tuple (0-255)

        Returns:
            Trace object if successful, None otherwise.
        """
        if not self.raw_file:
            print("No raw file opened")
            return None

        expr = expression.strip()
        if not expr:
            print("Empty expression")
            return None

        try:
            print(f"Adding trace for expression: {expr}")
            var_names = self.raw_file.get_variable_names(self.current_dataset)
            print(f"Available variables: {var_names}")

            n_points = self.raw_file.get_num_points(self.current_dataset)
            print(f"Number of points: {n_points}")

            # Split the expression into individual variables/expressions
            variables = self.split_expressions(expr)
            print(f"Split expressions: {variables}")

            if not x_var_name:
                print("No X-axis variable selected")
                return None
            x_var = x_var_name
            print(f"X-axis variable: {x_var}")

            x_data = self.raw_file.get_variable_data(x_var, self.current_dataset)
            if x_data is not None:
                print(f"X data length: {len(x_data)}")

                # Apply log transformation if needed
                x_data = self._apply_log_transformation(
                    x_data, self.x_log, axis_name="X")

                traces_added = []

                for var in variables:
                    evaluator = ExprEvaluator(self.raw_file, self.current_dataset)
                    print(f"Created evaluator for {var}")

                    y_data = evaluator.evaluate(var)
                    print(f"Evaluated expression {var}, result length: {len(y_data)}")

                    # Apply log transformation if needed
                    y_log = self.y1_log if y_axis == AxisAssignment.Y1 else self.y2_log
                    y_data = self._apply_log_transformation(
                        y_data, y_log, axis_name="Y")

                    # Check if X and Y data have the same length
                    if len(x_data) != len(y_data):
                        print(f"  ERROR: X and Y data length mismatch!")
                        print(f"    X data length: {len(x_data)}")
                        print(f"    Y data length: {len(y_data)}")
                        print(f"    Skipping trace for {var}")
                        continue

                    # Get color
                    if custom_color is not None:
                        color = custom_color
                        print(f"  Using custom color: {color}")
                    else:
                        color = self.color_manager.get_next_color()
                        print(f"  Using auto-assigned color: {color}")

                    # Create trace model
                    trace = Trace(
                        name=var,
                        expression=var,
                        x_data=x_data,
                        y_data=y_data,
                        y_axis=y_axis,
                        color=color,
                        line_width=2.0,
                        dataset_idx=self.current_dataset
                    )

                    # Add trace to application state
                    self.state.add_trace(trace)

                    # Create visual representation
                    plot_item = self._create_plot_item(trace)

                    # Store reference
                    self.traces.append((var, plot_item, y_axis.value))
                    traces_added.append(trace)

                    print(f"Added trace: {var} on {y_axis.value}")

                # Auto-range the appropriate Y axis
                self._auto_range_y_axis(y_axis)

                # Clear the trace expression input box (should be done by caller)
                # Return the first trace if any were added
                return traces_added[0] if traces_added else None

            else:
                print(f"No data for X variable: {x_var}")
                return None

        except Exception as e:
            print(f"Error adding trace: {e}")
            import traceback
            traceback.print_exc()
            return None

    def add_trace_from_variable(self,
                                variable_name: str,
                                x_var_name: str,
                                y_axis: AxisAssignment = AxisAssignment.Y1,
                                custom_color: Optional[Tuple[int, int, int]] = None) -> Optional[Trace]:
        """Add a trace for a single variable name.

        Convenience method for adding traces from combo box selections.
        """
        # Quote the variable name to treat it as a literal
        quoted_var = f'"{variable_name}"'
        return self.add_trace(quoted_var, x_var_name, y_axis, custom_color)

    def clear_traces(self) -> None:
        """Clear all traces from plot and application state."""
        print(f"[DEBUG] clear_traces called, current traces count: {len(self.traces)}")
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
            print(f"  Clearing {len(items)} items from legend")
            for item in items:
                try:
                    self.legend.removeItem(item)
                except Exception as e:
                    print(f"    Error removing legend item: {e}")
            # Also try clear() method
            try:
                self.legend.clear()
            except Exception as e:
                print(f"    Error clearing legend: {e}")

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

    def update_traces_for_log_mode(self) -> None:
        """Update all existing traces for current log mode settings.

        This method should be called when log modes change. It re-adds all
        traces with the new log mode settings.
        """
        print(f"\n=== update_traces_for_log_mode ===")
        print(f"  Current log modes: x_log={self.x_log}, y1_log={self.y1_log}, y2_log={self.y2_log}")

        if not self.traces:
            print(f"  No traces to update")
            return

        print(f"  Found {len(self.traces)} traces to update")

        # Save current trace information
        saved_traces = []
        for var, plot_item, y_axis in self.traces:
            # Get trace color from plot item and convert to RGB tuple
            qcolor = plot_item.opts['pen'].color()
            color = (qcolor.red(), qcolor.green(), qcolor.blue())
            saved_traces.append({
                'var': var,
                'y_axis': y_axis,
                'color': color
            })
            print(f"  Saving trace: {var} on {y_axis}, color={color}")

        # Clear all traces and legend
        self.clear_traces()
        print(f"  Cleared all traces and legend")

        # Re-add all traces with current log mode settings
        for trace_info in saved_traces:
            var = trace_info['var']
            y_axis = AxisAssignment.Y1 if trace_info['y_axis'] == "Y1" else AxisAssignment.Y2
            color = trace_info['color']

            print(f"  Re-adding trace: {var} on {y_axis.value} with color {color}")

            # Re-add trace with saved color and axis
            try:
                self.add_trace_from_variable(var, self._get_current_x_var(), y_axis, color)
            except Exception as e:
                print(f"    Error re-adding trace: {e}")

        print(f"  Trace update complete")

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

    def _apply_log_transformation(self,
                                  data: np.ndarray,
                                  log_mode: bool,
                                  axis_name: str = "axis") -> np.ndarray:
        """Apply log transformation to data if log mode is enabled.

        Handles non-positive values by replacing them with small positive values.
        Returns the transformed data (log10(data)) if log_mode is True,
        otherwise returns the original data.
        """
        if not log_mode:
            print(f"  {axis_name}-axis is in linear mode, using original data")
            return data

        print(f"  {axis_name}-axis is in log mode, transforming data...")
        data_real = np.real(data)
        print(f"  Original {axis_name} data range: [{np.min(data_real):.6e}, {np.max(data_real):.6e}]")

        # Handle non-positive values (log10 undefined for <= 0)
        mask = data_real > 0
        if np.any(~mask):
            print(f"  Warning: {np.sum(~mask)} non-positive {axis_name} values found, adjusting for log scale...")

            # Calculate a reasonable replacement value
            if np.any(mask):
                # If there are positive values, use a small fraction of the minimum positive value
                min_positive = np.min(data_real[mask])
                replacement = min_positive * 1e-10  # Much smaller fraction
            else:
                # If no positive values, use a small fraction of the data range
                data_range = np.max(np.abs(data_real)) - np.min(np.abs(data_real))
                if data_range > 0:
                    replacement = data_range * 1e-10
                else:
                    replacement = 1e-10  # Default small value

            print(f"    Replacement value: {replacement:.6e}")
            data_real = np.where(mask, data_real, replacement)
            print(f"    Adjusted {axis_name} data range: [{np.min(data_real):.6e}, {np.max(data_real):.6e}]")

        # Transform to log10
        data_transformed = np.log10(data_real)
        print(f"  Transformed {axis_name} data range: [{np.min(data_transformed):.6e}, {np.max(data_transformed):.6e}]")
        return data_transformed

    def _create_plot_item(self, trace: Trace) -> pg.PlotCurveItem:
        """Create a PlotCurveItem for the trace and add it to the appropriate viewbox."""
        pen = pg.mkPen(color=trace.color, width=trace.line_width)
        plot_item = pg.PlotCurveItem(trace.x_data, trace.y_data, name=trace.name, pen=pen)

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

    def _auto_range_y1(self) -> None:
        """Auto-range Y1 axis."""
        self.plot_widget.auto_range_axis('Y1')

    def _auto_range_y2(self) -> None:
        """Auto-range Y2 axis."""
        if self.y2_viewbox:
            self.y2_viewbox.enableAutoRange(axis='y')

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