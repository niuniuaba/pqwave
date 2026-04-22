#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main entry point for pqwave.

This module provides the main() function that serves as the entry point
for the pqwave application, both for command-line usage and for the
package entry point defined in pyproject.toml.
"""

import sys
import argparse
import socket
import json
from PyQt6.QtWidgets import QApplication

from pqwave.ui.main_window import MainWindow
from pqwave.logging_config import setup_logging
from pqwave.communication import XschemServer, CommandHandler
from pqwave.models.state import ApplicationState


def _send_command_to_server(port, command_text):
    """Send command to xschem server and print response."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', port))
        # Send command
        sock.sendall((command_text + '\n').encode('utf-8'))
        # Only wait for response on JSON commands (GAW-style commands don't respond)
        # JSON commands start with 'json ' or '{', GAW commands like 'table_set' don't
        stripped = command_text.strip()
        if stripped.startswith('json ') or stripped.startswith('{'):
            sock.settimeout(5.0)
            response = sock.recv(4096).decode('utf-8', errors='ignore')
            if response:
                print(response.strip())
        else:
            # For GAW-style commands, use short timeout and ignore if no response
            sock.settimeout(0.1)
            try:
                response = sock.recv(4096).decode('utf-8', errors='ignore')
                if response:
                    print(response.strip())
            except socket.timeout:
                # Expected for GAW commands that don't send responses
                pass
        sock.close()
        return True
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point for pqwave."""
    parser = argparse.ArgumentParser(
        description="pqwave - SPICE Waveform Viewer",
        epilog="Example: pqwave simulation.raw"
    )
    # Xschem integration arguments
    parser.add_argument(
        "--xschem-port",
        type=int,
        default=2026,
        help="TCP port for xschem integration server (default: 2026). Set to 0 to disable."
    )
    parser.add_argument(
        "--no-xschem-server",
        action="store_true",
        help="Disable xschem integration server"
    )
    parser.add_argument(
        "--xschem-send",
        metavar="COMMAND",
        help="Send command to existing xschem server and exit"
    )

    parser.add_argument(
        "raw_file",
        nargs="?",  # Optional positional argument
        help="SPICE raw file to open"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="pqwave 0.2.3"
    )

    # Testing and debugging arguments
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run test suites in ./tests directory"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging (most verbose)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable info-level logging (user feedback)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output except errors"
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        help="Write logs to specified file"
    )

    args = parser.parse_args()

    # Setup logging based on command-line arguments
    logger = setup_logging(
        debug=args.debug,
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file
    )

    # Handle xschem integration
    xschem_servers = []  # Track active servers for cleanup

    # Send command and exit if requested
    if args.xschem_send:
        _send_command_to_server(args.xschem_port, args.xschem_send)
        return 0

    # Create xschem server and command handler if enabled
    xschem_server = None
    command_handler = None
    if not args.no_xschem_server and args.xschem_port != 0:
        xschem_server = XschemServer(port=args.xschem_port)
        command_handler = CommandHandler()
        command_handler.set_server(xschem_server)
        # Store command handler in application state for window access
        ApplicationState().command_handler = command_handler
        # Connect signals for logging
        xschem_server.command_received.connect(command_handler.handle_command)
        # Log command handler signals for debugging
        command_handler.table_set_received.connect(
            lambda raw_file, client_addr, connection_state, logger=logger: logger.debug(f"table_set: {raw_file} from {client_addr}")
        )
        command_handler.copyvar_received.connect(
            lambda var_name, color, client_addr, connection_state, logger=logger: logger.debug(f"copyvar: {var_name} color {color} from {client_addr}")
        )
        command_handler.open_file_received.connect(
            lambda raw_file, client_addr, connection_state, logger=logger: logger.debug(f"open_file: {raw_file} from {client_addr}")
        )
        command_handler.add_trace_received.connect(
            lambda var_name, axis, color, client_addr, connection_state, logger=logger: logger.debug(f"add_trace: {var_name} axis {axis} from {client_addr}")
        )
        command_handler.invalid_command_received.connect(
            lambda command_dict, error_message, logger=logger: logger.warning(f"Invalid command: {error_message} - {command_dict}")
        )

    # Handle --test argument
    if args.test:
        logger.info("Running test suites...")
        try:
            from pqwave.test_runner import run_all_tests
            exit_code = run_all_tests()
            logger.info(f"Tests completed with exit code: {exit_code}")
            return exit_code
        except ImportError as e:
            logger.error(f"Failed to import test_runner: {e}")
            return 1
        except Exception as e:
            logger.error(f"Unexpected error running tests: {e}")
            return 1

    # Normal GUI startup
    app = QApplication(sys.argv)

    # Create window with optional initial file
    if args.raw_file:
        logger.info(f"Opening file from command line: {args.raw_file}")
        window = MainWindow(initial_file=args.raw_file)
    else:
        window = MainWindow()

    # Start xschem server after window is created (so signals are connected)
    if xschem_server is not None:
        if xschem_server.start():
            logger.info(f"Xschem server started on port {args.xschem_port}")
            xschem_servers.append(xschem_server)
        else:
            logger.warning(f"Failed to start xschem server on port {args.xschem_port}")
            # If port in use, assume another pqwave instance is running
            # Forward raw_file command if provided
            if args.raw_file:
                logger.info(f"Forwarding file to existing xschem server on port {args.xschem_port}")
                success = _send_command_to_server(args.xschem_port, f"table_set {args.raw_file}")
                if success:
                    return 0  # Exit after forwarding
                else:
                    logger.warning("Failed to forward command to existing server")
            # Server failed but we continue with GUI

    # Cleanup xschem servers on exit
    app.aboutToQuit.connect(lambda: [server.stop() for server in xschem_servers])

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())