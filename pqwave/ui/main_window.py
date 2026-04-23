#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MainWindow - Main application window orchestrating all UI components.

This module provides the MainWindow class that composes all modular UI components
(MenuManager, ControlPanel, PlotWidget, TraceManager, AxisManager) and integrates
them with the ApplicationState singleton.
"""

import sys
import time
import traceback
import json
import socket
from typing import Optional, Tuple
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QDialog, QCheckBox, QDialogButtonBox, QLabel
)
from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtGui import QColor

from pqwave.models.state import ApplicationState, AxisId, ViewboxTheme
from pqwave.models.rawfile import RawFile
from pqwave.models.raw_converter import write_raw_file, FORMAT_CONFIG
from pqwave.models.dataset import Dataset
from pqwave.models.trace import AxisAssignment
from pqwave.ui.menu_manager import MenuManager
from pqwave.ui.control_panel import ControlPanel
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.trace_manager import TraceManager
from pqwave.ui.settings_widget import SettingsWidget
from pqwave.ui.axis_manager import AxisManager
from pqwave.ui.mark_panel import MarkPanel
from pqwave.utils.colors import ColorManager
from pqwave.logging_config import get_logger
from pqwave.communication.window_registry import get_registry
import uuid


logger = get_logger(__name__)

class MainWindow(QMainWindow):
    """Main application window orchestrating all UI components."""

    def __init__(self, initial_file=None):
        """
        Initialize MainWindow.

        Args:
            initial_file: Optional path to initial raw file to load
        """
        super().__init__()
        self.setWindowTitle("pqwave - SPICE Waveform Viewer")
        self.setGeometry(100, 100, 1200, 800)

        # Initialize application state singleton
        self.state = ApplicationState()

        # Xschem integration: window ID and registry
        self.window_id = str(uuid.uuid4())
        self.raw_file_path = initial_file  # current raw file path (may be updated when loading new file)
        self.state.window_registry.register_window(
            window_id=self.window_id,
            window_instance=self,
            raw_file_path=self.raw_file_path
        )

        # Store initial file for delayed loading
        self.initial_file = initial_file

        # Component references (will be initialized in _setup_ui)
        self.menu_manager = None
        self.plot_widget = None
        self.control_panel = None
        self.trace_manager = None
        self.axis_manager = None
        self.color_manager = None

        # Raw file reference
        self.raw_file = None

        # Zoom box state
        self.zoom_box_enabled = False

        # Cross-hair cursor state
        self.cross_hair_visible = False
        self.mark_panel = None

        # Xschem pending commands (when raw_file not yet loaded)
        self.pending_xschem_commands = []  # list of (command_type, args, client_addr, connection_state)

        # Setup UI
        self._setup_ui()

        # Connect signals
        self._connect_signals()

        # Flag to prevent double loading from timer
        self.initial_file_loaded = False

        # Load initial file if provided
        if self.initial_file:
            QTimer.singleShot(100, self._load_initial_file)

    def _setup_ui(self):
        """Create and arrange UI components."""
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Create color manager
        self.color_manager = ColorManager()

        # Create plot widget (with cursor support)
        self.plot_widget = PlotWidget()

        # Create legend (attached to plot widget)
        legend = self.plot_widget.addLegend()
        self.legend = legend

        # Create axis manager
        self.axis_manager = AxisManager(self.plot_widget, self.state)

        # Create trace manager
        self.trace_manager = TraceManager(
            plot_widget=self.plot_widget,
            legend=legend,
            application_state=self.state,
            color_manager=self.color_manager
        )

        # Create control panel
        self.control_panel = ControlPanel()

        # Create menu manager with callbacks
        callbacks = self._create_menu_callbacks()
        self.menu_manager = MenuManager(self, callbacks)

        # Add plot widget to layout (with stretch factor)
        main_layout.addWidget(self.plot_widget, 1)

        # Add control panel to layout
        main_layout.addWidget(self.control_panel)

        # Set layout
        central_widget.setLayout(main_layout)

        # Initialize log mode flags in trace manager
        self._update_trace_manager_log_modes()

    def _create_menu_callbacks(self):
        """Create callback dictionary for menu manager."""
        return {
            'open_file': self.open_file,
            'open_new_window': self.open_new_window,
            'convert_raw_data': self.convert_raw_data,
            'edit_trace_properties': self.edit_trace_properties,
            'show_settings': self.show_settings,
            'toggle_toolbar': self.toggle_toolbar,
            'toggle_statusbar': self.toggle_statusbar,
            'toggle_grids': self.toggle_grids,
            'zoom_in': self.zoom_in,
            'zoom_out': self.zoom_out,
            'zoom_to_fit': self.zoom_to_fit,
            'auto_range_x': self.auto_range_x,
            'auto_range_y': self.auto_range_y,
            'enable_zoom_box': self.enable_zoom_box,
            'zoom_in_toolbar': self.zoom_in,
            'zoom_out_toolbar': self.zoom_out,
            'zoom_to_fit_toolbar': self.zoom_to_fit,
            'auto_range_x_toolbar': self.auto_range_x,
            'auto_range_y_toolbar': self.auto_range_y,
            'zoom_box_toolbar': self.enable_zoom_box,
            'toggle_grids_toolbar': self.toggle_grids,
            'toggle_cross_hair': self.toggle_cross_hair,
            'toggle_x_cursor_a': self._toggle_x_cursor_a,
            'toggle_x_cursor_b': self._toggle_x_cursor_b,
            'toggle_y_cursor_A': self._toggle_y_cursor_A,
            'toggle_y_cursor_B': self._toggle_y_cursor_B,
        }

    def _connect_signals(self):
        """Connect signals between components."""
        # Connect control panel signals
        self.control_panel.dataset_changed.connect(self._on_dataset_changed)
        self.control_panel.vector_selected.connect(self._on_vector_selected)
        self.control_panel.add_trace_to_axis.connect(self._on_add_trace_to_axis)
        self.control_panel.expression_changed.connect(self._on_expression_changed)

        # Connect plot widget signals
        self.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.plot_widget.mouse_left.connect(self._on_mouse_left)
        self.plot_widget.cursor_xa_changed.connect(self._on_cursor_xa_changed)
        self.plot_widget.cursor_xb_changed.connect(self._on_cursor_xb_changed)
        self.plot_widget.cursor_yA_changed.connect(self._on_cursor_yA_changed)
        self.plot_widget.cursor_yB_changed.connect(self._on_cursor_yB_changed)
        self.plot_widget.cursor_y2_changed.connect(self._on_cursor_y2_changed)
        self.plot_widget.axis_log_mode_changed.connect(self._on_axis_log_mode_changed)
        self.plot_widget.mark_clicked.connect(self._on_mark_clicked)

        # Connect axis manager signals
        self.axis_manager.axis_log_mode_changed.connect(self._on_axis_log_mode_changed_from_manager)
        self.axis_manager.axis_range_changed.connect(self._on_axis_range_changed)
        self.axis_manager.axis_label_changed.connect(self._on_axis_label_changed)

        # Connect xschem integration signals
        self._connect_xschem_signals()

        # Back-annotation debounce timer (avoid sending too many updates)
        self._backannotation_timer = QTimer()
        self._backannotation_timer.setSingleShot(True)
        self._backannotation_timer.setInterval(100)  # 100ms debounce
        self._backannotation_timer.timeout.connect(self._send_data_point_update_debounced)
        self._pending_x_value = None  # X value to send when timer fires

    def _connect_xschem_signals(self):
        """Connect xschem command handler signals."""
        if self.state.command_handler is None:
            logger.debug("No xschem command handler available, skipping xschem signal connections")
            return

        # Connect command handler signals to local slots
        self.state.command_handler.table_set_received.connect(self._handle_xschem_table_set)
        self.state.command_handler.copyvar_received.connect(self._handle_xschem_copyvar)
        self.state.command_handler.open_file_received.connect(self._handle_xschem_open_file)
        self.state.command_handler.add_trace_received.connect(self._handle_xschem_add_trace)
        self.state.command_handler.remove_trace_received.connect(self._handle_xschem_remove_trace)
        self.state.command_handler.get_data_point_received.connect(self._handle_xschem_get_data_point)
        self.state.command_handler.close_window_received.connect(self._handle_xschem_close_window)
        self.state.command_handler.list_windows_received.connect(self._handle_xschem_list_windows)
        self.state.command_handler.ping_received.connect(self._handle_xschem_ping)
        self.state.command_handler.invalid_command_received.connect(self._handle_xschem_invalid_command)

        logger.debug(f"Connected xschem signals for window {self.window_id}")

    # Xschem pending commands handling
    def _queue_xschem_command(self, command_type: str, args: dict, client_addr: str, connection_state: dict) -> None:
        """Queue xschem command for processing when raw_file is available."""
        logger.debug(f"Window {self.window_id} queuing {command_type} command from {client_addr}")
        self.pending_xschem_commands.append((command_type, args, client_addr, connection_state))

    def _process_pending_xschem_commands(self) -> None:
        """Process any queued xschem commands."""
        if not self.pending_xschem_commands:
            return
        logger.debug(f"Window {self.window_id} processing {len(self.pending_xschem_commands)} pending commands")
        # Process in order
        for command_type, args, client_addr, connection_state in self.pending_xschem_commands:
            if command_type == 'copyvar':
                self._handle_xschem_copyvar(
                    args['var_name'], args['color'], client_addr, connection_state
                )
            elif command_type == 'add_trace':
                self._handle_xschem_add_trace(
                    args['var_name'], args['axis'], args['color'], client_addr, connection_state
                )
            elif command_type == 'remove_trace':
                self._handle_xschem_remove_trace(
                    args['var_name'], client_addr, connection_state
                )
            elif command_type == 'get_data_point':
                self._handle_xschem_get_data_point(
                    args['x_value'], client_addr, connection_state
                )
            # Note: table_set and open_file are not queued as they trigger file loading
        # Clear processed commands
        self.pending_xschem_commands.clear()

    # Xschem command slot methods
    def _handle_xschem_table_set(self, raw_file: str, client_addr: str, connection_state: dict):
        """Handle xschem table_set command."""
        logger.info(f"Window {self.window_id} received table_set: {raw_file} from {client_addr}")
        # Check if this command is for this window
        is_for_this = self._is_command_for_this_window(client_addr, connection_state, raw_file=raw_file)
        logger.info(f"Window {self.window_id} table_set is_for_this_window: {is_for_this}")
        if not is_for_this:
            logger.info(f"Ignoring table_set, not for this window")
            return
        # Update client-window mapping
        self.state.window_registry.set_window_for_client(client_addr, self.window_id)
        # Load the raw file in this window
        logger.info(f"Loading raw file: {raw_file}")
        self._load_raw_file(raw_file)

    def _handle_xschem_copyvar(self, var_name: str, color: str, client_addr: str, connection_state: dict):
        """Handle xschem copyvar command."""
        logger.info(f"Window {self.window_id} received copyvar: {var_name} color {color} from {client_addr}")
        current_raw_file = connection_state.get('current_raw_file')
        logger.info(f"Current raw file from connection_state: {current_raw_file}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=current_raw_file):
            logger.info(f"Ignoring copyvar, not for this window")
            return

        # Parse color
        rgb = self._parse_color(color)
        if rgb is None:
            logger.warning(f"Invalid color format: {color}, using default red")
            rgb = (255, 0, 0)  # Red

        # Determine axis from variable name
        axis = self._detect_axis_from_var_name(var_name)

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.info(f"Raw file not loaded, queuing copyvar command for {var_name}")
            self._queue_xschem_command('copyvar', {
                'var_name': var_name,
                'color': color,
                'rgb': rgb,
                'axis': axis
            }, client_addr, connection_state)
            return

        # Get current X variable
        x_var = self._get_current_x_var()
        logger.info(f"Current X variable: {x_var}")
        if x_var is None:
            logger.error(f"Cannot add trace: no X variable set (raw file loaded but no X variable?)")
            return

        # Add trace with error collection
        error_messages = []
        logger.info(f"Adding trace for variable {var_name} on axis {axis} with color {color}")
        trace = self.trace_manager.add_trace_from_variable(
            variable_name=var_name,
            x_var_name=x_var,
            y_axis=axis,
            custom_color=rgb,
            error_out=error_messages
        )
        if trace is None:
            error_msg = f"Failed to add trace for variable: {var_name}"
            if error_messages:
                error_msg = f"Failed to add trace: {error_messages[0]}"
            logger.error(error_msg)
        else:
            logger.info(f"Successfully added trace for {var_name} on axis {axis} color {color}")

    def _handle_xschem_open_file(self, raw_file: str, client_addr: str, connection_state: dict):
        """Handle xschem open_file JSON command."""
        logger.debug(f"Window {self.window_id} received open_file: {raw_file} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=raw_file):
            logger.debug(f"Ignoring open_file, not for this window")
            return
        self.state.window_registry.set_window_for_client(client_addr, self.window_id)
        try:
            self._load_raw_file(raw_file)
            self._send_xschem_response(
                client_addr, connection_state,
                status="success",
                data={"loaded": True, "raw_file": raw_file, "window_id": self.window_id}
            )
        except Exception as e:
            logger.error(f"Failed to load raw file {raw_file}: {e}")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error",
                error=f"Failed to load raw file: {e}"
            )

    def _handle_xschem_add_trace(self, var_name: str, axis: str, color: str, client_addr: str, connection_state: dict):
        """Handle xschem add_trace JSON command."""
        logger.debug(f"Window {self.window_id} received add_trace: {var_name} axis {axis} color {color} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=connection_state.get('current_raw_file')):
            logger.debug(f"Ignoring add_trace, not for this window")
            return

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.debug(f"Raw file not loaded, queuing add_trace command for {var_name}")
            self._queue_xschem_command('add_trace', {
                'var_name': var_name,
                'axis': axis,
                'color': color
            }, client_addr, connection_state)
            return

        # Parse color
        rgb = self._parse_color(color)
        if rgb is None:
            logger.warning(f"Invalid color format: {color}, using default red")
            rgb = (255, 0, 0)  # Red

        # Determine axis assignment
        if axis == 'auto':
            y_axis = self._detect_axis_from_var_name(var_name)
        elif axis == 'Y1':
            y_axis = AxisAssignment.Y1
        elif axis == 'Y2':
            y_axis = AxisAssignment.Y2
        else:
            logger.warning(f"Invalid axis '{axis}', defaulting to auto detection")
            y_axis = self._detect_axis_from_var_name(var_name)

        # Get current X variable
        x_var = self._get_current_x_var()
        if x_var is None:
            logger.error(f"Cannot add trace: no X variable set (raw file not loaded?)")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error",
                error="No X variable set (raw file not loaded)"
            )
            return

        # Add trace with error collection
        error_messages = []
        trace = self.trace_manager.add_trace_from_variable(
            variable_name=var_name,
            x_var_name=x_var,
            y_axis=y_axis,
            custom_color=rgb,
            error_out=error_messages
        )
        if trace is None:
            error_msg = f"Failed to add trace for variable: {var_name}"
            if error_messages:
                # Use the first error message for more detail
                error_msg = error_messages[0]
            logger.error(error_msg)
            self._send_xschem_response(
                client_addr, connection_state,
                status="error",
                error=error_msg
            )
        else:
            logger.info(f"Added trace for {var_name} on axis {y_axis} color {color}")
            self._send_xschem_response(
                client_addr, connection_state,
                status="success",
                data={"added": True, "var_name": var_name, "axis": str(y_axis), "color": color}
            )

    def _handle_xschem_remove_trace(self, var_name: str, client_addr: str, connection_state: dict):
        """Handle xschem remove_trace JSON command."""
        logger.debug(f"Window {self.window_id} received remove_trace: {var_name} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=connection_state.get('current_raw_file')):
            logger.debug(f"Ignoring remove_trace, not for this window")
            return

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.debug(f"Raw file not loaded, queuing remove_trace command for {var_name}")
            self._queue_xschem_command('remove_trace', {
                'var_name': var_name
            }, client_addr, connection_state)
            return

        if self.trace_manager is None:
            logger.error("Cannot remove trace: trace_manager not initialized")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error", error="Trace manager not available"
            )
            return

        success = self.trace_manager.remove_trace_by_variable_name(var_name)
        if success:
            logger.info(f"Removed trace for variable '{var_name}'")
            self._send_xschem_response(
                client_addr, connection_state,
                status="success", data={"removed": var_name}
            )
        else:
            logger.warning(f"Trace not found for variable '{var_name}'")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error", error=f"Trace not found for variable '{var_name}'"
            )

    def _handle_xschem_get_data_point(self, x_value: float, client_addr: str, connection_state: dict):
        """Handle xschem get_data_point JSON command."""
        logger.debug(f"Window {self.window_id} received get_data_point: x={x_value} from {client_addr}")
        if not self._is_command_for_this_window(client_addr, connection_state, raw_file=connection_state.get('current_raw_file')):
            logger.debug(f"Ignoring get_data_point, not for this window")
            return

        # If raw file not yet loaded, queue command for later processing
        if self.raw_file is None:
            logger.debug(f"Raw file not loaded, queuing get_data_point command for x={x_value}")
            self._queue_xschem_command('get_data_point', {
                'x_value': x_value
            }, client_addr, connection_state)
            return

        if self.state is None or self.trace_manager is None:
            logger.error("Cannot query data point: state or trace_manager not initialized")
            self._send_xschem_response(
                client_addr, connection_state,
                status="error", error="Application not ready"
            )
            return

        results = self._query_data_point(x_value)
        # Convert numpy types to Python native types for JSON serialization
        # The _query_data_point already converts to float via float()
        # However, y_value may be complex, which is not JSON serializable.
        # We'll replace complex y_value with dict representation.
        serializable_results = []
        for res in results:
            res_copy = res.copy()
            y_val = res_copy.get('y_value')
            if isinstance(y_val, complex) or np.iscomplexobj(y_val):
                # Replace with magnitude/phase representation
                res_copy['y_value'] = {
                    'magnitude': float(np.abs(y_val)),
                    'phase_deg': float(np.angle(y_val, deg=True)),
                    'real': float(y_val.real),
                    'imag': float(y_val.imag)
                }
            elif isinstance(y_val, (np.floating, np.integer)):
                res_copy['y_value'] = float(y_val)
            # y_nearest may also be complex
            y_nearest = res_copy.get('y_nearest')
            if isinstance(y_nearest, complex) or np.iscomplexobj(y_nearest):
                res_copy['y_nearest'] = {
                    'magnitude': float(np.abs(y_nearest)),
                    'phase_deg': float(np.angle(y_nearest, deg=True)),
                    'real': float(y_nearest.real),
                    'imag': float(y_nearest.imag)
                }
            elif isinstance(y_nearest, (np.floating, np.integer)):
                res_copy['y_nearest'] = float(y_nearest)
            # Convert numpy bool to Python bool
            out_of_range = res_copy.get('out_of_range')
            if isinstance(out_of_range, np.bool_):
                res_copy['out_of_range'] = bool(out_of_range)
            serializable_results.append(res_copy)

        self._send_xschem_response(
            client_addr, connection_state,
            status="success",
            data={"x": x_value, "traces": serializable_results}
        )

    def _handle_xschem_close_window(self, window_id: str, client_addr: str, connection_state: dict):
        """Handle xschem close_window JSON command."""
        logger.debug(f"Window {self.window_id} received close_window: window_id={window_id} from {client_addr}")
        # If window_id matches this window, close it
        if window_id == self.window_id:
            self.close()
        # Otherwise ignore (could be for another window)

    def _handle_xschem_list_windows(self, client_addr: str, connection_state: dict):
        """Handle xschem list_windows JSON command."""
        logger.debug(f"Window {self.window_id} received list_windows from {client_addr}")
        registry = self.state.window_registry
        window_ids = registry.get_all_window_ids()
        windows = []
        for win_id in window_ids:
            win = registry.get_window_by_id(win_id)
            if win is not None:
                windows.append({
                    "window_id": win_id,
                    "raw_file": win.raw_file_path,
                    "title": win.windowTitle()
                })
            else:
                # Window reference lost (garbage collected)
                windows.append({
                    "window_id": win_id,
                    "raw_file": None,
                    "title": "(closed)"
                })
        self._send_xschem_response(
            client_addr, connection_state,
            status="success",
            data={"windows": windows}
        )

    def _handle_xschem_ping(self, client_addr: str, connection_state: dict):
        """Handle xschem ping JSON command."""
        logger.debug(f"Window {self.window_id} received ping from {client_addr}")
        from pqwave import __version__
        self._send_xschem_response(
            client_addr, connection_state,
            status="success",
            data={"pong": True, "version": f"pqwave {__version__}"}
        )

    def _handle_xschem_invalid_command(self, command_dict: dict, error_message: str):
        """Handle xschem invalid_command signal."""
        logger.warning(f"Invalid command received: {error_message} - {command_dict}")
        # Extract client info from command dict
        client_addr = command_dict.get('_client_addr', 'unknown')
        connection_state = command_dict.get('_connection_state', {})
        command_id = command_dict.get('id')

        # Only send response for JSON commands (those with an ID)
        if command_id is not None:
            response = {
                "status": "error",
                "error": error_message,
                "id": command_id
            }
            if self.state.command_handler is not None:
                self.state.command_handler.send_response(client_addr, response)
            else:
                logger.error("Cannot send error response: command_handler not available")

    def _is_command_for_this_window(self, client_addr: str, connection_state: dict, raw_file: Optional[str] = None) -> bool:
        """
        Determine if an xschem command is intended for this window.

        Checks:
        1. If client is already associated with this window (via registry)
        2. If raw_file matches this window's raw_file_path
        3. If this is the only window open (default)

        Returns True if command should be processed by this window.
        """
        logger.debug(f"_is_command_for_this_window: client={client_addr}, raw_file={raw_file}, window_id={self.window_id}")
        registry = self.state.window_registry
        # Check client-window mapping
        assigned_window = registry.get_window_for_client(client_addr)
        logger.debug(f"  assigned_window: {assigned_window.window_id if assigned_window else None}")
        if assigned_window is not None:
            # Client already assigned to a window
            return assigned_window.window_id == self.window_id

        # Check raw file mapping
        if raw_file is not None:
            file_window = registry.get_window_by_raw_file(raw_file)
            if file_window is not None:
                return file_window.window_id == self.window_id
            # If raw_file provided and not mapped, and this window has no raw file loaded,
            # accept the command (this window can load the file)
            if self.raw_file is None:
                logger.debug(f"  raw_file not mapped, this window has no raw file, accepting")
                return True

        # If no mapping exists, check if this is the only window
        all_windows = registry.get_all_window_ids()
        if len(all_windows) == 1 and all_windows[0] == self.window_id:
            return True

        # Default: not for this window
        return False

    # Xschem helper methods
    def _send_xschem_response(self, client_addr: str, connection_state: dict,
                              status: str = "success", data: Optional[dict] = None,
                              error: Optional[str] = None) -> bool:
        """
        Send JSON response to xschem client.

        Args:
            client_addr: Client address string "ip:port"
            connection_state: Connection state dict (contains command_id)
            status: "success" or "error"
            data: Optional response data dictionary
            error: Optional error message string

        Returns:
            True if response sent successfully, False otherwise.
        """
        if self.state.command_handler is None:
            logger.warning(f"Cannot send response: command_handler not available")
            return False

        response = {"status": status}
        if data is not None:
            response["data"] = data
        if error is not None:
            response["error"] = error

        # Include command ID if present in connection_state
        command_id = connection_state.get('command_id')
        if command_id is not None:
            response["id"] = command_id

        logger.debug(f"Sending xschem response to {client_addr}: {response}")
        return self.state.command_handler.send_response(client_addr, response)

    def _query_data_point(self, x_value: float) -> list:
        """
        Query data point at x coordinate across all traces in this window.

        Args:
            x_value: X coordinate (linear space)

        Returns:
            List of dictionaries with keys:
            - name: trace name (expression)
            - var_name: variable name (unquoted)
            - y_axis: 'Y1' or 'Y2'
            - color: RGB tuple
            - y_value: interpolated Y value (complex if complex data)
            - magnitude: magnitude (if complex)
            - phase_deg: phase in degrees (if complex)
            - real: real component (if complex)
            - imag: imaginary component (if complex)
            - x_nearest: nearest X data point (for reference)
            - y_nearest: nearest Y data point (for reference)
            - interpolation: 'linear' or 'nearest' (if within range)
            - out_of_range: True if x_value outside trace X range
        """
        results = []
        if self.state is None or not self.state.traces:
            return results

        for trace in self.state.traces:
            x_data = trace.x_data
            y_data = trace.y_data
            if len(x_data) == 0:
                continue

            x_min, x_max = np.min(x_data), np.max(x_data)
            out_of_range = bool(x_value < x_min or x_value > x_max)  # convert numpy bool to Python bool

            # Nearest neighbor indices
            idx = np.abs(x_data - x_value).argmin()
            x_nearest = float(x_data[idx])
            y_nearest = y_data[idx]  # may be complex
            # Convert numpy scalar to Python native type if not complex
            if np.iscomplexobj(y_nearest):
                pass  # keep as numpy complex (handled later)
            elif isinstance(y_nearest, (np.floating, np.integer)):
                y_nearest = float(y_nearest)

            # Linear interpolation if within range and more than one point
            if not out_of_range and len(x_data) > 1:
                # numpy.interp does not support complex; handle separately
                if np.iscomplexobj(y_data):
                    y_real = np.interp(x_value, x_data, y_data.real)
                    y_imag = np.interp(x_value, x_data, y_data.imag)
                    y_interp = y_real + 1j * y_imag
                else:
                    y_interp = np.interp(x_value, x_data, y_data)
                interpolation = 'linear'
                y_value = y_interp
            else:
                interpolation = 'nearest'
                y_value = y_nearest

            # Convert numpy scalar to Python native type if not complex
            if np.iscomplexobj(y_value):
                pass  # keep as numpy complex (handled later)
            elif isinstance(y_value, (np.floating, np.integer)):
                y_value = float(y_value)

            # Build result dict
            result = {
                'name': trace.name,
                'var_name': trace.expression,
                'y_axis': trace.y_axis.value,
                'color': trace.color,
                'y_value': y_value,
                'x_nearest': x_nearest,
                'y_nearest': y_nearest,
                'interpolation': interpolation,
                'out_of_range': out_of_range,
            }

            # Add complex data representation if applicable
            if np.iscomplexobj(y_value):
                result['magnitude'] = float(np.abs(y_value))
                result['phase_deg'] = float(np.angle(y_value, deg=True))
                result['real'] = float(y_value.real)
                result['imag'] = float(y_value.imag)

            results.append(result)

        return results

    def _parse_color(self, color_hex: str) -> Optional[Tuple[int, int, int]]:
        """
        Parse hexadecimal color string to RGB tuple (0-255).

        Supports formats: #rgb, #rgba, #rrggbb, #rrggbbaa
        Returns None if invalid.
        """
        if not color_hex.startswith('#'):
            return None
        hex_str = color_hex[1:]
        length = len(hex_str)
        if length not in (3, 4, 6, 8):
            return None
        try:
            # Expand shorthand
            if length == 3 or length == 4:
                hex_str = ''.join([c*2 for c in hex_str])
                # Now length 6 or 8
            # Convert to integer
            rgb_int = int(hex_str, 16)
            # Extract components (ignore alpha)
            if len(hex_str) >= 6:
                r = (rgb_int >> 16) & 0xFF
                g = (rgb_int >> 8) & 0xFF
                b = rgb_int & 0xFF
                return (r, g, b)
            else:
                return None
        except ValueError:
            return None

    def _detect_axis_from_var_name(self, var_name: str) -> AxisAssignment:
        """
        Detect appropriate Y axis for a SPICE variable name.

        Rules:
        - Current variables (starting with 'i(') -> Y2
        - Voltage variables (starting with 'v(') -> Y1
        - Default: Y1
        """
        import re
        # Match i(...) or v(...)
        match = re.match(r'^([iv])\(', var_name)
        if match:
            prefix = match.group(1)
            if prefix == 'i':
                return AxisAssignment.Y2
        return AxisAssignment.Y1

    def _connect_mark_panel(self):
        """Connect mark panel signals (called when panel is created)."""
        if self.mark_panel is not None:
            self.mark_panel.mark_deleted_last.connect(self._on_mark_deleted_last)
            self.mark_panel.window_closed.connect(self._on_mark_panel_closed)

    def _update_trace_manager_log_modes(self):
        """Update trace manager with current log mode settings."""
        x_config = self.state.get_axis_config(AxisId.X)
        y1_config = self.state.get_axis_config(AxisId.Y1)
        y2_config = self.state.get_axis_config(AxisId.Y2)

        self.trace_manager.set_log_modes(
            x_log=x_config.log_mode,
            y1_log=y1_config.log_mode,
            y2_log=y2_config.log_mode
        )

    # Menu callbacks

    def open_file(self):
        """Open a raw file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Raw File", "", "Raw Files (*.raw);;All Files (*)"
        )
        if filename:
            self._load_raw_file(filename)

    def open_new_window(self):
        """Open a new MainWindow instance."""
        new_window = MainWindow()
        new_window.show()

    def convert_raw_data(self):
        """Convert currently loaded raw data to another format."""
        if not self.raw_file or not self.raw_file.datasets:
            QMessageBox.warning(
                self, "No Data",
                "No raw data loaded. Open a raw file first before converting."
            )
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QPushButton

        dataset = self.raw_file.datasets[0]  # Use first dataset
        title = dataset.get('title', 'pqwave conversion')
        date = dataset.get('date', '')
        plotname = dataset.get('plotname', '')
        flags = dataset.get('flags', '')
        variables = dataset.get('variables', [])
        data = dataset.get('data', np.array([]))
        is_ac_or_complex = dataset.get('_is_ac_or_complex', False)

        # Detect source format from spicelib's dialect detection
        if self.raw_file.raw_data:
            detected = self.raw_file.raw_data.dialect
            if detected in ('ltspice', 'qspice', 'ngspice', 'xyce'):
                src_format = detected
            else:
                # Fallback to extension-based detection
                src_file = self.raw_file.filename.lower()
                if src_file.endswith('.qraw'):
                    src_format = 'qspice'
                else:
                    src_format = 'ltspice'
        else:
            src_format = 'ltspice'

        # Show format selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Convert Raw Data")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout()

        info_label = QLabel(
            f"Source: {src_format.upper()}\n"
            f"Variables: {len(variables)}\n"
            f"Points: {data.shape[0] if data.ndim > 0 else 0}"
        )
        layout.addWidget(info_label)

        layout.addWidget(QLabel("Target format:"))

        format_group = []
        for fmt_key, fmt_config in FORMAT_CONFIG.items():
            label = f"{fmt_key.upper()} ({fmt_config['extension']})"
            rb = QRadioButton(label)
            if fmt_key == src_format:
                rb.setEnabled(False)  # Disable current format
            else:
                rb.setChecked(True)  # Default to first non-source format
            format_group.append((fmt_key, rb))
            layout.addWidget(rb)

        # Button box
        button_layout = QHBoxLayout()
        convert_btn = QPushButton("Convert")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(convert_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        def do_convert():
            target_fmt = None
            for fmt_key, rb in format_group:
                if rb.isChecked():
                    target_fmt = fmt_key
                    break

            if target_fmt is None:
                QMessageBox.warning(dialog, "Error", "Please select a target format.")
                return

            dialog.accept()

            # Show save file dialog
            ext = FORMAT_CONFIG[target_fmt]['extension']
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Converted Raw File",
                "",
                f"Raw Files (*{ext});;All Files (*)"
            )

            if not save_path:
                return

            try:
                write_raw_file(
                    output_path=save_path,
                    title=title,
                    date=date,
                    plotname=plotname,
                    flags=flags,
                    variables=variables,
                    data=data,
                    target_format=target_fmt,
                    is_ac_or_complex=is_ac_or_complex,
                )
                QMessageBox.information(
                    self, "Conversion Successful",
                    f"Converted to {target_fmt.upper()} format:\n{save_path}"
                )
                logger.info(f"Raw data converted to {save_path} ({target_fmt})")
            except Exception as e:
                logger.exception(f"Conversion failed: {e}")
                QMessageBox.critical(
                    self, "Conversion Failed",
                    f"Failed to convert raw data:\n{e}"
                )

        convert_btn.clicked.connect(do_convert)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def edit_trace_properties(self):
        """Edit trace properties (alias, color, line width)"""
        logger.debug(f"edit_trace_properties called, traces count: {len(self.trace_manager.traces)}")
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLineEdit, QPushButton, QHBoxLayout, QLabel, QComboBox

        # Get traces from trace manager
        traces = self.trace_manager.traces
        if not traces:
            QMessageBox.information(self, "No Traces", "No traces to edit.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Trace Properties")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # Create list widget for traces
        list_widget = QListWidget()
        for i, (var, plot_item, y_axis) in enumerate(traces):
            list_widget.addItem(f"{i+1}. {var} @ {y_axis}")

        layout.addWidget(list_widget)

        # Create alias edit
        alias_layout = QHBoxLayout()
        alias_label = QLabel("Alias:")
        self.alias_edit = QLineEdit()
        alias_layout.addWidget(alias_label)
        alias_layout.addWidget(self.alias_edit)
        layout.addLayout(alias_layout)

        # Create color combo
        color_layout = QHBoxLayout()
        color_label = QLabel("Color:")
        self.color_combo = QComboBox()
        # Add color options
        colors = [
            ("Default (auto)", None),
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
            ("Yellow", (255, 255, 0)),
            ("Magenta", (255, 0, 255)),
            ("Cyan", (0, 255, 255)),
            ("Orange", (255, 165, 0)),
            ("Purple", (128, 0, 128)),
            ("Brown", (165, 42, 42))
        ]
        for color_name, color_value in colors:
            self.color_combo.addItem(color_name, color_value)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_combo)
        layout.addLayout(color_layout)

        # Create line width combo
        width_layout = QHBoxLayout()
        width_label = QLabel("Line width:")
        self.width_combo = QComboBox()
        # Add line width options
        widths = [1, 2, 3, 4, 5]
        for width in widths:
            self.width_combo.addItem(str(width), width)
        width_layout.addWidget(width_label)
        width_layout.addWidget(self.width_combo)
        layout.addLayout(width_layout)

        # Connect list selection change to update all fields
        list_widget.currentRowChanged.connect(lambda row: self._update_trace_properties(row, list_widget))

        # Create buttons
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(lambda: self._apply_trace_properties(list_widget.currentRow(), list_widget))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        # Select first trace if available
        if traces:
            list_widget.setCurrentRow(0)
            self._update_trace_properties(0, list_widget)

        dialog.exec()

    def _update_trace_properties(self, row, list_widget):
        """Update trace properties fields with current trace values"""
        if 0 <= row < len(self.trace_manager.traces):
            var, plot_item, y_axis = self.trace_manager.traces[row]
            # Update alias field
            self.alias_edit.setText(var)

            # Update color combo
            current_color = plot_item.opts['pen'].color()
            current_rgb = (current_color.red(), current_color.green(), current_color.blue())

            # Find matching color in combo
            color_index = 0  # Default to "Default (auto)"
            for i in range(self.color_combo.count()):
                color_value = self.color_combo.itemData(i)
                if color_value == current_rgb:
                    color_index = i
                    break
            self.color_combo.setCurrentIndex(color_index)

            # Update line width combo
            current_width = plot_item.opts['pen'].width()
            width_index = 0  # Default to 1
            for i in range(self.width_combo.count()):
                width_value = self.width_combo.itemData(i)
                if width_value == current_width:
                    width_index = i
                    break
            self.width_combo.setCurrentIndex(width_index)

    def _apply_trace_properties(self, row, list_widget):
        """Apply trace properties (alias, color, line width)"""

        if 0 <= row < len(self.trace_manager.traces):
            var, plot_item, y_axis = self.trace_manager.traces[row]

            # Get new values
            new_alias = self.alias_edit.text().strip()
            new_color = self.color_combo.currentData()
            new_width = self.width_combo.currentData()

            # Find matching Trace object in state
            trace_obj = None
            for trace in self.state.traces:
                if trace.name == var:
                    trace_obj = trace
                    break

            # Update alias if provided
            if new_alias and new_alias != var:
                # Update plot item name
                plot_item.opts['name'] = new_alias
                # Update trace manager traces list
                self.trace_manager.traces[row] = (new_alias, plot_item, y_axis)
                # Update Trace object name if found
                if trace_obj:
                    trace_obj.name = new_alias
                # Update list widget display
                list_widget.item(row).setText(f"{row+1}. {new_alias} @ {y_axis}")

            # Update color if not None (None means "Default (auto)")
            if new_color is not None:
                qcolor = QColor(*new_color)
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=qcolor, width=pen.width())
                plot_item.setPen(new_pen)
                # Update Trace object color if found
                if trace_obj:
                    trace_obj.color = new_color

            # Update line width
            if new_width:
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=pen.color(), width=new_width)
                plot_item.setPen(new_pen)
                # Update Trace object line width if found
                if trace_obj:
                    trace_obj.line_width = new_width

            # Refresh legend - trace manager should handle this
            # We'll call trace manager's method to update legend for this trace
            self._refresh_legend_for_trace(row, new_alias if new_alias else var, y_axis)

    def _refresh_legend_for_trace(self, trace_idx, trace_name, y_axis):
        """Refresh legend entry for a specific trace"""
        # The legend is managed by trace manager, but we need to update the legend item.
        # Since trace manager's legend items are added with format "{name} @ {y_axis}",
        # we can clear and re-add all legend items, or find and update the specific one.
        # For simplicity, we'll clear and re-add all legend items.
        legend = self.trace_manager.legend
        if legend:
            legend.clear()
            # Re-add all traces to legend
            for i, (var, plot_item, axis) in enumerate(self.trace_manager.traces):
                legend_name = f"{var} @ {axis}"
                legend.addItem(plot_item, legend_name)

    def show_settings(self):
        """Show application settings widget."""
        # Create settings widget if it doesn't exist or was closed
        if not hasattr(self, '_settings_widget') or self._settings_widget is None:
            self._settings_widget = SettingsWidget(
                axis_manager=self.axis_manager,
                application_state=self.state,
                parent=self
            )
            # Connect signals
            self._settings_widget.plot_title_changed.connect(self._on_plot_title_changed)
            self._settings_widget.viewbox_theme_changed.connect(self._on_viewbox_theme_changed)
            self._settings_widget.destroyed.connect(lambda: setattr(self, '_settings_widget', None))

        # Show and raise the widget
        self._settings_widget.show()
        self._settings_widget.raise_()
        self._settings_widget.activateWindow()

    def _on_plot_title_changed(self, title: str):
        """Handle plot title changes from settings widget."""
        # Update plot widget title
        self.plot_widget.set_plot_title(title)

    def _on_viewbox_theme_changed(self, theme: ViewboxTheme) -> None:
        """Handle viewbox theme changes from settings widget."""
        self.plot_widget.set_viewbox_theme(theme)

    def toggle_toolbar(self):
        """Toggle toolbar visibility."""
        self.set_toolbar_visible(not self.menu_manager.toolbar.isVisible())

    def toggle_statusbar(self):
        """Toggle status bar visibility."""
        self.set_statusbar_visible(not self.menu_manager.statusbar.isVisible())

    def toggle_grids(self):
        """Toggle grid visibility."""
        visible = self.axis_manager.get_grid_visible()
        self.axis_manager.set_grid_visible(not visible)

        # Update menu manager toggle state
        self.menu_manager.set_grids_visible(not visible)

    def set_toolbar_visible(self, visible):
        """Set toolbar visibility and update state."""
        self.menu_manager.set_toolbar_visible(visible)
        self.state.toolbar_visible = visible

    def set_statusbar_visible(self, visible):
        """Set status bar visibility and update state."""
        self.menu_manager.set_statusbar_visible(visible)
        self.state.status_bar_visible = visible

    def set_legend_visible(self, visible):
        """Set legend visibility and update state."""
        if self.legend:
            self.legend.setVisible(visible)
        self.state.legend_visible = visible

    def zoom_in(self):
        """Zoom in."""
        if self.plot_widget and self.plot_widget.plotItem:
            self.plot_widget.plotItem.vb.scaleBy(s=(0.8, 0.8))

    def zoom_out(self):
        """Zoom out."""
        if self.plot_widget and self.plot_widget.plotItem:
            self.plot_widget.plotItem.vb.scaleBy(s=(1.25, 1.25))

    def zoom_to_fit(self):
        """Auto-range all axes."""
        self.axis_manager.auto_range_axis(AxisId.X)
        self.axis_manager.auto_range_axis(AxisId.Y1)
        self.axis_manager.auto_range_axis(AxisId.Y2)

    def auto_range_x(self):
        """Auto-range X-axis."""
        self.axis_manager.auto_range_axis(AxisId.X)

    def auto_range_y(self):
        """Auto-range Y axes."""
        self.axis_manager.auto_range_axis(AxisId.Y1)
        self.axis_manager.auto_range_axis(AxisId.Y2)

    def enable_zoom_box(self):
        """Enable/disable zoom box mode."""
        # Toggle zoom box state
        self.zoom_box_enabled = not self.zoom_box_enabled

        # Update plot widget
        if self.plot_widget:
            self.plot_widget.enable_zoom_box(self.zoom_box_enabled)

        # Synchronize menu and toolbar actions
        if self.menu_manager:
            self.menu_manager.actions['zoom_box'].setChecked(self.zoom_box_enabled)
            self.menu_manager.actions['zoom_box_toolbar'].setChecked(self.zoom_box_enabled)

    # Cross-hair cursor and marks

    def toggle_cross_hair(self):
        """Toggle cross-hair cursor ON/OFF.

        When turning ON: shows cross-hair and opens the mark data panel.
        When turning OFF: hides cross-hair, clears all marks, closes mark panel.
        Note: X/Y cursors are independent and not affected by cross-hair toggle.
        """
        self.cross_hair_visible = not self.cross_hair_visible

        # Update plot widget (cross-hair only — X/Y cursors are independent)
        self.plot_widget.set_cross_hair_visible(self.cross_hair_visible)

        # Update menu and toolbar state
        if self.menu_manager:
            self.menu_manager.set_cross_hair_visible(self.cross_hair_visible)

        if self.cross_hair_visible:
            self._open_mark_panel()
        else:
            self._close_mark_panel()

    def _toggle_x_cursor_a(self, checked: bool) -> None:
        """Toggle X cursor a on/off."""
        self.plot_widget.set_cursor_xa_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_x_cursor_a_checked(checked)
        self._update_cursor_status()

    def _toggle_x_cursor_b(self, checked: bool) -> None:
        """Toggle X cursor b on/off."""
        self.plot_widget.set_cursor_xb_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_x_cursor_b_checked(checked)
        self._update_cursor_status()

    def _toggle_y_cursor_A(self, checked: bool) -> None:
        """Toggle Y cursor A on/off."""
        self.plot_widget.set_cursor_yA_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_y_cursor_A_checked(checked)
        self._update_cursor_status()

    def _toggle_y_cursor_B(self, checked: bool) -> None:
        """Toggle Y cursor B on/off."""
        self.plot_widget.set_cursor_yB_visible(checked)
        if self.menu_manager:
            self.menu_manager.set_y_cursor_B_checked(checked)
        self._update_cursor_status()

    def _open_mark_panel(self):
        """Create and show the mark data panel."""
        if self.mark_panel is None:
            self.mark_panel = MarkPanel(parent=self)
            self._connect_mark_panel()
        self.mark_panel.clear_all_marks()
        self.mark_panel.show()
        self.mark_panel.raise_()
        self.mark_panel.activateWindow()

    def _close_mark_panel(self):
        """Close the mark panel and clear all marks."""
        self.plot_widget.clear_marks()
        if self.mark_panel is not None:
            self.mark_panel.close()
            self.mark_panel = None

    @pyqtSlot(float, float, float, float, float)
    def _on_mark_clicked(self, x_vb, y1_vb, x_linear, y1_linear, y2_linear):
        """Handle mark placement from plot widget click.

        Args:
            x_vb, y1_vb: Viewbox coordinates (for mark rendering in plot space)
            x_linear, y1_linear, y2_linear: Linear display values (for data panel)
        """
        self.plot_widget.add_mark_at_position(x_vb, y1_vb)
        if self.mark_panel is not None:
            # Re-show panel if user had closed it via window close button
            self.mark_panel.show()
            self.mark_panel.raise_()
            self.mark_panel.activateWindow()
            self.mark_panel.add_mark(x_linear, y1_linear, y2_linear)

    @pyqtSlot()
    def _on_mark_panel_closed(self):
        """Handle mark panel window close button — hide without destroying."""
        if self.mark_panel is not None:
            self.mark_panel.hide()

    @pyqtSlot()
    def _on_mark_deleted_last(self):
        """Handle mark deletion from mark panel button."""
        self.plot_widget.remove_last_mark()

    # Raw file handling

    def _load_raw_file(self, filename):
        """Load raw file and update UI."""
        try:
            # 1. Clear existing traces from plot widget BEFORE replacing raw_file.
            #    This ensures Qt objects don't hold references to old data when
            #    the old RawFile is garbage-collected and its temp files deleted.
            self.trace_manager.clear_traces()
            self.trace_manager.set_raw_file(None)

            # 2. Parse the new file (does NOT touch self.raw_file yet)
            new_raw_file = RawFile(filename)

            # 3. Clear application state (releases old datasets)
            self.state.clear_datasets()

            # 4. Now safe to replace self.raw_file — old one has no remaining refs
            self.raw_file = new_raw_file
            # Update window registry mapping
            self._update_window_registry_raw_file(filename)

            # 5. Populate UI with new data
            for i in range(len(self.raw_file.datasets)):
                dataset = Dataset(self.raw_file, i)
                self.state.add_dataset(dataset)

            # Set current dataset to first one
            if self.state.datasets:
                self.state.current_dataset_idx = 0
                # Set current X variable to first variable
                var_names = self.raw_file.get_variable_names(0)
                if var_names:
                    self.state.current_x_var = var_names[0]
                    logger.info(f"Auto-set X variable to: {self.state.current_x_var}")
                    # Update X-axis label
                    self.axis_manager.set_axis_label(AxisId.X, self.state.current_x_var)

            # Update control panel
            self._update_dataset_combo()
            self._update_variable_combo()
            self.control_panel.clear_expression()  # Clear trace expression for new file

            # Set raw file reference in trace manager
            self.trace_manager.set_raw_file(self.raw_file)

            # Update trace manager with current log mode settings from state
            self._update_trace_manager_log_modes()

            # Auto-range axes
            self.auto_range_x()
            self.auto_range_y()

            # Update window title
            self.setWindowTitle(f"pqwave - {filename}")

            # Update status bar dataset label
            self._update_dataset_label()

            logger.info(f"Successfully loaded: {filename}")
            # Process any pending xschem commands that arrived before file was loaded
            self._process_pending_xschem_commands()

        except FileNotFoundError as e:
            self._show_error("File not found", f"File not found: {filename}\n\n{e}")
        except Exception as e:
            logger.exception(f"Error opening file: {filename}")
            error_msg = str(e)
            if "Invalid RAW file" in error_msg:
                self._show_error("Invalid RAW file", f"Invalid RAW file format: {filename}\n\n{error_msg}")
            else:
                self._show_error("Error opening file", f"Error opening file: {filename}\n\n{error_msg}")

    def _update_window_registry_raw_file(self, raw_file_path):
        """Update window registry mapping for this window's raw file."""
        self.raw_file_path = raw_file_path
        # Re-register with new raw file path
        self.state.window_registry.register_window(
            window_id=self.window_id,
            window_instance=self,
            raw_file_path=self.raw_file_path
        )

    def _load_initial_file(self):
        """Load the initial file provided via command line."""
        if self.initial_file_loaded:
            return
        if self.initial_file:
            logger.info(f"Loading initial file: {self.initial_file}")
            self._load_raw_file(self.initial_file)
            self.initial_file_loaded = True

    def _update_dataset_combo(self):
        """Update dataset combo box in control panel."""
        if self.raw_file:
            datasets = []
            for i, dataset in enumerate(self.raw_file.datasets):
                plotname = dataset.get('plotname', f'Dataset {i+1}')
                datasets.append(f"Dataset {i+1}: {plotname}")
            self.control_panel.set_datasets(datasets)

    def _update_variable_combo(self):
        """Update variable combo box in control panel."""
        if self.raw_file and self.state.current_dataset_idx is not None:
            var_names = self.raw_file.get_variable_names(self.state.current_dataset_idx)
            self.control_panel.set_variables(var_names)

    def _update_dataset_label(self):
        """Update dataset label in status bar."""
        if self.raw_file and self.raw_file.datasets:
            total_datasets = len(self.raw_file.datasets)
            current_dataset = self.state.current_dataset_idx + 1
            self.menu_manager.update_dataset_label(f"{current_dataset}/{total_datasets}")
        else:
            self.menu_manager.update_dataset_label("-")

    # Signal handlers

    @pyqtSlot(int)
    def _on_dataset_changed(self, index):
        """Handle dataset selection change."""
        self.state.current_dataset_idx = index
        self.trace_manager.set_current_dataset(index)
        self._update_variable_combo()
        self._update_dataset_label()
        # Clear trace expression as previous expression may not be valid for new dataset
        self.control_panel.clear_expression()

        # TODO: Update traces for new dataset

    @pyqtSlot(str)
    def _on_vector_selected(self, vector):
        """Handle vector selection."""
        # Add selected vector to trace expression, avoiding duplicates
        if not vector:
            return
        current_text = self.control_panel.trace_expr.text()
        if current_text:
            # Split by whitespace to check if vector already present
            parts = current_text.split()
            if vector in parts:
                # Vector already in expression, do nothing
                return
            new_text = f"{current_text} {vector}"
        else:
            new_text = vector
        self.control_panel.trace_expr.setText(new_text)

    @pyqtSlot(str)
    def _on_add_trace_to_axis(self, axis):
        """Handle add trace to axis button click."""
        expression = self.control_panel.trace_expr.text().strip()
        if not expression:
            QMessageBox.warning(self, "No Expression", "Please enter an expression first.")
            return

        if axis == "X":
            # X button sets X-axis variable
            # For simplicity, treat whole expression as variable name
            x_var = expression.strip()
            # Validate it's a single variable (no spaces)
            if ' ' in x_var:
                QMessageBox.warning(self, "Invalid X-axis", "X-axis can only have one variable/expression.")
                return

            # Store X-axis variable
            self.state.current_x_var = x_var

            # Update X-axis label
            self.axis_manager.set_axis_label(AxisId.X, x_var)

            # Auto-range X-axis based on new variable
            if self.raw_file and self.state.current_dataset_idx is not None:
                x_data = self.raw_file.get_variable_data(x_var, self.state.current_dataset_idx)
                if x_data is not None:
                    self.axis_manager.auto_range_x_from_data(x_data, x_var)

            # Clear expression after successful addition
            self.control_panel.trace_expr.clear()
            logger.info(f"Set X-axis variable to: {x_var}")

        elif axis in ["Y1", "Y2"]:
            # Y1/Y2 buttons add traces
            # Get current X-axis variable
            x_var = self._get_current_x_var()
            if not x_var:
                QMessageBox.warning(self, "No X-axis", "Please select an X-axis variable.")
                return

            # Map axis string to AxisAssignment
            if axis == "Y1":
                y_axis = AxisAssignment.Y1
            else:  # Y2
                y_axis = AxisAssignment.Y2

            # Add trace
            trace = self.trace_manager.add_trace(expression, x_var, y_axis)
            if trace:
                logger.info(f"Added trace: {trace.name} to {y_axis.value}")
                # Clear expression after successful addition
                self.control_panel.trace_expr.clear()
            else:
                QMessageBox.warning(self, "Error", f"Failed to add trace for expression: {expression}")
        else:
            logger.warning(f"Unknown axis: {axis}")

    @pyqtSlot(str)
    def _on_expression_changed(self, expression):
        """Handle trace expression text change."""
        # Nothing to do here for now
        pass

    @pyqtSlot(float, float, float)
    def _on_mouse_moved(self, x, y1, y2):
        """Handle mouse movement in plot."""
        self.menu_manager.update_coordinate_label(x, y1, y2)

    @pyqtSlot()
    def _on_mouse_left(self):
        """Handle mouse leaving plot."""
        self.menu_manager.update_coordinate_label(None, None, None)

    @pyqtSlot(float)
    def _on_cursor_xa_changed(self, value):
        """Handle X1 cursor position change — triggers back-annotation + status update."""
        # Convert ViewBox coordinate to linear space if X axis is in log mode
        x_linear = value
        if self.plot_widget.get_axis_log_mode('X'):
            x_linear = self.plot_widget._log_to_linear(value)

        # Store X value and start debounce timer for back-annotation
        self._pending_x_value = x_linear
        self._backannotation_timer.start()

        self._update_cursor_status()

    @pyqtSlot(float)
    def _on_cursor_xb_changed(self, value):
        """Handle X2 cursor position change."""
        self._update_cursor_status()

    @pyqtSlot(float)
    def _on_cursor_yA_changed(self, value):
        """Handle YA cursor position change."""
        self._update_cursor_status()

    @pyqtSlot(float)
    def _on_cursor_yB_changed(self, value):
        """Handle YB cursor position change."""
        self._update_cursor_status()

    @pyqtSlot(float)
    def _on_cursor_y2_changed(self, value):
        """Handle Y2 cursor position change (Y2-axis-specific cursor)."""
        pass

    def _update_cursor_status(self) -> None:
        """Read cursor positions and deltas, update status bar and legend."""
        positions = self.plot_widget.get_cursor_positions()
        deltas = self.plot_widget.get_cursor_deltas()
        if self.menu_manager:
            self.menu_manager.update_cursor_status(positions, deltas)
        self._update_legend_cursor_values()

    def _update_legend_cursor_values(self) -> None:
        """Update trace legend with Y values at visible X cursor positions."""
        positions = self.plot_widget.get_cursor_positions()
        xa = positions.get('xa')
        xb = positions.get('xb')

        # Convert viewbox coordinates to linear space for data interpolation
        xa_lin = (self.plot_widget._log_to_linear(xa)
                  if xa is not None and self.plot_widget._x_log_mode
                  else xa)
        xb_lin = (self.plot_widget._log_to_linear(xb)
                  if xb is not None and self.plot_widget._x_log_mode
                  else xb)

        self.trace_manager.update_legend_cursor_values(xa_lin, xb_lin)

    def _send_data_point_update_debounced(self):
        """Send data point update after debounce timer fires."""
        if self._pending_x_value is not None:
            self._send_data_point_update(self._pending_x_value)
            self._pending_x_value = None

    def _send_data_point_update(self, x_value: float):
        """
        Send data point update to all xschem clients connected to this window.

        Args:
            x_value: X coordinate in linear space
        """
        logger.debug(f"_send_data_point_update called with x={x_value}")
        if self.state is None or self.state.command_handler is None:
            logger.debug("State or command_handler is None, returning")
            return

        # Query data points at this X coordinate
        results = self._query_data_point(x_value)
        if not results:
            return

        # Get all clients associated with this window
        registry = self.state.window_registry
        clients = registry.get_clients_for_window(self.window_id)
        logger.debug(f"Found {len(clients)} clients for window {self.window_id}: {clients}")
        if not clients:
            logger.debug("No clients found for this window")
            return

        # Prepare data for JSON serialization (similar to get_data_point response)
        serializable_results = []
        for res in results:
            res_copy = res.copy()
            y_val = res_copy.get('y_value')
            if isinstance(y_val, complex) or np.iscomplexobj(y_val):
                # Replace with magnitude/phase representation
                res_copy['y_value'] = {
                    'magnitude': float(np.abs(y_val)),
                    'phase_deg': float(np.angle(y_val, deg=True)),
                    'real': float(y_val.real),
                    'imag': float(y_val.imag)
                }
            elif isinstance(y_val, (np.floating, np.integer)):
                res_copy['y_value'] = float(y_val)
            # y_nearest may also be complex
            y_nearest = res_copy.get('y_nearest')
            if isinstance(y_nearest, complex) or np.iscomplexobj(y_nearest):
                res_copy['y_nearest'] = {
                    'magnitude': float(np.abs(y_nearest)),
                    'phase_deg': float(np.angle(y_nearest, deg=True)),
                    'real': float(y_nearest.real),
                    'imag': float(y_nearest.imag)
                }
            elif isinstance(y_nearest, (np.floating, np.integer)):
                res_copy['y_nearest'] = float(y_nearest)
            # Convert numpy bool to Python bool
            out_of_range = res_copy.get('out_of_range')
            if isinstance(out_of_range, np.bool_):
                res_copy['out_of_range'] = bool(out_of_range)
            serializable_results.append(res_copy)

        # Send update to each client
        for client_addr in clients:
            # Create update message (similar to get_data_point response but with different command)
            update_msg = {
                "command": "data_point_update",
                "data": {
                    "x": x_value,
                    "traces": serializable_results
                },
                "timestamp": time.time() if 'time' in sys.modules else 0
            }

            # Send via command handler with "json " prefix (xschem expects this format)
            # Get xschem server from command handler
            xschem_server = self.state.command_handler.xschem_server
            if xschem_server is None:
                logger.warning(f"Cannot send data_point_update: xschem server not available")
                continue

            # Parse client address string
            try:
                ip_str, port_str = client_addr.split(':')
                client_addr_tuple = (ip_str, int(port_str))
            except (ValueError, TypeError):
                logger.error(f"Invalid client address format: {client_addr}")
                continue

            # Find client socket
            client_socket = xschem_server.clients.get(client_addr_tuple)
            if not client_socket:
                logger.warning(f"Client socket not found: {client_addr}")
                continue

            # Send JSON command with "json " prefix
            try:
                json_str = json.dumps(update_msg)
                line = f"json {json_str}"
                logger.debug(f"Sending data_point_update to {client_addr}: {line[:100]}...")
                client_socket.sendall((line + '\n').encode('utf-8'))
                logger.debug(f"Sent data_point_update to {client_addr}: x={x_value}")
            except (socket.error, TypeError) as e:
                logger.error(f"Failed to send data_point_update to {client_addr}: {e}")

    # (Cross-hair mark handlers follow below)

    @pyqtSlot(str, bool)
    def _on_axis_log_mode_changed(self, orientation, log_mode):
        """Handle axis log mode change from plot widget."""
        # This signal comes from plot widget's LogAxisItem
        # AxisManager should already handle this via its connection
        # We just need to update trace manager
        self._update_trace_manager_log_modes()

        # Update traces for new log mode
        self.trace_manager.update_traces_for_log_mode()

    @pyqtSlot(str, bool)
    def _on_axis_log_mode_changed_from_manager(self, axis_id, log_mode):
        """Handle axis log mode change from axis manager."""
        # Update trace manager
        self._update_trace_manager_log_modes()

        # Update traces for new log mode
        self.trace_manager.update_traces_for_log_mode()

    @pyqtSlot(str, float, float)
    def _on_axis_range_changed(self, axis_id, min_val, max_val):
        """Handle axis range change."""
        # TODO: Update range display if needed
        pass

    @pyqtSlot(str, str)
    def _on_axis_label_changed(self, axis_id, label):
        """Handle axis label change."""
        # TODO: Update label display if needed
        pass

    # Helper methods

    def _get_current_x_var(self):
        """Get current X-axis variable name."""
        # Return stored X variable if set
        if self.state.current_x_var:
            return self.state.current_x_var

        # Otherwise return first variable if available
        if self.raw_file and self.state.current_dataset_idx is not None:
            var_names = self.raw_file.get_variable_names(self.state.current_dataset_idx)
            if var_names:
                return var_names[0]
        return None

    def _show_error(self, title, message):
        """Show error message dialog."""
        logger.error(f"{title}: {message}")
        QMessageBox.warning(self, title, message)

    # Public API for testing

    def get_plot_widget(self):
        """Get plot widget reference (for testing)."""
        return self.plot_widget

    def get_control_panel(self):
        """Get control panel reference (for testing)."""
        return self.control_panel

    def get_trace_manager(self):
        """Get trace manager reference (for testing)."""
        return self.trace_manager

    def get_axis_manager(self):
        """Get axis manager reference (for testing)."""
        return self.axis_manager

    def closeEvent(self, event):
        """Handle window close event."""
        # Unregister window from xschem integration registry
        self.state.window_registry.unregister_window(self.window_id)
        super().closeEvent(event)


if __name__ == "__main__":
    # Simple test runner
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())