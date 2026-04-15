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
from pqwave.logging_config import get_logger


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
        self.traces: List[Tuple[str, pg.PlotDataItem, str]] = []  # (var, plot_item, y_axis)
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
            self.logger.warning("No raw file opened")
            return None

        expr = expression.strip()
        if not expr:
            self.logger.warning("Empty expression")
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
                self.logger.warning("No X-axis variable selected")
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
                return traces_added[0] if traces_added else None

            else:
                self.logger.error(f"No data for X variable: {x_var}")
                return None

        except Exception as e:
            self.logger.error(f"Error adding trace: {e}")
            import traceback
            self.logger.exception("Error adding trace")
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

    def update_traces_for_log_mode(self) -> None:
        """Update all existing traces for current log mode settings.

        Reuses existing PlotDataItem objects — only updates logMode flags.
        PlotDataItem internally invalidates its cached mapped data and
        re-applies log10 mapping on the next paint.
        """
        self.logger.debug(f"\n=== update_traces_for_log_mode ===")
        self.logger.debug(f"  Current log modes: x_log={self.x_log}, y1_log={self.y1_log}, y2_log={self.y2_log}")

        if not self.traces:
            self.logger.debug(f"  No traces to update")
            return

        self.logger.debug(f"  Found {len(self.traces)} traces to update")

        for var, plot_item, y_axis in self.traces:
            y_log = self.y1_log if y_axis == "Y1" else self.y2_log
            plot_item.setLogMode(self.x_log, y_log)
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

    def _create_plot_item(self, trace: Trace) -> pg.PlotDataItem:
        """Create a PlotDataItem for the trace and add it to the appropriate viewbox."""
        pen = pg.mkPen(color=trace.color, width=1)
        y_log = self.y1_log if trace.y_axis == AxisAssignment.Y1 else self.y2_log

        plot_item = pg.PlotDataItem(
            trace.x_data,
            trace.y_data,
            name=trace.name,
            pen=pen,
            symbol=None,              # rule 2: disable scatter points
            skipFiniteCheck=True,     # rule 8: skip finite check
            autoDownsample=True,
            downsampleMethod='peak',
        )
        plot_item.setLogMode(self.x_log, y_log)

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
            self.y2_viewbox.autoRange(y=True, padding=0.05)

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