#!/usr/bin/env python3
"""
Integration test for xschem server communication (Phase 1).
"""
import sys
import socket
import threading
import time
import logging
from pqwave.communication import XschemServer, CommandHandler

# Configure logging for test
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_server_start_stop():
    """Test that server can start and stop cleanly."""
    server = XschemServer(port=2023)  # Use different port to avoid conflict
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    # Start server
    assert server.start(), "Server failed to start"
    time.sleep(0.5)  # Give server time to bind

    # Stop server
    server.stop()
    time.sleep(0.5)
    logger.info("✓ Server start/stop test passed")
    return True

def test_gaw_table_set_command():
    """Test reception of gaw-style table_set command."""
    server = XschemServer(port=2024)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    # Capture received command
    received_commands = []
    def on_table_set(raw_file, client_addr, connection_state):
        received_commands.append(('table_set', raw_file, client_addr))
    handler.table_set_received.connect(on_table_set)

    assert server.start(), "Server failed to start"
    time.sleep(0.5)

    # Send command via socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', 2024))
        sock.sendall(b'table_set /path/to/test.raw\n')
        sock.close()
    except Exception as e:
        logger.error(f"Socket error: {e}")
        server.stop()
        return False

    # Wait for command processing
    time.sleep(0.5)

    # Verify command received
    assert len(received_commands) == 1, f"Expected 1 command, got {len(received_commands)}"
    cmd_type, raw_file, client_addr = received_commands[0]
    assert cmd_type == 'table_set'
    assert raw_file == '/path/to/test.raw'
    logger.info(f"✓ table_set command test passed: {raw_file} from {client_addr}")

    server.stop()
    time.sleep(0.5)
    return True

def test_gaw_copyvar_command():
    """Test reception of gaw-style copyvar command."""
    server = XschemServer(port=2025)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    received_commands = []
    def on_copyvar(var_name, color, client_addr, connection_state):
        received_commands.append(('copyvar', var_name, color, client_addr))
    handler.copyvar_received.connect(on_copyvar)

    assert server.start(), "Server failed to start"
    time.sleep(0.5)

    # Send copyvar command
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', 2025))
        sock.sendall(b'copyvar v(out) sel #ff0000\n')
        sock.close()
    except Exception as e:
        logger.error(f"Socket error: {e}")
        server.stop()
        return False

    time.sleep(0.5)
    assert len(received_commands) == 1, f"Expected 1 command, got {len(received_commands)}"
    cmd_type, var_name, color, client_addr = received_commands[0]
    assert cmd_type == 'copyvar'
    assert var_name == 'v(out)'
    assert color == '#ff0000'
    logger.info(f"✓ copyvar command test passed: {var_name} color {color} from {client_addr}")

    server.stop()
    time.sleep(0.5)
    return True

def test_json_command():
    """Test reception of JSON command."""
    server = XschemServer(port=2026)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    received_commands = []
    def on_open_file(raw_file, client_addr, connection_state):
        received_commands.append(('open_file', raw_file, client_addr))
    handler.open_file_received.connect(on_open_file)

    assert server.start(), "Server failed to start"
    time.sleep(0.5)

    # Send JSON command
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', 2026))
        sock.sendall(b'json {"command": "open_file", "args": {"raw_file": "/path/to/json.raw"}}\n')
        sock.close()
    except Exception as e:
        logger.error(f"Socket error: {e}")
        server.stop()
        return False

    time.sleep(0.5)
    assert len(received_commands) == 1, f"Expected 1 command, got {len(received_commands)}"
    cmd_type, raw_file, client_addr = received_commands[0]
    assert cmd_type == 'open_file'
    assert raw_file == '/path/to/json.raw'
    logger.info(f"✓ JSON command test passed: {raw_file} from {client_addr}")

    server.stop()
    time.sleep(0.5)
    return True

def test_invalid_command():
    """Test handling of invalid command."""
    server = XschemServer(port=2027)
    handler = CommandHandler()
    server.command_received.connect(handler.handle_command)

    invalid_received = []
    def on_invalid(command_dict, error_message):
        invalid_received.append((command_dict, error_message))
    handler.invalid_command_received.connect(on_invalid)

    assert server.start(), "Server failed to start"
    time.sleep(0.5)

    # Send invalid command
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', 2027))
        sock.sendall(b'invalid_command\n')
        sock.close()
    except Exception as e:
        logger.error(f"Socket error: {e}")
        server.stop()
        return False

    time.sleep(0.5)
    # Invalid command should trigger signal
    assert len(invalid_received) == 1, f"Expected 1 invalid command, got {len(invalid_received)}"
    logger.info(f"✓ Invalid command test passed: {invalid_received[0][1]}")

    server.stop()
    time.sleep(0.5)
    return True

def main():
    """Run all tests."""
    tests = [
        test_server_start_stop,
        test_gaw_table_set_command,
        test_gaw_copyvar_command,
        test_json_command,
        test_invalid_command,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        logger.info(f"Running {test_func.__name__}...")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Test {test_func.__name__} raised exception: {e}")
            failed += 1

    logger.info(f"Tests completed: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())