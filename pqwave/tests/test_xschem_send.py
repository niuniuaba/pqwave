#!/usr/bin/env python3
"""
Test script to send xschem commands to pqwave server.
"""
import socket
import time
import sys
import os

def send_xschem_commands(raw_file=None):
    """Send table_set and copyvar commands in same connection."""
    try:
        # Connect to xschem server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(('localhost', 2026))
        print(f"Connected to xschem server on port 2026")

        # Send table_set command
        if raw_file is None:
            # Use bridge.raw in the same directory if it exists
            script_dir = os.path.dirname(os.path.abspath(__file__))
            raw_file = os.path.join(script_dir, "bridge.raw")
            if not os.path.exists(raw_file):
                print(f"Warning: {raw_file} not found, using placeholder")
                raw_file = "bridge.raw"

        table_set_cmd = f"table_set {raw_file}\n"
        sock.sendall(table_set_cmd.encode('utf-8'))
        print(f"Sent: {table_set_cmd.strip()}")

        # Wait a bit for processing
        time.sleep(0.5)

        # Send copyvar command for v(r2)
        copyvar_cmd = "copyvar v(r2) sel #ff0000\n"
        sock.sendall(copyvar_cmd.encode('utf-8'))
        print(f"Sent: {copyvar_cmd.strip()}")

        # Wait for processing
        time.sleep(0.5)

        # Try to receive any response (JSON commands would respond)
        sock.settimeout(0.5)
        try:
            response = sock.recv(4096).decode('utf-8', errors='ignore')
            if response:
                print(f"Response: {response.strip()}")
        except socket.timeout:
            # Expected for GAW commands
            pass

        sock.close()
        print("Connection closed")
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send xschem commands to pqwave server")
    parser.add_argument("--raw-file", "-f", help="Path to raw file (default: bridge.raw in script directory)")
    args = parser.parse_args()
    success = send_xschem_commands(raw_file=args.raw_file)
    sys.exit(0 if success else 1)