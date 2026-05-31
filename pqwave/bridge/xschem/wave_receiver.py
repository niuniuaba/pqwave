#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GAW-compatible wave receiver for pqwave integration.

This module provides a TCP socket server (WaveReceiver) that listens for commands
from EDA tools and forwards them to the main application via Qt signals, plus a
command handler (WaveCommandHandler) that validates and dispatches commands.

The server supports both gaw-style commands (table_set, copyvar) and extended
JSON commands.
"""

import socket
import threading
import json
import logging
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class WaveReceiver(QObject):
    """
    TCP server for EDA tool integration via the GAW-compatible wave protocol.

    Listens on a configurable port (default 2026) for commands from EDA tools.
    Commands are parsed and emitted as Qt signals for processing in the main thread.

    Signals:
        command_received: Emitted when a valid command is received
        connection_opened: Emitted when a new client connects
        connection_closed: Emitted when a client disconnects
        server_started: Emitted when server starts successfully
        server_stopped: Emitted when server stops
    """

    # Qt signals
    command_received = pyqtSignal(dict)  # command dict
    connection_opened = pyqtSignal(str)  # client address
    connection_closed = pyqtSignal(str)  # client address
    server_started = pyqtSignal(int)     # port number
    server_stopped = pyqtSignal()

    def __init__(self, port: int = 2026):
        """
        Initialize WaveReceiver.

        Args:
            port: TCP port to listen on (default 2026)
        """
        super().__init__()
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self._lock = threading.Lock()
        self.clients: Dict[Tuple[str, int], socket.socket] = {}
        self.client_threads: Dict[Tuple[str, int], threading.Thread] = {}

        # Per-connection state: map client address to current raw file
        self.connection_state: Dict[Tuple[str, int], Dict[str, Any]] = {}

        logger.debug(f"WaveReceiver initialized (port: {port})")

    def start(self) -> bool:
        """
        Start the TCP server in a background thread.

        Returns:
            True if server started successfully, False otherwise
        """
        if self.running:
            logger.warning("Server already running")
            return False

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('localhost', self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Non-blocking with timeout

            self.running = True
            self.server_thread = threading.Thread(
                target=self._server_loop,
                daemon=True,
                name=f"WaveReceiver-{self.port}"
            )
            self.server_thread.start()

            logger.info(f"Wave receiver started on port {self.port}")
            self.server_started.emit(self.port)
            return True

        except socket.error as e:
            logger.warning(f"Wave receiver not available on port {self.port}: {e}")
            self.server_socket = None
            return False

    def stop(self) -> None:
        """Stop the TCP server and close all connections."""
        if not self.running:
            return

        self.running = False

        # Close all client connections (snapshot under lock)
        with self._lock:
            client_snapshot = list(self.clients.items())
        for client_addr, client_sock in client_snapshot:
            try:
                client_sock.close()
                self.connection_closed.emit(f"{client_addr[0]}:{client_addr[1]}")
            except socket.error:
                pass

        with self._lock:
            self.clients.clear()
            self.client_threads.clear()
            self.connection_state.clear()

        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except socket.error:
                pass
            self.server_socket = None

        # Wait for server thread to terminate
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)

        logger.info("Wave receiver stopped")
        self.server_stopped.emit()

    def _server_loop(self) -> None:
        """Main server loop accepting connections."""
        while self.running and self.server_socket:
            try:
                client_socket, client_addr = self.server_socket.accept()
                logger.debug(f"New connection from {client_addr[0]}:{client_addr[1]}")

                # Create client handler thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_addr),
                    daemon=True,
                    name=f"WaveClient-{client_addr[0]}:{client_addr[1]}"
                )

                # Store under lock for thread safety with stop()
                with self._lock:
                    self.clients[client_addr] = client_socket
                    self.connection_state[client_addr] = {
                        'current_raw_file': None,
                        'window_id': None
                    }
                    self.client_threads[client_addr] = client_thread
                client_thread.start()

                self.connection_opened.emit(f"{client_addr[0]}:{client_addr[1]}")

            except socket.timeout:
                # Timeout is expected, continue loop
                continue
            except socket.error as e:
                if self.running:
                    logger.error(f"Socket error in server loop: {e}")
                break

        logger.debug("Server loop exiting")

    def _handle_client(self, client_socket: socket.socket, client_addr: Tuple[str, int]) -> None:
        """
        Handle communication with a single client.

        Args:
            client_socket: Client socket
            client_addr: Client address (ip, port)
        """
        client_ip, client_port = client_addr
        client_str = f"{client_ip}:{client_port}"

        try:
            # Set socket timeout for reading
            client_socket.settimeout(1.0)

            # Receive and process commands
            while self.running:
                try:
                    # Read data from client
                    data = client_socket.recv(4096)
                    if not data:
                        # Client disconnected
                        logger.debug(f"Client {client_str} disconnected")
                        break

                    # Decode and process command(s)
                    text = data.decode('utf-8', errors='ignore').strip()
                    if not text:
                        continue

                    # Split by newlines (multiple commands possible)
                    lines = text.split('\n')
                    for raw_line in lines:
                        line = raw_line.strip()
                        if line:
                            # Echo back the line to satisfy handshake (only for non-JSON commands)
                            if not line.startswith('json '):
                                self._send_line(client_socket, line)
                            self._process_command(line, client_addr)

                except socket.timeout:
                    # Timeout is expected, continue loop
                    continue
                except socket.error as e:
                    logger.error(f"Socket error with client {client_str}: {e}")
                    break

        except Exception as e:
            logger.error(f"Unexpected error handling client {client_str}: {e}")
        finally:
            # Cleanup
            try:
                client_socket.close()
            except socket.error:
                pass

            # Remove client from tracking (under lock for thread safety)
            with self._lock:
                if client_addr in self.clients:
                    del self.clients[client_addr]
                if client_addr in self.client_threads:
                    del self.client_threads[client_addr]
                if client_addr in self.connection_state:
                    del self.connection_state[client_addr]

            self.connection_closed.emit(client_str)
            logger.debug(f"Client handler for {client_str} exiting")

    def _process_command(self, command_text: str, client_addr: Tuple[str, int]) -> None:
        """
        Parse and process a single command.

        Args:
            command_text: Raw command text
            client_addr: Client address for state tracking
        """
        # Get connection state
        state = self.connection_state.get(client_addr, {})

        # Check if command is JSON (starts with 'json ')
        if command_text.startswith('json '):
            json_text = command_text[5:].strip()
            try:
                command_dict = json.loads(json_text)
                if isinstance(command_dict, dict):
                    # Add client address to command for routing
                    command_dict['_client_addr'] = f"{client_addr[0]}:{client_addr[1]}"
                    command_dict['_connection_state'] = state
                    logger.debug(f"JSON command from {client_addr}: {command_dict}")
                    self.command_received.emit(command_dict)
                else:
                    logger.warning(f"Invalid JSON command format from {client_addr}: {json_text}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON command from {client_addr}: {e}")
            return

        # Check for gaw-style commands
        if command_text.startswith('table_set '):
            # Format: table_set filename.raw
            logger.debug(f"Processing table_set command: {command_text}")
            parts = command_text.split(' ', 1)
            logger.debug(f"Table_set parts: {parts}")
            if len(parts) == 2:
                raw_file = parts[1].strip()
                state['current_raw_file'] = raw_file
                logger.info(f"Table set for {client_addr}: {raw_file}")

                # Emit as command
                command_dict = {
                    'command': 'table_set',
                    'args': {'raw_file': raw_file},
                    '_client_addr': f"{client_addr[0]}:{client_addr[1]}",
                    '_connection_state': state
                }
                self.command_received.emit(command_dict)
            else:
                logger.warning(f"Invalid table_set command from {client_addr}: {command_text}")
            return

        if command_text.startswith('copyvar '):
            # Format: copyvar v(node) sel #color
            # Example: copyvar v(out) sel #ff0000
            logger.debug(f"Processing copyvar command: {command_text}")
            parts = command_text.split(' ', 3)
            logger.debug(f"Copyvar parts: {parts}")
            if len(parts) >= 4 and parts[2] == 'sel':
                var_name = parts[1].strip()
                color = parts[3].strip()

                # Validate color format
                if not color.startswith('#') or len(color) not in [4, 5, 7, 9]:
                    logger.warning(f"Invalid color format in copyvar command from {client_addr}: {color}")
                    color = '#ff0000'  # Default to red

                logger.info(f"Copyvar command from {client_addr}: {var_name} color {color}")

                # Emit as command
                command_dict = {
                    'command': 'copyvar',
                    'args': {
                        'var_name': var_name,
                        'color': color,
                        'raw_file': state.get('current_raw_file')
                    },
                    '_client_addr': f"{client_addr[0]}:{client_addr[1]}",
                    '_connection_state': state
                }
                self.command_received.emit(command_dict)
            else:
                logger.warning(f"Invalid copyvar command from {client_addr}: {command_text}")
            return

        # Unknown command
        logger.warning(f"Unknown command from {client_addr}: {command_text}")

    def _send_line(self, client_socket: socket.socket, line: str) -> None:
        """Send a line back to the client (echo)."""
        try:
            client_socket.sendall((line + '\n').encode('utf-8'))
        except socket.error as e:
            logger.warning(f"Failed to send echo line to client: {e}")
            raise  # Re-raise to let outer handler break the connection

    def send_response(self, client_addr_str: str, response: dict) -> bool:
        """
        Send a JSON response to a client.

        Args:
            client_addr_str: Client address string "ip:port"
            response: Response dictionary

        Returns:
            True if response sent successfully, False otherwise
        """
        # Parse client address string
        try:
            ip_str, port_str = client_addr_str.split(':')
            client_addr = (ip_str, int(port_str))
        except (ValueError, TypeError):
            logger.error(f"Invalid client address format: {client_addr_str}")
            return False

        # Find client socket (under lock for thread safety)
        with self._lock:
            client_socket = self.clients.get(client_addr)
        if not client_socket:
            logger.warning(f"Client not found: {client_addr_str}")
            return False

        # Send JSON response
        try:
            json_str = json.dumps(response)
            client_socket.sendall((json_str + '\n').encode('utf-8'))
            return True
        except (socket.error, TypeError) as e:
            logger.error(f"Failed to send response to {client_addr_str}: {e}")
            return False


class WaveCommandHandler(QObject):
    """
    Handles wave commands and emits specific Qt signals.

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
        """Initialize WaveCommandHandler."""
        super().__init__()
        self.wave_receiver = None
        logger.debug("WaveCommandHandler initialized")

    def set_receiver(self, wave_receiver):
        """Set reference to WaveReceiver for sending responses."""
        self.wave_receiver = wave_receiver

    def send_response(self, client_addr: str, response: dict) -> bool:
        """Send JSON response to client via wave receiver."""
        if self.wave_receiver is None:
            logger.error("Cannot send response: wave receiver not set")
            return False
        return self.wave_receiver.send_response(client_addr, response)

    def handle_command(self, command_dict: dict) -> None:
        """
        Process a command dictionary and emit appropriate signals.

        Args:
            command_dict: Command dictionary from WaveReceiver
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
        """Handle data_point_update JSON command (sent from pqwave to EDA tool).

        This command is sent by pqwave for back-annotation. When received
        (e.g., during testing via netcat), we log it and send a success response.
        """
        logger.debug(f"data_point_update command from {client_addr}: {args}")
        # Send success response for testing purposes
        if self.wave_receiver:
            response = {
                'status': 'success',
                'data': {'message': 'data_point_update received'},
                'id': connection_state.get('command_id')
            }
            self.wave_receiver.send_response(client_addr, response)

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
