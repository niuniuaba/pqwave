#!/usr/bin/env python3
"""
End-to-end test for xschem integration.
This script tests the xschem server functionality by starting pqwave in server mode,
sending commands, and verifying responses.
"""

import subprocess
import time
import socket
import sys
import os
import json

def send_json_command(port, command):
    """Send JSON command to xschem server and return response."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', port))
        sock.sendall((command + '\n').encode('utf-8'))
        sock.settimeout(5.0)
        response = sock.recv(4096).decode('utf-8', errors='ignore')
        sock.close()
        return response.strip()
    except Exception as e:
        return f"Error: {e}"

def send_gaw_command(port, command):
    """Send GAW-style command (table_set, copyvar) - no response expected."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', port))
        sock.sendall((command + '\n').encode('utf-8'))
        # Don't wait for response - server doesn't send one for GAW commands
        sock.close()
        return ""
    except Exception as e:
        return f"Error: {e}"

def test_xschem_server():
    """Test xschem server functionality."""
    print("Testing xschem integration...")

    # Start pqwave with xschem server on port 2023 (avoid conflict with default)
    port = 2023
    raw_file = os.path.join(os.path.dirname(__file__), 'bridge.raw')

    if not os.path.exists(raw_file):
        print(f"Raw file not found: {raw_file}")
        # Try another location (legacy)
        raw_file = os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'bridge.raw')
        if not os.path.exists(raw_file):
            print("Skipping e2e test (no raw file available)")
            return True

    # Start pqwave in background with xschem server
    print(f"Starting pqwave with xschem server on port {port}...")
    env = os.environ.copy()
    env['DISPLAY'] = ':99'
    proc = subprocess.Popen([
        sys.executable, '-m', 'pqwave.main',
        '--xschem-port', str(port),
        '--debug',
        '--log-file', 'xschem_test.log',
        raw_file
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    # Wait for server to start
    time.sleep(3)

    try:
        all_passed = True

        # Test 1: Send ping command (JSON)
        print("Test 1: Sending ping command...")
        response = send_json_command(port, 'json {"command": "ping", "id": "test1"}')
        print(f"Response: {response}")
        try:
            resp_json = json.loads(response)
            if resp_json.get('status') == 'success':
                print("✓ Ping successful")
            else:
                print(f"✗ Ping failed: {resp_json.get('error', 'Unknown error')}")
                all_passed = False
        except (json.JSONDecodeError, TypeError):
            print("✗ Ping failed: invalid JSON response")
            all_passed = False

        # Test 2: Send table_set command (GAW-style)
        print("\nTest 2: Sending table_set command...")
        response = send_gaw_command(port, f'table_set {raw_file}')
        # table_set doesn't expect response, but check for errors
        if response.startswith('Error:'):
            print(f"✗ Table set failed: {response}")
            all_passed = False
        else:
            print("✓ Table set command sent (no response expected)")

        # Test 3: Send copyvar command
        print("\nTest 3: Sending copyvar command...")
        response = send_gaw_command(port, 'copyvar v(r1) sel #ff0000')
        if response.startswith('Error:'):
            print(f"✗ Copyvar failed: {response}")
            all_passed = False
        else:
            print("✓ Copyvar command sent (no response expected)")

        # Test 4: Send add_trace JSON command
        print("\nTest 4: Sending add_trace JSON command...")
        response = send_json_command(port, 'json {"command": "add_trace", "args": {"var_name": "v(r1)", "axis": "Y2", "color": "#00ff00"}, "id": "test4"}')
        print(f"Response: {response}")
        try:
            resp_json = json.loads(response)
            if resp_json.get('status') == 'success':
                print("✓ Add trace successful")
            else:
                print(f"✗ Add trace failed: {resp_json.get('error', 'Unknown error')}")
                all_passed = False
        except (json.JSONDecodeError, TypeError):
            print("✗ Add trace failed: invalid JSON response")
            all_passed = False

        # Test 5: Send get_data_point command
        print("\nTest 5: Sending get_data_point command...")
        response = send_json_command(port, 'json {"command": "get_data_point", "args": {"x": 0.001}, "id": "test5"}')
        print(f"Response: {response}")
        try:
            resp_json = json.loads(response)
            if resp_json.get('status') == 'success':
                print("✓ Get data point successful")
            else:
                print(f"✗ Get data point failed: {resp_json.get('error', 'Unknown error')}")
                all_passed = False
        except (json.JSONDecodeError, TypeError):
            print("✗ Get data point failed: invalid JSON response")
            all_passed = False

        print("\nAll tests completed.")
        return all_passed

    finally:
        # Kill pqwave process
        print("\nStopping pqwave server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

if __name__ == '__main__':
    success = test_xschem_server()
    sys.exit(0 if success else 1)