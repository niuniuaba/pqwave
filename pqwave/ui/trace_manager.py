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
from PyQt6.QtWidgets import QColorDialog
from typing import Optional, List, Tuple

from pqwave.models.state import ApplicationState
from pqwave.models.trace import Trace, AxisAssignment
from pqwave.models.expression import ExprEvaluator
from pqwave.utils.colors import ColorManager
from pqwave.logging_config import get_logger

# Pre-downsample target: 2x typical screen width.  This gives good visual
# quality for moderate zoom-in while keeping per-paint overhead low.
DOWNSAMPLE_TARGET = 1600


from pyqtgraph.graphicsItems.LegendItem import ItemSample


class SelectableItemSample(ItemSample):
    """ItemSample that does NOT toggle visibility on left click.

    pyqtgraph's default ItemSample toggles plot_item visibility on every
    left click.  We replace that with a clean signal emission so the
    TraceManager selection handler controls all click behaviour.
    """

    sigRightClicked = QtCore.pyqtSignal(object)

    def mouseClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            self.update()
            self.sigClicked.emit(self.item)
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            event.accept()
            self.sigRightClicked.emit(self.item)


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

    @staticmethod
    def _is_fft_expression(expr: str) -> bool:
        return expr.lower().startswith('fft(')

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

        # Re-entrancy guard for update_traces_for_log_mode
        self._updating_log_mode = False


        # Connect legend click signal for trace selection
        self.legend.sigSampleClicked.connect(self._on_legend_sample_clicked)

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

            # Filter out variables that already exist (prevent duplicates)
            existing = {v for v, _, _ in self.traces}
            filtered = [v for v in variables if v not in existing]
            skipped = [v for v in variables if v in existing]
            if skipped:
                self.logger.info(f"Skipping duplicate traces: {', '.join(skipped)}")
            variables = filtered
            if not variables:
                error_msg = f"Expression already exists as a trace"
                self.logger.info(error_msg)
                if error_out is not None:
                    error_out.append(error_msg)
                return None

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
                if np.iscomplexobj(x_data) and np.all(x_data.imag == 0):
                    x_data = x_data.real
                self.logger.debug(f"X data length: {len(x_data)}")

                traces_added = []

                for var in variables:
                    evaluator = ExprEvaluator(self.raw_file, self.current_dataset)
                    self.logger.debug(f"Created evaluator for {var}")

                    y_data = evaluator.evaluate(var)
                    self.logger.debug(f"Evaluated expression {var}, result length: {len(y_data)}")

                    trace_x_data = x_data
                    is_fft = self._is_fft_expression(var)
                    if is_fft:
                        from pqwave.ui.fft_engine import compute_fft
                        cfg = self.state.fft_config

                        if cfg.x_range_mode == "current zoom":
                            vb = self.plot_widget.plotItem.vb
                            xmin, xmax = vb.viewRange()[0]
                            # If the view range is still uninitialized (default
                            # [0,1]), fall back to full range to avoid silently
                            # clipping all data.
                            if xmin == 0.0 and xmax == 1.0 and not self.traces:
                                pass  # fall through to "full" behavior
                            else:
                                if self.x_log:
                                    xmin, xmax = 10.0 ** xmin, 10.0 ** xmax
                                mask = (x_data >= xmin) & (x_data <= xmax)
                                if mask.any():
                                    x_data = x_data[mask]
                                    y_data = y_data[mask]

                        trace_x_data, y_data = compute_fft(
                            x_data, y_data,
                            window=cfg.window,
                            fft_size=cfg.fft_size,
                            dc_removal=cfg.dc_removal,
                            representation=cfg.representation,
                            x_range_mode=cfg.x_range_mode,
                            x_range_start=cfg.x_range_start,
                            x_range_end=cfg.x_range_end,
                            binomial_smooth=cfg.binomial_smooth,
                        )
                        self.logger.debug(
                            f"FFT: {var} → {len(trace_x_data)} frequency bins"
                        )

                    # Check if X and Y data have the same length
                    if len(trace_x_data) != len(y_data):
                        self.logger.error(f"X and Y data length mismatch!")
                        self.logger.error(f"    X data length: {len(trace_x_data)}")
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
                        x_data=trace_x_data,
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

                # Refresh legend after adding all new traces
                self._refresh_legend()

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

    def _refresh_legend(self) -> None:
        """Clear and re-populate the legend from the current trace list."""
        if not self.legend:
            return
        self.legend.clear()
        for i, (var, plot_item, y_axis) in enumerate(self.traces):
            legend_name = f"{var} @ {y_axis}"
            sample = self.legend.addItem(plot_item, legend_name)
            if isinstance(sample, SelectableItemSample):
                try:
                    sample.sigRightClicked.disconnect()
                except Exception:
                    pass
                sample.sigRightClicked.connect(self._on_legend_sample_right_clicked)
            # Apply bold styling to selected traces
            if i < len(self.state.traces) and self.state.traces[i].selected:
                label = self.legend.getLabel(plot_item)
                if label is not None:
                    label.setText(legend_name, bold=True)

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

    # --- Trace selection ---

    def _on_legend_sample_clicked(self, plot_item) -> None:
        """Handle left click on a legend item sample.

        Plain left click: select that trace (deselect others).
        Ctrl+left click: toggle selection of that trace (multi-select).
        Clicking the only selected trace again: toggle visibility.
        """
        idx = self._find_trace_index(plot_item)
        if idx is None:
            return

        from PyQt6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        ctrl_held = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)

        trace = self.state.traces[idx] if idx < len(self.state.traces) else None
        if trace is None:
            return

        if ctrl_held:
            # Toggle selection of this trace
            trace.selected = not trace.selected
        else:
            # If clicking the only selected trace, toggle visibility instead
            if trace.selected and self._selected_count() == 1:
                trace.visible = not trace.visible
                plot_item.setVisible(trace.visible)
                self._refresh_legend()
                return
            # Single-select: deselect all, select this one
            self.deselect_all()
            trace.selected = True

        self._refresh_legend()

    def _on_legend_sample_right_clicked(self, plot_item) -> None:
        """Handle right click on a legend item sample — change trace color."""
        idx = self._find_trace_index(plot_item)
        if idx is None or idx >= len(self.state.traces):
            return

        trace = self.state.traces[idx]
        old_color = QColor(*trace.color)
        new_color = QColorDialog.getColor(old_color)
        if not new_color.isValid():
            return

        rgb = (new_color.red(), new_color.green(), new_color.blue())
        self.color_manager.release_color(trace.color)
        self.color_manager.mark_color_used(rgb)
        trace.color = rgb
        plot_item.setPen(pg.mkPen(color=rgb, width=1))
        self._refresh_legend()

    def select_trace(self, idx: int) -> None:
        """Select the trace at *idx* and deselect all others."""
        for i, trace in enumerate(self.state.traces):
            trace.selected = (i == idx)

    def deselect_all(self) -> None:
        """Deselect all traces."""
        for trace in self.state.traces:
            trace.selected = False

    def get_selected_traces(self) -> list[tuple[int, Trace]]:
        """Return (index, Trace) pairs for all selected traces."""
        return [(i, t) for i, t in enumerate(self.state.traces) if t.selected]

    def _find_trace_index(self, plot_item) -> int | None:
        """Find the index of *plot_item* in self.traces, or None."""
        for i, (_, pi, _) in enumerate(self.traces):
            if pi is plot_item:
                return i
        return None

    def _selected_count(self) -> int:
        """Return the number of selected traces."""
        return sum(1 for t in self.state.traces if t.selected)

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

        # Remove from internal list (before refreshing legend)
        self.traces.pop(found_index)

        # Refresh legend to reflect removal
        self._refresh_legend()

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
        if self._updating_log_mode:
            return
        self._updating_log_mode = True
        try:
            if not self.traces:
                return

            state_traces = self.state.traces
            for i, (var, plot_item, y_axis) in enumerate(self.traces):
                y_log = self.y1_log if y_axis == "Y1" else self.y2_log

                # Find matching trace by expression — self.state.traces is a
                # global list shared across all panels, so indexed lookup
                # (state_traces[i]) is WRONG when multiple panels exist.
                # Match by expression instead.
                trace = next((t for t in state_traces if t.expression == var), None)
                if trace is not None:
                    x_orig = trace.x_data
                    y_orig = trace.y_data
                else:
                    # Fallback: use whatever is in the curve item
                    x_orig, y_orig = plot_item.getData()
                    if x_orig is None or y_orig is None:
                        continue

                # Apply log10 transform to original data, filtering non-positive
                # values that can't be represented on a log scale.
                if self.x_log:
                    x_mask = x_orig > 0
                    if x_mask.any():
                        x = np.log10(x_orig[x_mask])
                        y_orig = y_orig[x_mask]
                    else:
                        x = np.array([0.0])
                        y_orig = np.array([0.0])
                else:
                    x = x_orig.copy()
                # FFT traces in dB representation are already logarithmic;
                # applying log10 would double-transform and filter out all
                # negative dB values.
                is_fft = self._is_fft_expression(trace.expression)
                if y_log and not is_fft:
                    y_mask = y_orig > 0
                    if y_mask.any():
                        y = np.log10(y_orig[y_mask])
                        if self.x_log:
                            x = x[y_mask]
                    else:
                        y = np.array([0.0])
                        if self.x_log:
                            x = np.array([0.0])
                else:
                    y = y_orig.copy()

                # Re-downsample the transformed data
                x_ds, y_ds = self._downsample(x, y, DOWNSAMPLE_TARGET)

                plot_item.setData(x_ds, y_ds)
                plot_item.prepareGeometryChange()

        finally:
            self._updating_log_mode = False

    def update_x_variable(self, x_var_name: str) -> None:
        """Update all existing traces to use a new X variable.

        Called when the user changes the X-axis variable after traces have already been added.
        Replaces each trace's x_data with data from the new X variable and redraws plot items.
        """
        if self.raw_file is None:
            self.logger.warning("Cannot update X variable: no raw file loaded")
            return

        new_x_data = self.raw_file.get_variable_data(x_var_name, self.current_dataset)
        if new_x_data is None:
            self.logger.error(f"No data for X variable: {x_var_name}")
            return

        if np.iscomplexobj(new_x_data) and np.all(new_x_data.imag == 0):
            new_x_data = new_x_data.real

        state_traces = self.state.traces
        updated_count = 0
        for var, plot_item, y_axis in self.traces:
            y_log = self.y1_log if y_axis == "Y1" else self.y2_log

            # Find matching trace by expression (not by index, since
            # state_traces is a global list shared across panels).
            trace = next((t for t in state_traces if t.expression == var), None)
            if trace is None:
                self.logger.warning(f"No state trace found for '{var}', skipping")
                continue
            # FFT traces carry frequency bins as x_data — never replace
            # them with time-domain X variable data.
            if self._is_fft_expression(trace.expression):
                continue
            if len(new_x_data) != len(trace.y_data):
                self.logger.warning(
                    f"X data length ({len(new_x_data)}) doesn't match Y data length "
                    f"({len(trace.y_data)}) for trace '{var}'. Skipping."
                )
                continue
            trace.x_data = new_x_data.copy()

            # Apply log10 transform if the axis is in log mode, filtering
            # non-positive values that can't be represented on a log scale.
            if self.x_log:
                x_mask = new_x_data > 0
                if x_mask.any():
                    x = np.log10(new_x_data[x_mask])
                    y_data = trace.y_data[x_mask]
                else:
                    x = np.array([0.0])
                    y_data = np.array([0.0])
            else:
                x = new_x_data.copy()
                y_data = trace.y_data.copy()
            is_fft = self._is_fft_expression(trace.expression)
            if y_log and not is_fft:
                y_mask = y_data > 0
                if y_mask.any():
                    y = np.log10(y_data[y_mask])
                    if self.x_log:
                        x = x[y_mask]
                else:
                    y = np.array([0.0])
                    if self.x_log:
                        x = np.array([0.0])
            else:
                y = y_data

            # Downsample and update the plot item
            x_ds, y_ds = self._downsample(x, y, DOWNSAMPLE_TARGET)
            plot_item.setData(x_ds, y_ds)
            updated_count += 1

        if updated_count > 0:
            # Auto-range X axis to fit the new data
            self._auto_range_x()

        self.logger.info(f"Updated {updated_count} traces to use X variable: {x_var_name}")

    def update_legend_cursor_values(self, xa_linear: Optional[float], xb_linear: Optional[float]) -> None:
        """Update legend labels with Y values at X cursor positions.

        Appends bare Y value(s) to each trace's legend label:
          one cursor:  -- v(out) @ Y1 4
          two cursors: -- v(out) @ Y1 4 8

        Args:
            xa_linear: Xa cursor position in linear space, or None if hidden
            xb_linear: Xb cursor position in linear space, or None if hidden
        """
        if not self.traces or not self.legend:
            return

        state_traces = self.state.traces

        for i, (var, plot_item, y_axis) in enumerate(self.traces):
            trace = state_traces[i] if i < len(state_traces) else None
            if trace is None:
                self.logger.warning(f"No state trace found for legend item {i}")
                continue

            base_name = f"{var} @ {y_axis}"

            # Collect Y values for visible X cursors
            values = []
            for cursor_x in (xa_linear, xb_linear):
                if cursor_x is not None and len(trace.x_data) > 0:
                    x_min, x_max = float(trace.x_data[0]), float(trace.x_data[-1])
                    clipped_x = max(x_min, min(cursor_x, x_max))
                    y_val = float(np.interp(clipped_x, trace.x_data, trace.y_data))
                    values.append(f"{y_val:.6g}")

            suffix = " " + " ".join(values) if values else ""
            full_name = base_name + suffix

            # Update legend label via pyqtgraph's public API
            label = self.legend.getLabel(plot_item)
            if label is not None:
                label.setText(full_name, bold=trace.selected)

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

        # Apply log10 transform if the corresponding axis is in log mode.
        # Filter non-positive values (e.g. DC bin at 0 Hz in FFT, t=0 in
        # transient) that can't be represented on a log scale. The 1e-300
        # fallback used previously corrupted auto-range when x_data[0] == 0.
        if self.x_log:
            x_mask = x_data > 0
            if x_mask.any():
                x = np.log10(x_data[x_mask])
                y_data = y_data[x_mask]
            else:
                x = np.array([0.0])
                y_data = np.array([0.0])
        else:
            x = x_data
        y_log = self.y1_log if trace.y_axis == AxisAssignment.Y1 else self.y2_log
        is_fft = self._is_fft_expression(trace.expression)
        if y_log and not is_fft:
            y_mask = y_data > 0
            if y_mask.any():
                y = np.log10(y_data[y_mask])
                if self.x_log:
                    x = x[y_mask]
            else:
                y = np.array([0.0])
                if self.x_log:
                    x = np.array([0.0])
        else:
            y = y_data

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
        else:
            # Add to main viewbox (Y1)
            self.plot_widget.plotItem.vb.addItem(plot_item)

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