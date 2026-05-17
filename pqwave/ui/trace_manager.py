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
from PyQt6.QtWidgets import QMessageBox
from typing import Optional, List, Tuple

from pqwave.ui.trace_analysis_dialog import TraceAnalysisDialog

from pqwave.models.state import ApplicationState
from pqwave.models.trace import Trace, AxisAssignment
from pqwave.models.expression import ExprEvaluator
from pqwave.utils.colors import ColorManager
from pqwave.digital.digital_renderer import threshold_and_step
from pqwave.digital.threshold_config import ThresholdConfig
from pqwave.digital.trace_type_manager import TraceTypeManager
from pqwave.digital.vcd_time_aligner import align_vcd_to_raw, vcd_to_step_arrays, vcd_to_uniform_grid
from pqwave.digital.threshold_dialog import ThresholdDialog
from pqwave.logging_config import get_logger

# Pre-downsample target: 2x typical screen width.  This gives good visual
# quality for moderate zoom-in while keeping per-paint overhead low.
DOWNSAMPLE_TARGET = 1600

# Rendering constants for bus trace visualisation
BUS_BASE_OFFSET = 0.5     # base Y level for bus centre line (relative to y_off)
BUS_RAIL_GAP = 0.25       # vertical gap from centre to each rail
BUS_TW_FRACTION = 200.0   # transition width = total_time_span / this


from pyqtgraph.graphicsItems.LegendItem import ItemSample


class SelectableItemSample(ItemSample):
    """ItemSample that does NOT toggle visibility on left click.

    pyqtgraph's default ItemSample toggles plot_item visibility on every
    left click.  We replace that with a clean signal emission so the
    TraceManager selection handler controls all click behaviour.

    Right-click looks up a callback stored on the parent LegendItem
    (set by TraceManager) so each panel's context menu fires correctly.
    """

    def __init__(self, item):
        super().__init__(item)
        self.setMinimumWidth(120)

    def mouseClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            self.update()
            self.sigClicked.emit(self.item)
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            event.accept()
            handler = getattr(self.parentItem(), '_right_click_handler', None)
            if handler is not None:
                handler(self.item)
        else:
            super().mouseClickEvent(event)


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


