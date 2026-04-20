#!/usr/bin/env python3
"""
Unit tests for xschem server communication (Phase 1).
"""
import sys
import socket
import threading
import time
import logging
import pytest
from PyQt6.QtCore import QCoreApplication, QTimer

from pqwave.communication import XschemServer, CommandHandler

# Configure logging for tests
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@pytest.fixture
def qapp():
    """Provide QCoreApplication instance."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def test_server_start_stop():
    """Test that server can start and stop cleanly."""
    server = XschemServer(port=2023)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    assert server.start(), "Server failed to start"
    time.sleep(0.5)
    server.stop()
    time.sleep(0.5)
    # No assertion needed if no exception


def test_command_handler_table_set(qapp):
    """Test command_handler processes table_set command."""
    handler = CommandHandler()

    # Capture signal using a list
    received = []
    def on_table_set(raw_file, client_addr, connection_state):
        received.append(('table_set', raw_file, client_addr))
    handler.table_set_received.connect(on_table_set)

    # Simulate command from server
    command_dict = {
        'command': 'table_set',
        'args': {'raw_file': '/path/to/test.raw'},
        '_client_addr': '127.0.0.1:12345',
        '_connection_state': {}
    }

    # Process command
    handler.handle_command(command_dict)

    # Process Qt events
    QCoreApplication.processEvents()

    assert len(received) == 1
    assert received[0][1] == '/path/to/test.raw'
    assert received[0][2] == '127.0.0.1:12345'


def test_command_handler_copyvar(qapp):
    """Test command_handler processes copyvar command."""
    handler = CommandHandler()

    received = []
    def on_copyvar(var_name, color, client_addr, connection_state):
        received.append(('copyvar', var_name, color, client_addr))
    handler.copyvar_received.connect(on_copyvar)

    command_dict = {
        'command': 'copyvar',
        'args': {'var_name': 'v(out)', 'color': '#ff0000'},
        '_client_addr': '127.0.0.1:12346',
        '_connection_state': {}
    }

    handler.handle_command(command_dict)
    QCoreApplication.processEvents()

    assert len(received) == 1
    assert received[0][1] == 'v(out)'
    assert received[0][2] == '#ff0000'


def test_command_handler_json_open_file(qapp):
    """Test command_handler processes JSON open_file command."""
    handler = CommandHandler()

    received = []
    def on_open_file(raw_file, client_addr, connection_state):
        received.append(('open_file', raw_file, client_addr))
    handler.open_file_received.connect(on_open_file)

    command_dict = {
        'command': 'open_file',
        'args': {'raw_file': '/path/to/json.raw'},
        '_client_addr': '127.0.0.1:12347',
        '_connection_state': {}
    }

    handler.handle_command(command_dict)
    QCoreApplication.processEvents()

    assert len(received) == 1
    assert received[0][1] == '/path/to/json.raw'


def test_command_handler_invalid_command(qapp):
    """Test command_handler emits invalid_command signal for unknown command."""
    handler = CommandHandler()

    received = []
    def on_invalid(command_dict, error_message):
        received.append((command_dict, error_message))
    handler.invalid_command_received.connect(on_invalid)

    command_dict = {
        'command': 'unknown_command',
        'args': {},
        '_client_addr': '127.0.0.1:12348',
        '_connection_state': {}
    }

    handler.handle_command(command_dict)
    QCoreApplication.processEvents()

    assert len(received) == 1
    assert 'unknown_command' in received[0][1]


def test_server_integration_table_set(qapp):
    """Integration test: server receives gaw-style table_set command."""
    server = XschemServer(port=2024)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    received = []
    def on_table_set(raw_file, client_addr, connection_state):
        received.append(('table_set', raw_file, client_addr))
    handler.table_set_received.connect(on_table_set)

    assert server.start()
    time.sleep(0.5)

    # Send command via socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(('localhost', 2024))
    sock.sendall(b'table_set /path/to/integration.raw\n')
    sock.close()

    # Wait for signal with timeout
    start_time = time.time()
    while len(received) == 0 and time.time() - start_time < 3.0:
        QCoreApplication.processEvents()
        time.sleep(0.1)

    server.stop()
    time.sleep(0.5)

    assert len(received) == 1
    assert received[0][1] == '/path/to/integration.raw'


def test_server_integration_copyvar(qapp):
    """Integration test: server receives gaw-style copyvar command."""
    server = XschemServer(port=2025)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    received = []
    def on_copyvar(var_name, color, client_addr, connection_state):
        received.append(('copyvar', var_name, color, client_addr))
    handler.copyvar_received.connect(on_copyvar)

    assert server.start()
    time.sleep(0.5)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(('localhost', 2025))
    sock.sendall(b'copyvar v(out) sel #00ff00\n')
    sock.close()

    start_time = time.time()
    while len(received) == 0 and time.time() - start_time < 3.0:
        QCoreApplication.processEvents()
        time.sleep(0.1)

    server.stop()
    time.sleep(0.5)

    assert len(received) == 1
    assert received[0][1] == 'v(out)'
    assert received[0][2] == '#00ff00'


if __name__ == "__main__":
    # Simple test runner for manual execution
    pytest.main([__file__, "-v"])