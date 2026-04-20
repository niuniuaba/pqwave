#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Xschem TCP server for pqwave integration.

This module provides a TCP socket server that listens for commands from xschem
and forwards them to the main application via Qt signals. The server supports
both gaw-style commands (table_set, copyvar) and extended JSON commands.
"""

import socket
import threading
import json
import logging
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class XschemServer(QObject):
    """
    TCP server for xschem integration.

    Listens on a configurable port (default 2022) for commands from xschem.
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

    def __init__(self, port: int = 2022):
        """
        Initialize XschemServer.

        Args:
            port: TCP port to listen on (default 2022)
        """
        super().__init__()
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self.clients: Dict[Tuple[str, int], socket.socket] = {}
        self.client_threads: Dict[Tuple[str, int], threading.Thread] = {}

        # Per-connection state: map client address to current raw file
        self.connection_state: Dict[Tuple[str, int], Dict[str, Any]] = {}

        logger.debug(f"XschemServer initialized (port: {port})")

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
                name=f"XschemServer-{self.port}"
            )
            self.server_thread.start()

            logger.info(f"Xschem TCP server started on port {self.port}")
            self.server_started.emit(self.port)
            return True

        except socket.error as e:
            logger.error(f"Failed to start Xschem server on port {self.port}: {e}")
            self.server_socket = None
            return False

    def stop(self) -> None:
        """Stop the TCP server and close all connections."""
        if not self.running:
            return

        self.running = False

        # Close all client connections
        for client_addr, client_sock in list(self.clients.items()):
            try:
                client_sock.close()
                self.connection_closed.emit(f"{client_addr[0]}:{client_addr[1]}")
            except socket.error:
                pass

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

        logger.info("Xschem TCP server stopped")
        self.server_stopped.emit()

    def _server_loop(self) -> None:
        """Main server loop accepting connections."""
        while self.running and self.server_socket:
            try:
                client_socket, client_addr = self.server_socket.accept()
                logger.debug(f"New connection from {client_addr[0]}:{client_addr[1]}")

                # Store client socket
                self.clients[client_addr] = client_socket

                # Initialize connection state
                self.connection_state[client_addr] = {
                    'current_raw_file': None,
                    'window_id': None
                }

                # Start client handler thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_addr),
                    daemon=True,
                    name=f"XschemClient-{client_addr[0]}:{client_addr[1]}"
                )
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
                    for line in lines:
                        line = line.strip()
                        if line:
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

            # Remove client from tracking
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
            parts = command_text.split(' ', 1)
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
            parts = command_text.split(' ', 3)
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

        # Find client socket
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