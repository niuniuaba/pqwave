#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Command handler for xschem integration.

This module provides a command handler that processes commands from the XschemServer
and emits specific Qt signals for different command types. It validates commands
and extracts parameters for the main application to process.
"""

import logging
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class CommandHandler(QObject):
    """
    Handles xschem commands and emits specific Qt signals.

    Signals:
        table_set_received: Emitted for table_set commands
        copyvar_received: Emitted for copyvar commands
        open_file_received: Emitted for open_file JSON commands
        add_trace_received: Emitted for add_trace JSON commands
        remove_trace_received: Emitted for remove_trace JSON commands
        get_data_point_received: Emitted for get_data_point JSON commands
        close_window_received: Emitted for close_window JSON commands
        list_windows_received: Emitted for list_windows JSON commands
        ping_received: Emitted for ping JSON commands
        invalid_command_received: Emitted for invalid commands
    """

    # Command-specific signals
    table_set_received = pyqtSignal(str, str, dict)  # raw_file, client_addr, connection_state
    copyvar_received = pyqtSignal(str, str, str, dict)  # var_name, color, client_addr, connection_state

    # JSON command signals
    open_file_received = pyqtSignal(str, str, dict)  # raw_file, client_addr, connection_state
    add_trace_received = pyqtSignal(str, str, str, str, dict)  # var_name, axis, color, client_addr, connection_state
    remove_trace_received = pyqtSignal(str, str, dict)  # var_name, client_addr, connection_state
    get_data_point_received = pyqtSignal(float, str, dict)  # x_value, client_addr, connection_state
    close_window_received = pyqtSignal(str, str, dict)  # window_id, client_addr, connection_state
    list_windows_received = pyqtSignal(str, dict)  # client_addr, connection_state
    ping_received = pyqtSignal(str, dict)  # client_addr, connection_state

    # Error signal
    invalid_command_received = pyqtSignal(dict, str)  # command_dict, error_message

    def __init__(self):
        """Initialize CommandHandler."""
        super().__init__()
        self.xschem_server = None
        logger.debug("CommandHandler initialized")

    def set_server(self, xschem_server):
        """Set reference to XschemServer for sending responses."""
        self.xschem_server = xschem_server

    def send_response(self, client_addr: str, response: dict) -> bool:
        """Send JSON response to client via xschem server."""
        if self.xschem_server is None:
            logger.error("Cannot send response: xschem server not set")
            return False
        return self.xschem_server.send_response(client_addr, response)
    def handle_command(self, command_dict: dict) -> None:
        """
        Process a command dictionary and emit appropriate signals.

        Args:
            command_dict: Command dictionary from XschemServer
        """
        try:
            # Extract common fields
            client_addr = command_dict.get('_client_addr', 'unknown')
            connection_state = command_dict.get('_connection_state', {})
            # Store command ID in connection state for response routing
            if 'id' in command_dict:
                connection_state['command_id'] = command_dict['id']

            # Route based on command type
            command = command_dict.get('command')
            args = command_dict.get('args', {})

            if command == 'table_set':
                self._handle_table_set(args, client_addr, connection_state)
            elif command == 'copyvar':
                self._handle_copyvar(args, client_addr, connection_state)
            elif command == 'open_file':
                self._handle_open_file(args, client_addr, connection_state)
            elif command == 'add_trace':
                self._handle_add_trace(args, client_addr, connection_state)
            elif command == 'remove_trace':
                self._handle_remove_trace(args, client_addr, connection_state)
            elif command == 'get_data_point':
                self._handle_get_data_point(args, client_addr, connection_state)
            elif command == 'close_window':
                self._handle_close_window(args, client_addr, connection_state)
            elif command == 'list_windows':
                self._handle_list_windows(args, client_addr, connection_state)
            elif command == 'ping':
                self._handle_ping(args, client_addr, connection_state)
            elif command == 'data_point_update':
                self._handle_data_point_update(args, client_addr, connection_state)
            else:
                error_msg = f"Unknown command: {command}"
                logger.warning(f"{error_msg} from {client_addr}")
                self.invalid_command_received.emit(command_dict, error_msg)

        except Exception as e:
            error_msg = f"Error processing command: {e}"
            logger.error(f"{error_msg} for command: {command_dict}")
            self.invalid_command_received.emit(command_dict, error_msg)

    def _handle_table_set(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle table_set command."""
        raw_file = args.get('raw_file')
        if not raw_file:
            error_msg = "Missing raw_file parameter in table_set command"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'table_set', 'args': args},
                error_msg
            )
            return

        logger.info(f"table_set command from {client_addr}: {raw_file}")
        logger.debug(f"table_set args: {args}, connection_state: {connection_state}")
        self.table_set_received.emit(raw_file, client_addr, connection_state)

    def _handle_copyvar(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle copyvar command."""
        var_name = args.get('var_name')
        color = args.get('color', '#ff0000')

        if not var_name:
            error_msg = "Missing var_name parameter in copyvar command"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'copyvar', 'args': args},
                error_msg
            )
            return

        # Validate color format
        if not self._is_valid_color(color):
            logger.warning(f"Invalid color format in copyvar command from {client_addr}: {color}")
            color = '#ff0000'  # Default to red

        logger.info(f"copyvar command from {client_addr}: {var_name} color {color}")
        logger.debug(f"copyvar args: {args}, connection_state: {connection_state}")
        self.copyvar_received.emit(var_name, color, client_addr, connection_state)

    def _handle_open_file(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle open_file JSON command."""
        raw_file = args.get('raw_file')
        if not raw_file:
            error_msg = "Missing raw_file parameter in open_file command"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'open_file', 'args': args},
                error_msg
            )
            return

        logger.info(f"open_file command from {client_addr}: {raw_file}")
        self.open_file_received.emit(raw_file, client_addr, connection_state)

    def _handle_add_trace(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle add_trace JSON command."""
        var_name = args.get('var_name')
        axis = args.get('axis', 'auto')  # auto, Y1, or Y2
        color = args.get('color', '#ff0000')

        if not var_name:
            error_msg = "Missing var_name parameter in add_trace command"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'add_trace', 'args': args},
                error_msg
            )
            return

        # Validate axis
        if axis not in ('auto', 'Y1', 'Y2'):
            logger.warning(f"Invalid axis in add_trace command from {client_addr}: {axis}")
            axis = 'auto'

        # Validate color
        if not self._is_valid_color(color):
            logger.warning(f"Invalid color format in add_trace command from {client_addr}: {color}")
            color = '#ff0000'

        logger.info(f"add_trace command from {client_addr}: {var_name} axis {axis} color {color}")
        self.add_trace_received.emit(var_name, axis, color, client_addr, connection_state)

    def _handle_remove_trace(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle remove_trace JSON command."""
        var_name = args.get('var_name')
        if not var_name:
            error_msg = "Missing var_name parameter in remove_trace command"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'remove_trace', 'args': args},
                error_msg
            )
            return

        logger.info(f"remove_trace command from {client_addr}: {var_name}")
        self.remove_trace_received.emit(var_name, client_addr, connection_state)

    def _handle_get_data_point(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle get_data_point JSON command."""
        x_value = args.get('x')
        if x_value is None:
            error_msg = "Missing x parameter in get_data_point command"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'get_data_point', 'args': args},
                error_msg
            )
            return

        try:
            x_value = float(x_value)
        except (ValueError, TypeError):
            error_msg = f"Invalid x value in get_data_point command: {args.get('x')}"
            logger.warning(f"{error_msg} from {client_addr}")
            self.invalid_command_received.emit(
                {'command': 'get_data_point', 'args': args},
                error_msg
            )
            return

        logger.info(f"get_data_point command from {client_addr}: x={x_value}")
        self.get_data_point_received.emit(x_value, client_addr, connection_state)

    def _handle_close_window(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle close_window JSON command."""
        window_id = args.get('window_id', '')
        logger.info(f"close_window command from {client_addr}: window_id={window_id}")
        self.close_window_received.emit(window_id, client_addr, connection_state)

    def _handle_list_windows(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle list_windows JSON command."""
        logger.info(f"list_windows command from {client_addr}")
        self.list_windows_received.emit(client_addr, connection_state)

    def _handle_ping(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle ping JSON command."""
        logger.info(f"ping command from {client_addr}")
        self.ping_received.emit(client_addr, connection_state)

    def _handle_data_point_update(self, args: dict, client_addr: str, connection_state: dict) -> None:
        """Handle data_point_update JSON command (sent from pqwave to xschem).

        This command is sent by pqwave to xschem for back-annotation. When received
        (e.g., during testing via netcat), we log it and send a success response.
        """
        logger.debug(f"data_point_update command from {client_addr}: {args}")
        # Send success response for testing purposes
        if self.xschem_server:
            response = {
                'status': 'success',
                'data': {'message': 'data_point_update received'},
                'id': connection_state.get('command_id')
            }
            self.xschem_server.send_response(client_addr, response)

    @staticmethod
    def _is_valid_color(color: str) -> bool:
        """
        Validate hexadecimal color format.

        Args:
            color: Color string (e.g., '#ff0000', '#f00', '#ff0000ff')

        Returns:
            True if valid, False otherwise
        """
        if not color.startswith('#'):
            return False

        hex_part = color[1:]
        length = len(hex_part)
        if length not in (3, 4, 6, 8):
            return False

        try:
            int(hex_part, 16)
            return True
        except ValueError:
            return False