class TraceManager(QtCore.QObject):
    """Manages trace lifecycle, color assignment, and legend updates."""

    logger = get_logger(__name__)

    # Emitted when user right-clicks a trace legend item
    trace_context_menu_requested = QtCore.pyqtSignal(str)

    @staticmethod
    def _is_fft_expression(expr: str) -> bool:
        return expr.lower().startswith('fft(')

    def __init__(self,
                 plot_widget: pg.PlotWidget,
                 legend: pg.LegendItem,
                 application_state: ApplicationState,
                 panel_id: str = '',
                 color_manager: Optional[ColorManager] = None):
        """
        Initialize TraceManager.

        Args:
            plot_widget: The PlotWidget instance for visual representation
            legend: The LegendItem for trace labels
            application_state: ApplicationState singleton for data management
            panel_id: ID of the panel this TraceManager belongs to
            color_manager: ColorManager instance for color assignment (creates default if None)
        """
        super().__init__()
        self.plot_widget = plot_widget
        self.legend = legend
        self.state = application_state
        self._panel_id = panel_id
        if not panel_id:
            self.logger.warning(
                "TraceManager created without panel_id — "
                "trace operations will be no-ops")
        self.color_manager = color_manager or ColorManager()

        # References to plot components for Y2 axis
        self.y2_viewbox = None  # Will be set when Y2 axis is enabled
        self.right_axis = None

        # Internal state
        self.traces: List[Tuple[str, pg.PlotCurveItem, str]] = []  # (var, plot_item, y_axis)
        self.raw_file = None
        self.vcd_file = None  # Optional VcdFile for mixed-signal overlay
        self.current_dataset = 0

        # Log mode flags (should be synchronized with axis configuration)
        self.x_log = False
        self.y1_log = False
        self.y2_log = False

        # Re-entrancy guard for update_traces_for_log_mode
        self._updating_log_mode = False

        # Digital signal type manager (handles analog↔digital toggle, bus grouping)
        self.type_manager = TraceTypeManager(
            on_recreate=self.recreate_trace_plot_item)

        # Connect legend click signal for trace selection
        self.legend.sigSampleClicked.connect(self._on_legend_sample_clicked)

        # Wire right-click on legend samples via legend attribute
        self.legend._right_click_handler = self._on_legend_sample_right_clicked

    @property
    def _state_traces(self) -> List[Trace]:
        """Return traces belonging to this TraceManager's panel.

        Unlike ApplicationState.traces (which routes through the active panel),
        this always returns the trace list for the panel this manager was
        created for, eliminating cross-panel data corruption.
        """
        panel = self.state.panels.get(self._panel_id) if self._panel_id else None
        return panel.traces if panel else []

    # Public API

    def set_raw_file(self, raw_file) -> None:
        """Set the current raw file for trace evaluation."""
        self.raw_file = raw_file

    def set_vcd_file(self, vcd_file) -> None:
        """Set an optional VCD file for mixed-signal overlay."""
        self.vcd_file = vcd_file

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

        expr = expression.strip()
        if not expr:
            error_msg = "Empty expression"
            self.logger.warning(error_msg)
            if error_out is not None:
                error_out.append(error_msg)
            return None

        # VCD-only mode: no raw file, only VCD signals available
        if self.raw_file is None and self.vcd_file is not None:
            try:
                variables = self.split_expressions(expr)
            except Exception:
                self.logger.exception(f"Failed to split expression: {expr}")
                if error_out is not None:
                    error_out.append(f"Failed to parse expression: {expr}")
                return None
            existing = {v for v, _, _ in self.traces}
            traces_added = []
            for var in variables:
                if var in existing:
                    self.logger.info(f"Skipping duplicate VCD trace: {var}")
                    continue
                t = self._add_vcd_trace(var, AxisAssignment.Y1, custom_color, error_out)
                if t is not None:
                    traces_added.append(t)
            if traces_added:
                return traces_added[0]
            if error_out is not None and not error_out:
                error_out.append(f"VCD signal not found: {expr}")
            return None

        if not self.raw_file:
            error_msg = "No raw file opened"
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
                _fft_db_axes: set[str] = set()

                for var in variables:
                    # Check if this is a VCD signal (mixed-signal overlay or VCD-only)
                    vcd_sig = None
                    if self.vcd_file and not self._is_fft_expression(var):
                        vcd_sig = self._resolve_vcd_signal(var)

                    if vcd_sig is not None:
                        y_axis = AxisAssignment.Y1  # digital traces always Y1
                        vcd_t, vcd_v = vcd_sig.to_arrays(
                            self.vcd_file.timescale)
                        _vcd_event_times = vcd_t.copy()
                        _vcd_event_values = vcd_v.copy()
                        if self.raw_file and x_data is not None:
                            y_data = align_vcd_to_raw(x_data, vcd_t, vcd_v)
                        else:
                            trace_x_data, y_data = vcd_to_uniform_grid(vcd_t, vcd_v)
                    else:
                        evaluator = ExprEvaluator(self.raw_file, self.current_dataset)
                        self.logger.debug(f"Created evaluator for {var}")

                        y_data = evaluator.evaluate(var)
                    self.logger.debug(f"Evaluated expression {var}, result length: {len(y_data)}")

                    trace_x_data = x_data
                    is_fft = self._is_fft_expression(var)
                    fft_repr = "linear"
                    if is_fft:
                        from pqwave.ui.fft_engine import compute_fft
                        cfg = self.state.fft_config
                        fft_repr = cfg.representation

                        _x, _y = x_data, y_data  # default: full range
                        if cfg.x_range_mode == "current zoom":
                            vb = self.plot_widget.plotItem.vb
                            xmin, xmax = vb.viewRange()[0]
                            # If the view range is still uninitialized (default
                            # [0,1]), fall back to full range to avoid silently
                            # clipping all data.
                            if xmin == 0.0 and xmax == 1.0 and not self.traces:
                                pass  # use full-range defaults
                            else:
                                if self.x_log:
                                    xmin, xmax = 10.0 ** xmin, 10.0 ** xmax
                                mask = (x_data >= xmin) & (x_data <= xmax)
                                if mask.any():
                                    _x = x_data[mask]
                                    _y = y_data[mask]

                        trace_x_data, y_data = compute_fft(
                            _x, _y,
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

                    if vcd_sig is not None:
                        trace.trace_type = 'digital'
                        trace.metadata['vcd_times'] = _vcd_event_times
                        trace.metadata['vcd_values'] = _vcd_event_values

                    # Add trace to application state
                    self.state.add_trace(trace)

                    # Create visual representation
                    plot_item = self._create_plot_item(trace)

                    # Store reference
                    self.traces.append((var, plot_item, y_axis.value))
                    traces_added.append(trace)

                    self.logger.info(f"Added trace: {var} on {y_axis.value}")

                    if fft_repr == "db":
                        _fft_db_axes.add(y_axis.value)

                # Enable dB suffix once per axis after the loop
                for axis_side in _fft_db_axes:
                    orientation = 'left' if axis_side == 'Y1' else 'right'
                    ax = self.plot_widget.plotItem.getAxis(orientation)
                    if hasattr(ax, 'setDbMode'):
                        ax.setDbMode(True)

                # Refresh legend after adding all new traces
                self._refresh_legend()

                # Auto-range the appropriate Y axis
                self._auto_range_y_axis(y_axis)

                # Also auto-range X axis to match the new data
                self._auto_range_x()

                # Update Y tick visibility for digital panels
                self._update_y_tick_visibility()

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

    def _resolve_vcd_signal(self, expr: str):
        """Look up a VCD signal by name, with scope-prefix fallback.

        Returns the VCD signal object or None.
        """
        stripped = expr.strip('"').strip("'")
        sig = self.vcd_file.get_signal(stripped)
        if sig is None:
            for name in self.vcd_file.get_signal_names():
                if name.endswith('.' + stripped) or name == stripped:
                    sig = self.vcd_file.get_signal(name)
                    break
        return sig

    def _add_vcd_trace(self, expr: str, y_axis: AxisAssignment,
                       custom_color=None, error_out=None) -> Optional[Trace]:
        """Add a trace from a VCD signal (VCD-only mode, no raw file)."""
        vcd_sig = self._resolve_vcd_signal(expr)
        if vcd_sig is None:
            msg = f"VCD signal not found: {expr}"
            self.logger.warning(msg)
            if error_out is not None:
                error_out.append(msg)
            return None
        stripped = expr.strip('"').strip("'")

        vcd_t, vcd_v = vcd_sig.to_arrays(self.vcd_file.timescale)
        _vcd_event_times = vcd_t.copy()
        _vcd_event_values = vcd_v.copy()
        if len(vcd_t) == 0 or len(vcd_v) == 0:
            # Signal never changed — create a flat constant-unknown trace
            t_max = max(1e-9, self.vcd_file.timescale * 1000)
            for sig in self.vcd_file.signals.values():
                if sig.times:
                    t_max = max(t_max, max(sig.times) * self.vcd_file.timescale)
            trace_x_data = np.array([0.0, t_max], dtype=np.float64)
            y_data = np.array([-0.5, -0.5], dtype=np.float64)
            _vcd_event_times = trace_x_data
            _vcd_event_values = y_data
            self.logger.info(f"VCD signal has no events, showing as constant: {stripped}")
        else:
            trace_x_data, y_data = vcd_to_step_arrays(vcd_t, vcd_v)
            # Extend the last value to the VCD file's global max time so
            # the trace doesn't end at the signal's last event time.
            vcd_max = self.vcd_file.get_max_time()
            if vcd_max > vcd_t[-1]:
                trace_x_data = np.append(trace_x_data, vcd_max)
                y_data = np.append(y_data, vcd_v[-1])
                _vcd_event_times = np.append(_vcd_event_times, vcd_max)
                _vcd_event_values = np.append(_vcd_event_values, vcd_v[-1])
        if len(trace_x_data) == 0:
            msg = f"Failed to grid VCD data: {stripped}"
            self.logger.warning(msg)
            if error_out is not None:
                error_out.append(msg)
            return None

        color = custom_color or self.color_manager.get_next_color()
        trace = Trace(
            name=stripped, expression=stripped,
            x_data=trace_x_data, y_data=y_data,
            y_axis=y_axis, color=color, line_width=1.0,
            dataset_idx=0,
        )
        if vcd_sig.width > 1:
            trace.trace_type = 'bus'
            trace.metadata['bus_width'] = vcd_sig.width
            trace.metadata['bus_display_format'] = 'hex'
        else:
            trace.trace_type = 'digital'
        trace.metadata.setdefault('digital_height', 1.0)
        # Store VCD event data for accurate step rendering
        trace.metadata['vcd_times'] = _vcd_event_times
        trace.metadata['vcd_values'] = _vcd_event_values

        self.state.add_trace(trace)
        plot_item = self._create_plot_item(trace)
        self.traces.append((stripped, plot_item, y_axis.value))
        self._refresh_legend()
        self._auto_range_y_axis(y_axis)
        self._auto_range_x()
        self.logger.info(f"Added VCD trace: {stripped} on {y_axis.value}")
        self._update_y_tick_visibility()
        return trace

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
            if i < len(self._state_traces):
                tt = self._state_traces[i].trace_type
                if tt == 'digital':
                    legend_name = f"{var} [D] @ {y_axis}"
                elif tt == 'bus':
                    t = self._state_traces[i]
                    n_bits = t.metadata.get('bus_width', len(t.bus_signals or []))
                    legend_name = f"{var} [BUS:{n_bits}] @ {y_axis}"
            sample = self.legend.addItem(plot_item, legend_name)
            # Apply bold styling to selected traces
            if i < len(self._state_traces) and self._state_traces[i].selected:
                label = self.legend.getLabel(plot_item)
                if label is not None:
                    label.setText(legend_name, bold=True)

    def _update_y_tick_visibility(self) -> None:
        """Hide Y tick labels when all traces are digital, show otherwise.

        Digital traces carry no physical unit — showing numeric tick values
        (-1, 0, 1, ...) confuses users.  Analog traces (or digital traces
        viewed in analog mode) restore normal tick display.
        """
        traces = self._state_traces
        all_digital = (
            len(traces) > 0
            and all(t.trace_type in ('digital', 'bus') for t in traces)
        )

        for orientation in ('left', 'right'):
            axis = self.plot_widget.plotItem.getAxis(orientation)
            if hasattr(axis, 'setHideTickLabels'):
                axis.setHideTickLabels(all_digital)

    def clear_traces(self) -> None:
        """Clear all traces from plot and application state."""
        self.logger.debug(f"clear_traces called, current traces count: {len(self.traces)}")
        # import traceback
        # traceback.print_stack()  # Debug statement removed for test stability
        # Clear traces from viewboxes (including bus bottom lines)
        for t in self._state_traces:
            bot = t.metadata.pop('_bus_bot_item', None)
            if bot is not None:
                vb = bot.getViewBox()
                if vb is not None:
                    vb.removeItem(bot)
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

        # Remove phantom digital Y bounds
        self._remove_digital_y1_bounds()

        # Clear traces from application state
        self.state.clear_traces()

        # Reset dB mode on Y axes
        for orientation in ('left', 'right'):
            ax = self.plot_widget.plotItem.getAxis(orientation)
            if hasattr(ax, 'setDbMode'):
                ax.setDbMode(False)

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
            except Exception as e:
                self.logger.warning(
                    "Failed to remove y2_viewbox from scene: %s", e)
            self.y2_viewbox = None

        # Reset log mode flags for fresh start
        self.x_log = False
        self.y1_log = False
        self.y2_log = False

        # Restore Y tick visibility (no traces → show ticks)
        self._update_y_tick_visibility()

    # --- Trace selection ---

    def _on_legend_sample_right_clicked(self, plot_item) -> None:
        """Forward right-click on legend sample to MainWindow for context menu."""
        idx = self._find_trace_index(plot_item)
        if idx is None:
            return
        trace = self._state_traces[idx] if idx < len(self._state_traces) else None
        if trace is None:
            return
        self.trace_context_menu_requested.emit(trace.name)

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

        trace = self._state_traces[idx] if idx < len(self._state_traces) else None
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
                # Toggle bus bottom line if present
                bot = trace.metadata.get('_bus_bot_item')
                if bot is not None:
                    bot.setVisible(trace.visible)
                self._refresh_legend()
                return
            # Single-select: deselect all, select this one
            self.deselect_all()
            trace.selected = True

        self._refresh_legend()

    # --- Keybinding-accessible operations (no right-click menu) ---

    def toggle_trace_type(self) -> None:
        """Toggle selected traces between analog and digital."""
        for idx, trace in self.get_selected_traces():
            self.type_manager.toggle(trace, idx)

    def group_selected_as_bus(self) -> None:
        """Create a bus from selected digital traces."""
        selected = self.get_selected_traces()
        digital_traces = [(i, t) for i, t in selected if t.trace_type == 'digital']
        if len(digital_traces) < 2:
            return
        name = f"bus{len(self.traces)}"
        traces_for_bus = [t for _, t in digital_traces]
        indices = [i for i, _ in digital_traces]
        bus_trace = self.type_manager.group_as_bus(traces_for_bus, name, indices)
        if bus_trace is None:
            return
        self.state.add_trace(bus_trace)
        plot_item = self._create_plot_item(bus_trace)
        self.traces.append((name, plot_item, bus_trace.y_axis.value))
        # Hide member traces from view and legend
        for i, t in digital_traces:
            t.visible = False
            t.metadata['_bus_member_hidden'] = True
            if i < len(self.traces):
                _, pi, _ = self.traces[i]
                pi.setVisible(False)
        self._refresh_legend()
        self._auto_range_y_axis(bus_trace.y_axis)
        self._auto_range_x()
        self._update_y_tick_visibility()

    def toggle_bus_expand(self, bus_trace_name: str) -> None:
        """Expand/collapse a bus: show or hide its member traces."""
        bus_trace = next(
            (t for t in self._state_traces if t.name == bus_trace_name), None)
        if bus_trace is None or bus_trace.trace_type != 'bus':
            return
        if bus_trace.bus_signals is None:
            return

        expanded = bus_trace.metadata.get('bus_expanded', False)
        if expanded:
            self.collapse_bus(bus_trace)
        else:
            self.expand_bus(bus_trace)

    def expand_bus(self, bus_trace: Trace = None, bus_trace_name: str = None) -> None:
        """Show member traces of a bus (unconditionally)."""
        if bus_trace is None:
            bus_trace = next(
                (t for t in self._state_traces if t.name == bus_trace_name), None)
        if bus_trace is None or bus_trace.trace_type != 'bus':
            return
        if bus_trace.bus_signals is None:
            return
        member_exprs = set(bus_trace.bus_signals)
        for i, t in enumerate(self._state_traces):
            if t.expression in member_exprs:
                t.metadata.pop('_bus_member_hidden', None)
                t.visible = True
                if i < len(self.traces):
                    self.traces[i][1].setVisible(True)
        bus_trace.metadata['bus_expanded'] = True
        self._refresh_legend()

    def collapse_bus(self, bus_trace: Trace = None, bus_trace_name: str = None) -> None:
        """Hide member traces of a bus (unconditionally)."""
        if bus_trace is None:
            bus_trace = next(
                (t for t in self._state_traces if t.name == bus_trace_name), None)
        if bus_trace is None or bus_trace.trace_type != 'bus':
            return
        if bus_trace.bus_signals is None:
            return
        member_exprs = set(bus_trace.bus_signals)
        for i, t in enumerate(self._state_traces):
            if t.expression in member_exprs:
                t.metadata['_bus_member_hidden'] = True
                t.visible = False
                if i < len(self.traces):
                    self.traces[i][1].setVisible(False)
        bus_trace.metadata['bus_expanded'] = False
        self._refresh_legend()

    def ungroup_bus(self, bus_trace_name: str) -> None:
        """Ungroup a bus: restore member visibility and remove the bus trace."""
        bus_trace = next(
            (t for t in self._state_traces if t.name == bus_trace_name), None)
        if bus_trace is None or bus_trace.trace_type != 'bus':
            return

        # Restore member trace visibility
        if bus_trace.bus_signals:
            member_exprs = set(bus_trace.bus_signals)
            for i, t in enumerate(self._state_traces):
                if t.expression in member_exprs:
                    t.metadata.pop('_bus_member_hidden', None)
                    t.visible = True
                    if i < len(self.traces):
                        self.traces[i][1].setVisible(True)
                    t.trace_type = 'digital'

        # Remove bus from state
        state_idx = next((i for i, t in enumerate(self._state_traces)
                          if t.name == bus_trace_name), -1)
        if state_idx >= 0:
            self._state_traces.pop(state_idx)
            self.state.remove_trace(state_idx)

        # Remove bus plot items (main line + bottom rail)
        bot = bus_trace.metadata.pop('_bus_bot_item', None)
        if bot is not None:
            bvb = bot.getViewBox()
            if bvb is not None:
                bvb.removeItem(bot)
        for i, (name, pi, axis) in enumerate(self.traces):
            if name == bus_trace_name:
                vb = pi.getViewBox()
                if vb is not None:
                    vb.removeItem(pi)
                self.traces.pop(i)
                break

        self._refresh_legend()

    def set_trace_visible(self, expr: str, visible: bool) -> None:
        """Set a trace's visibility by name or expression."""
        for i, t in enumerate(self._state_traces):
            if t.name == expr or t.expression == expr:
                t.visible = visible
                if i < len(self.traces):
                    self.traces[i][1].setVisible(visible)
                    bot = t.metadata.get('_bus_bot_item')
                    if bot is not None:
                        bot.setVisible(visible)
                self._refresh_legend()
                return

    def set_all_traces_visible(self, visible: bool) -> None:
        """Set visibility for all traces."""
        changed = False
        for i, t in enumerate(self._state_traces):
            if t.visible != visible:
                t.visible = visible
                if i < len(self.traces):
                    self.traces[i][1].setVisible(visible)
                    bot = t.metadata.get('_bus_bot_item')
                    if bot is not None:
                        bot.setVisible(visible)
                changed = True
        if changed:
            self._refresh_legend()

    def show_threshold_dialog(self) -> None:
        """Open threshold settings for the first selected digital trace."""
        for idx, trace in self.get_selected_traces():
            if trace.trace_type == 'digital':
                dlg = ThresholdDialog(trace, self.plot_widget)
                if dlg.exec():
                    self.recreate_trace_plot_item(idx)
                break

    def select_trace(self, idx: int) -> None:
        """Select the trace at *idx* and deselect all others."""
        for i, trace in enumerate(self._state_traces):
            trace.selected = (i == idx)

    def deselect_all(self) -> None:
        """Deselect all traces."""
        for trace in self._state_traces:
            trace.selected = False

    def get_selected_traces(self) -> list[tuple[int, Trace]]:
        """Return (index, Trace) pairs for all selected traces."""
        return [(i, t) for i, t in enumerate(self._state_traces) if t.selected]

    def remove_selected_traces(self) -> int:
        """Remove all selected traces. Returns the number removed."""
        selected = self.get_selected_traces()
        names = [t.expression for _, t in selected]
        count = 0
        for name in names:
            if self.remove_trace_by_variable_name(name):
                count += 1
        return count

    def _show_stats_for_traces(self, targets: list[tuple[int, Trace]]) -> None:
        """Compute visible-range statistics for *targets* and show the dialog."""
        xmin, xmax = self.plot_widget.plotItem.vb.viewRange()[0]
        if self.x_log:
            xmin, xmax = 10.0 ** xmin, 10.0 ** xmax
        range_str = self._format_range_str(xmin, xmax)

        dlg = TraceAnalysisDialog(self.plot_widget)
        dlg.set_region_str(range_str)
        for _, trace in targets:
            metrics = self._compute_visible_stats(trace, xmin, xmax)
            if not metrics:
                QMessageBox.information(
                    self.plot_widget, "No Data",
                    f"{trace.name}: no data points in visible range."
                )
                continue
            dlg.add_trace_result(trace.name, metrics)
        dlg.show()

    def _compute_visible_stats(self, trace: Trace,
                               xmin: float, xmax: float) -> dict:
        """Compute statistics for *trace* over [xmin, xmax]."""
        mask = (trace.x_data >= xmin) & (trace.x_data <= xmax)
        if not mask.any():
            return {}
        y_seg = trace.y_data[mask]
        x_seg = trace.x_data[mask]
        results = {
            'avg': float(np.mean(y_seg)),
            'RMS': float(np.sqrt(np.mean(y_seg ** 2))),
            'min': float(np.min(y_seg)),
            'max': float(np.max(y_seg)),
            'pk-pk': float(np.ptp(y_seg)),
            'freq': None,
        }
        if len(y_seg) >= 4:
            dx = np.diff(x_seg)
            dt = np.median(dx)
            # Check uniformity: if sample spacing varies more than 1%,
            # the FFT frequency estimate is unreliable.
            if dt > 0:
                cv = float(np.std(dx) / dt) if dt > 0 else 0.0
                if cv < 0.01:
                    n_fft = 1 << (len(y_seg) - 1).bit_length()
                    yw = y_seg - np.mean(y_seg)
                    mag = np.abs(np.fft.rfft(yw, n=n_fft))
                    freqs = np.fft.rfftfreq(n_fft, d=dt)
                    if len(mag) > 2:
                        peak_idx = np.argmax(mag[1:]) + 1
                        results['freq'] = float(freqs[peak_idx])
        return results

    @staticmethod
    def _format_range_str(xmin: float, xmax: float) -> str:
        """Format an X range as a human-readable string with SI prefix hints."""
        span = xmax - xmin
        if span < 1e-6:
            return f"{xmin*1e9:.4g}ns — {xmax*1e9:.4g}ns"
        elif span < 1e-3:
            return f"{xmin*1e6:.4g}µs — {xmax*1e6:.4g}µs"
        elif span < 1:
            return f"{xmin*1e3:.4g}ms — {xmax*1e3:.4g}ms"
        else:
            return f"{xmin:.4g}s — {xmax:.4g}s"

    def _find_trace_index(self, plot_item) -> int | None:
        """Find the index of *plot_item* in self.traces, or None."""
        for i, (_, pi, _) in enumerate(self.traces):
            if pi is plot_item:
                return i
        return None

    def _selected_count(self) -> int:
        """Return the number of selected traces."""
        return sum(1 for t in self._state_traces if t.selected)

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

        # Remove bus bottom line if present (match by name, not index —
        # self.traces and self._state_traces may diverge after bus grouping).
        bot = None
        for t in self._state_traces:
            if t.name == var:
                bot = t.metadata.get('_bus_bot_item')
                break
        if bot is not None:
            vb = bot.getViewBox()
            if vb is not None:
                vb.removeItem(bot)

        # Remove from internal list (before refreshing legend)
        self.traces.pop(found_index)

        # Refresh legend to reflect removal
        self._refresh_legend()
        self._update_y_tick_visibility()

        # Remove from application state
        # Find corresponding trace in state.traces
        state_trace_idx = -1
        for i, trace in enumerate(self._state_traces):
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
        self._auto_range_y_axis(AxisAssignment.Y1)
        self._auto_range_x()
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

            state_traces = self._state_traces
            for i, (var, plot_item, y_axis) in enumerate(self.traces):
                y_log = self.y1_log if y_axis == "Y1" else self.y2_log

                # Find matching trace by expression — self._state_traces is a
                # global list shared across all panels, so indexed lookup
                # (state_traces[i]) is WRONG when multiple panels exist.
                # Match by expression instead.
                trace = next((t for t in state_traces if t.expression == var), None)
                if trace is not None:
                    x_orig = trace.x_data
                    y_orig = trace.y_data
                    is_fft = self._is_fft_expression(trace.expression)
                else:
                    # Fallback: use whatever is in the curve item
                    x_orig, y_orig = plot_item.getData()
                    if x_orig is None or y_orig is None:
                        continue
                    is_fft = self._is_fft_expression(var)

                x, y = self._apply_log10_if_needed(
                    x_orig, y_orig, self.x_log, y_log, is_fft
                )

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

        state_traces = self._state_traces
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

            is_fft = self._is_fft_expression(trace.expression)
            x, y = self._apply_log10_if_needed(
                new_x_data, trace.y_data, self.x_log, y_log, is_fft
            )

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

        state_traces = self._state_traces

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

    @staticmethod
    def _apply_log10_if_needed(
        x: np.ndarray, y: np.ndarray,
        x_log: bool, y_log: bool,
        is_fft: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Apply log10 transforms when the corresponding axis is in log mode.

        Filters out non-positive values that can't be represented on a log
        scale.  Used by all three code paths that apply log transforms
        (trace creation, log-mode toggle, X-variable update).
        """
        if x_log:
            x_mask = x > 0
            if x_mask.any():
                x = np.log10(x[x_mask])
                y = y[x_mask]
            else:
                return np.array([0.0]), np.array([0.0])

        if y_log and not is_fft:
            y_mask = y > 0
            if y_mask.any():
                y = np.log10(y[y_mask])
                if x_log:
                    x = x[y_mask]
            else:
                y = np.array([0.0])
                if x_log:
                    x = np.array([0.0])

        return x, y

    def _create_plot_item(self, trace: Trace) -> pg.PlotCurveItem:
        """Create a graphics item for the trace.

        Dispatches to the analog or digital rendering path based on
        trace.trace_type.  Analog traces use _StaticCurveItem (PlotCurveItem
        subclass with cached bounds).  Digital traces use _StaticCurveItem
        with stepMode='center' for step-function rendering.
        """
        if trace.trace_type in ('digital', 'bus'):
            return self._create_digital_plot_item(trace)
        return self._create_analog_plot_item(trace)

    def _create_digital_plot_item(self, trace: Trace) -> pg.PlotCurveItem:
        """Create a step-mode PlotCurveItem for a digital or bus trace.

        Uses pyqtgraph's native stepMode='center' which draws each y[i]
        from x[i] to x[i+1].  VCD event data (stored in trace metadata)
        yields the most accurate step rendering; uniform-grid data falls
        back to midpoint boundaries.
        """
        # Compute Y stacking offset from previous traces' actual slot heights.
        # Only count traces assigned to the same Y axis to avoid cross-axis
        # contamination when digital/bus traces are split across Y1 and Y2.
        trace_height = trace.metadata.get('digital_height', 1.0)
        target_axis = trace.y_axis
        y_off = 0.0
        for t in self._state_traces:
            if t is trace:
                break
            if t.trace_type in ('digital', 'bus') and t.y_axis == target_axis:
                h = t.metadata.get('digital_height', 1.0)
                y_off += h * 2.0 + 0.3  # digital values span [-1,1] → range 2

        if trace.trace_type == 'bus':
            return self._create_bus_plot_item(trace, y_off)

        # Prefer raw VCD event data for accurate transition placement
        vcd_t = trace.metadata.get('vcd_times')
        vcd_v = trace.metadata.get('vcd_values')
        if vcd_t is not None and vcd_v is not None and len(vcd_t) >= 2:
            t_arr = np.asarray(vcd_t, dtype=np.float64)
            v_arr = np.asarray(vcd_v, dtype=np.float64)
            # Extend by one boundary so stepMode covers the final segment
            dt = t_arr[-1] - t_arr[-2] if len(t_arr) >= 2 else t_arr[-1] * 0.1 or 1e-9
            x_bounds = np.append(t_arr, t_arr[-1] + dt)
            y_vals = v_arr
        else:
            x = np.asarray(trace.x_data, dtype=np.float64)
            y = np.asarray(trace.y_data, dtype=np.float64)
            if len(x) == 0:
                return _StaticCurveItem([], [], pen=pg.mkPen(color=trace.color, width=trace.line_width))
            if len(x) >= 2:
                x_bounds = np.empty(len(x) + 1, dtype=np.float64)
                x_bounds[0] = x[0] - (x[1] - x[0]) / 2.0
                x_bounds[1:-1] = (x[:-1] + x[1:]) / 2.0
                x_bounds[-1] = x[-1] + (x[-1] - x[-2]) / 2.0
            else:
                x_bounds = np.array([x[0], x[0] + 1e-9], dtype=np.float64)
            y_vals = y

        y_vals = y_vals * trace_height + y_off

        pen = pg.mkPen(color=trace.color, width=trace.line_width)
        plot_item = _StaticCurveItem(x_bounds, y_vals, pen=pen, stepMode='center')
        self._add_to_viewbox(plot_item, trace.y_axis)
        self.logger.debug(
            f"_create_digital_plot_item: stepMode plot, "
            f"n_bounds={len(x_bounds)}, n_vals={len(y_vals)}, "
            f"x_range=[{x_bounds[0]:.6g}, {x_bounds[-1]:.6g}], "
            f"y_range=[{y_vals.min():.6g}, {y_vals.max():.6g}], "
            f"y_off={y_off:.3f}"
        )
        return plot_item

    def _create_bus_plot_item(self, trace: Trace,
                              y_off: float = 0.0) -> pg.PlotCurveItem:
        """Create a bus trace: two parallel lines that cross at value
        transitions, with hex/bin labels placed between them.

        At each transition the two lines swap levels through diagonal
        segments, forming a visible X pattern (like xschem/surfer).
        """
        from PyQt6.QtGui import QColor

        y = np.nan_to_num(np.asarray(trace.y_data, dtype=np.float64), nan=0)
        x = trace.x_data
        n = len(y)

        scale = trace.metadata.get('digital_height', 1.0)
        base_level = BUS_BASE_OFFSET * scale + y_off
        gap = BUS_RAIL_GAP * scale
        high = base_level + gap
        low  = base_level - gap

        if n >= 2:
            total_span = float(x[-1]) - float(x[0])
            tw = max(total_span / BUS_TW_FRACTION, 1e-12)
        else:
            tw = 1e-9

        # Collect transition times first so we can start / end at the
        # first / last crossing instead of the full data range.
        transitions = []
        prev_val = int(y[0]) if n > 0 else 0
        for i in range(1, n):
            curr_val = int(y[i])
            if curr_val != prev_val:
                transitions.append(float(x[i]))
                prev_val = curr_val

        top_t = []
        top_v = []
        bot_t = []
        bot_v = []

        if len(transitions) == 0:
            top_t = [float(x[0]), float(x[-1])]
            top_v = [high, high]
            bot_t = [float(x[0]), float(x[-1])]
            bot_v = [low, low]
        elif len(transitions) == 1:
            tx = transitions[0]
            # Pre-transition segment + right half of crossing + flat to end
            top_t = [float(x[0]), tx, tx + tw, x[-1]]
            top_v = [base_level, base_level, low, low]
            bot_t = [float(x[0]), tx, tx + tw, x[-1]]
            bot_v = [base_level, base_level, high, high]
        else:
            first_tx = transitions[0]
            last_tx  = transitions[-1]
            # Start at centre of first crossing (matches surfer)
            top_t.append(first_tx)
            top_v.append(base_level)
            bot_t.append(first_tx)
            bot_v.append(base_level)

            for k, tx in enumerate(transitions):
                is_first = (k == 0)
                is_last  = (k == len(transitions) - 1)
                if is_first:
                    # Right half only: centre → tw → new level
                    top_t.extend([tx + tw])
                    top_v.extend([low])
                    bot_t.extend([tx + tw])
                    bot_v.extend([high])
                elif is_last:
                    # Full crossing + flat segment + sharp closure at endpoint
                    tx_end = tx + tw
                    if x[-1] > tx_end + tw:
                        # Enough room: flat to near-end, then close
                        close_start = x[-1] - tw
                        top_t.extend([tx - tw, tx, tx_end, close_start, x[-1]])
                        top_v.extend([high, base_level, low, low, base_level])
                        bot_t.extend([tx - tw, tx, tx_end, close_start, x[-1]])
                        bot_v.extend([low, base_level, high, high, base_level])
                    else:
                        top_t.extend([tx - tw, tx, tx_end, x[-1]])
                        top_v.extend([high, base_level, low, base_level])
                        bot_t.extend([tx - tw, tx, tx_end, x[-1]])
                        bot_v.extend([low, base_level, high, base_level])
                else:
                    # Full crossing: left half + centre + right half
                    top_t.extend([tx - tw, tx, tx + tw])
                    top_v.extend([high, base_level, low])
                    bot_t.extend([tx - tw, tx, tx + tw])
                    bot_v.extend([low, base_level, high])
                high, low = low, high

        x_top = np.array(top_t, dtype=np.float64)
        y_top = np.array(top_v, dtype=np.float64)
        x_bot = np.array(bot_t, dtype=np.float64)
        y_bot = np.array(bot_v, dtype=np.float64)

        pen = pg.mkPen(color=trace.color, width=trace.line_width)
        top_item = _StaticCurveItem(x_top, y_top, pen=pen, symbol=None,
                                    skipFiniteCheck=True)
        bot_item = _StaticCurveItem(x_bot, y_bot, pen=pen, symbol=None,
                                    skipFiniteCheck=True)
        self._add_to_viewbox(top_item, trace.y_axis)
        self._add_to_viewbox(bot_item, trace.y_axis)

        # Value labels at the centre of each flat segment
        fmt = trace.metadata.get('bus_display_format', 'hex')
        n_bits = trace.metadata.get('bus_width', len(trace.bus_signals or []))
        prev_val = int(y[0]) if n > 0 else 0
        label_times = [float(x[0])] if n > 0 else []
        for i in range(1, n):
            curr_val = int(y[i])
            if curr_val != prev_val:
                label_times.append(float(x[i]))
                prev_val = curr_val

        # Ensure the final segment gets a label.  For constant-value buses
        # there are no transitions; show a single label at the midpoint.
        if len(label_times) == 1 and n > 1:
            label_times.append(float(x[-1]))
        elif len(label_times) >= 1 and label_times[-1] < x[-1]:
            label_times.append(float(x[-1]))

        # Build label font from tick font config (match axis tick appearance)
        from PyQt6.QtGui import QFont
        label_font = QFont()
        tf = self.state.tick_font
        if tf.family:
            label_font.setFamily(tf.family)
        if tf.size > 0:
            label_font.setPointSize(tf.size)

        step = max(1, len(label_times) // 20)
        for k in range(len(label_times) - 1):
            if k % step != 0:
                continue
            t_mid = (label_times[k] + label_times[k + 1]) / 2.0
            idx = int(np.searchsorted(x, t_mid))
            if idx >= n:
                idx = n - 1
            val_at_t = int(y[idx])
            if fmt == 'hex':
                n_hex = (n_bits + 3) // 4 if n_bits else 2
                label_text = f"0x{val_at_t:0{n_hex}X}"
            elif fmt == 'bin':
                w = n_bits if n_bits else 8
                label_text = f"{val_at_t:0{w}b}"
            else:
                label_text = str(val_at_t)

            text_item = pg.TextItem(label_text, color=QColor(200, 200, 200),
                                    anchor=(0.5, 0.5))
            text_item.setFont(label_font)
            text_item.setPos(t_mid, base_level)
            text_item.setParentItem(top_item)

        trace.metadata['_bus_bot_item'] = bot_item
        if not trace.visible:
            top_item.setVisible(False)
            bot_item.setVisible(False)
        return top_item

    def _add_to_viewbox(self, plot_item, y_axis: AxisAssignment) -> None:
        """Add a plot item to the correct ViewBox."""
        if y_axis == AxisAssignment.Y2:
            self.ensure_y2_axis()
            self.y2_viewbox.addItem(plot_item)
            vb = self.y2_viewbox
        else:
            vb = self.plot_widget.plotItem.vb
            vb.addItem(plot_item)
        self.logger.debug(
            f"_add_to_viewbox: added {type(plot_item).__name__} to "
            f"{'Y2' if y_axis == AxisAssignment.Y2 else 'Y1'}, "
            f"vb.addedItems count={len(vb.addedItems)}, "
            f"vb.viewRange={vb.viewRange()}"
        )

    def _create_analog_plot_item(self, trace: Trace) -> pg.PlotCurveItem:
        """Create a PlotCurveItem for the trace with pre-downsampled data."""
        pen = pg.mkPen(color=trace.color, width=trace.line_width)

        y_log = self.y1_log if trace.y_axis == AxisAssignment.Y1 else self.y2_log
        is_fft = self._is_fft_expression(trace.expression)
        x, y = self._apply_log10_if_needed(
            trace.x_data, trace.y_data, self.x_log, y_log, is_fft
        )

        # Pre-downsample to fixed resolution
        x_ds, y_ds = self._downsample(x, y, DOWNSAMPLE_TARGET)

        plot_item = _StaticCurveItem(
            x_ds, y_ds,
            pen=pen,
        )
        # Segmented line mode is faster than path rendering for line plots.
        # Uses drawLines() instead of drawPath().
        plot_item.setSegmentedLineMode('on')

        self._add_to_viewbox(plot_item, trace.y_axis)

        return plot_item

    def _create_mc_spaghetti(self, mc, signal_name, x_data_list, y_data_list, color):
        """Create spaghetti plot: all runs overlaid with low alpha.

        Args:
            mc: MCRunCollection instance
            signal_name: name of the signal group
            x_data_list: list of x-data arrays, one per run
            y_data_list: list of y-data arrays, one per run
            color: base RGB tuple for run traces

        Returns:
            List of PlotCurveItem objects (one per active run, max 500)
        """
        from pyqtgraph import PlotCurveItem
        import numpy as np

        items = []
        max_runs = min(mc.active_count, 500)

        # Nominal gets a warm highlight color
        nominal_color = (255, 80, 80) if sum(color) < 300 else (255, 200, 50)

        for i, run_idx in enumerate(mc.active_runs[:max_runs]):
            if run_idx >= len(x_data_list):
                break
            x = np.array(x_data_list[run_idx], dtype=np.float64)
            y = np.array(y_data_list[run_idx], dtype=np.float64)

            if self.x_log:
                x = np.log10(np.abs(x) + 1e-300)
            if self._y_log_for_signal(signal_name):
                y = np.log10(np.abs(y) + 1e-300)

            is_nominal = (run_idx == mc.nominal_index)
            pen_color = nominal_color if is_nominal else color
            pen_width = 2.0 if is_nominal else 0.5
            alpha = 255 if is_nominal else 40

            curve = PlotCurveItem(
                x, y,
                pen=self._make_pen(pen_color, pen_width, alpha),
                symbol=None,
                skipFiniteCheck=True,
            )
            items.append(curve)

        return items

    def _create_mc_envelope(self, mc, signal_name, x_data_list, y_data_list, color):
        """Create envelope plot: mean line + sigma band fill.

        Returns:
            List of plot items: [FillBetweenItem, mean_curve, upper_curve, nominal_curve]
        """
        from pyqtgraph import PlotCurveItem, FillBetweenItem
        from pqwave.analysis.multi_run import compute_cross_run_stats
        import numpy as np

        # Build data matrix from active runs
        n_runs = mc.active_count
        n_points = max(len(y_data_list[r]) for r in mc.active_runs if r < len(y_data_list))
        data_matrix = np.zeros((n_runs, n_points))
        for i, run_idx in enumerate(mc.active_runs):
            if i >= n_runs or run_idx >= len(y_data_list):
                break
            y = y_data_list[run_idx]
            data_matrix[i, :len(y)] = y

        stats = compute_cross_run_stats(data_matrix)
        mean = stats["mean"]
        std = stats["std"]
        upper = mean + mc.envelope_sigma * std
        lower = mean - mc.envelope_sigma * std

        # Use first run's x data as reference
        x = np.array(x_data_list[0][:len(mean)], dtype=np.float64)

        if self.x_log:
            x = np.log10(np.abs(x) + 1e-300)
        if self._y_log_for_signal(signal_name):
            mean = np.log10(np.abs(mean) + 1e-300)
            upper = np.log10(np.abs(upper) + 1e-300)
            lower = np.log10(np.abs(lower) + 1e-300)

        # Mean line (solid)
        mean_curve = PlotCurveItem(
            x, mean,
            pen=self._make_pen(color, 1.5, 255),
            symbol=None, skipFiniteCheck=True,
        )
        # Upper band edge (dashed, faint)
        upper_curve = PlotCurveItem(
            x, upper,
            pen=self._make_pen(color, 0.5, 80),
            symbol=None, skipFiniteCheck=True,
        )

        # Fill between mean and upper band
        fill = FillBetweenItem(upper_curve, mean_curve, brush=(*color[:3], 30))

        # Nominal overlay (distinct color)
        nominal_y = np.array(y_data_list[mc.nominal_index][:len(mean)], dtype=np.float64)
        if self._y_log_for_signal(signal_name):
            nominal_y = np.log10(np.abs(nominal_y) + 1e-300)
        nominal_curve = PlotCurveItem(
            x, nominal_y,
            pen=self._make_pen((255, 80, 80), 2.0, 255),
            symbol=None, skipFiniteCheck=True,
        )

        return [fill, mean_curve, upper_curve, nominal_curve]

    def _make_pen(self, color, width, alpha):
        """Create a QPen from (r, g, b) color, width, and alpha."""
        from PyQt6.QtGui import QPen, QColor
        r, g, b = color[:3]
        return QPen(QColor(r, g, b, alpha), width)

    def _y_log_for_signal(self, signal_name):
        """Check if Y axis log mode is active for the given signal."""
        # Check y1_log attribute on the TraceManager or its panel
        if hasattr(self, 'y1_log'):
            return self.y1_log
        return False

    def recreate_trace_plot_item(self, trace_idx: int) -> None:
        """Recreate the plot item for a trace after type change.

        Removes the old item from the ViewBox, creates a new one via
        _create_plot_item dispatch, and refreshes the legend.
        """
        if trace_idx < 0 or trace_idx >= len(self.traces):
            return
        var, old_item, y_axis = self.traces[trace_idx]
        vb = old_item.getViewBox()
        if vb is not None:
            vb.removeItem(old_item)
        if old_item.scene() is not None:
            old_item.scene().removeItem(old_item)

        trace = next((t for t in self._state_traces if t.name == var), None)
        if trace is None:
            self.logger.warning(
                f"recreate_trace_plot_item: trace '{var}' not found in state; "
                "plot item was removed but not replaced.")
            return
        # Clean up old bus bottom rail if present
        bot = trace.metadata.pop('_bus_bot_item', None)
        if bot is not None:
            vb = bot.getViewBox()
            if vb is not None:
                vb.removeItem(bot)
        new_item = self._create_plot_item(trace)
        self.traces[trace_idx] = (var, new_item, y_axis)
        self._refresh_legend()
        self._auto_range_y_axis(trace.y_axis)
        self._auto_range_x()
        self._update_y_tick_visibility()

    def recreate_all_digital(self) -> None:
        """Recreate all digital and bus trace plot items (e.g., after height change)."""
        for i, (var, old_item, y_axis) in enumerate(self.traces):
            t = next((s for s in self._state_traces if s.name == var), None)
            if t is None or t.trace_type not in ('digital', 'bus'):
                continue
            vb = old_item.getViewBox()
            if vb is not None:
                vb.removeItem(old_item)
            bot = t.metadata.pop('_bus_bot_item', None)
            if bot is not None:
                bvb = bot.getViewBox()
                if bvb is not None:
                    bvb.removeItem(bot)
            new_item = self._create_plot_item(t)
            # Restore visibility for hidden bus member traces
            if not t.visible:
                new_item.setVisible(False)
            self.traces[i] = (var, new_item, y_axis)
        self._refresh_legend()
        self._auto_range_y_axis(AxisAssignment.Y1)
        self._auto_range_x()
        self._update_y_tick_visibility()

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
        """Auto-range Y1 axis.

        When all visible Y1 traces are digital/bus, places phantom boundary
        markers so pyqtgraph's autoRange includes a fixed minimum viewport
        height, preventing a single trace from filling the entire Y axis.
        """
        traces = self._state_traces
        y1_traces = [t for t in traces
                     if t.y_axis == AxisAssignment.Y1 and t.visible]
        y1_digital = [t for t in y1_traces
                      if t.trace_type in ('digital', 'bus')]
        if y1_digital and all(t.trace_type in ('digital', 'bus')
                               for t in y1_traces):
            total_h = sum(t.metadata.get('digital_height', 1.0) * 2.0 + 0.3
                          for t in y1_digital)
            y_max = max(20.0, total_h)
            self._set_digital_y1_bounds(-0.5, y_max)
        else:
            self._remove_digital_y1_bounds()
        self.plot_widget.auto_range_axis('Y1')

    def _set_digital_y1_bounds(self, y_min: float, y_max: float) -> None:
        self.plot_widget.set_digital_y1_bounds(y_min, y_max)

    def _remove_digital_y1_bounds(self) -> None:
        self.plot_widget.clear_digital_y1_bounds()

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