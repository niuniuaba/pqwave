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
from pqwave.models.raw_converter import extract_traces_to_raw, write_raw_file, FORMAT_CONFIG
from pqwave.models.rawfile import RawFile
from pqwave.models.expression import ExprEvaluator
from pqwave.models.trace import Trace
import numpy as np


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


def _run_extract() -> int:
    """Handle --extract CLI mode: extract traces from a raw file.

    Usage: pqwave --extract <inputfile> <expr1[,expr2[,...]]> (-ltspice|-ngspice|-qspice) <outputfile>

    Operates without QApplication — pure models-layer operation.
    """
    args = sys.argv[sys.argv.index('--extract') + 1:]
    if len(args) < 3:
        print("Usage: pqwave --extract <inputfile> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice) <outputfile>", file=sys.stderr)
        return 1

    input_file = args[0]
    expr_str = args[1]

    # Parse format flag + output file from remaining args
    target_format = None
    output_file = None

    i = 2
    while i < len(args):
        a = args[i]
        if a in ('-ltspice', '-ngspice', '-qspice'):
            target_format = a.lstrip('-')
            if i + 1 < len(args):
                output_file = args[i + 1]
            break
        i += 1

    if not target_format or not output_file:
        print("Usage: pqwave --extract <inputfile> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice) <outputfile>", file=sys.stderr)
        return 1

    # Load raw file
    try:
        raw_file = RawFile(input_file)
    except Exception as e:
        print(f"Error loading {input_file}: {e}", file=sys.stderr)
        return 1

    if not raw_file.datasets:
        print(f"Error: No datasets found in {input_file}", file=sys.stderr)
        return 1

    dataset = raw_file.datasets[0]

    # Detect AC analysis
    plotname = dataset.get('plotname', '').lower()
    flags = dataset.get('flags', '').lower()
    is_ac = 'ac' in plotname or 'complex' in flags

    # Get first variable name as default X for trace metadata
    variables = dataset.get('variables', [])
    if not variables:
        print(f"Error: No variables found in {input_file}", file=sys.stderr)
        return 1

    first_var_name = variables[0]['name']

    # Split comma-separated expressions
    expressions = [e.strip() for e in expr_str.split(',') if e.strip()]
    if not expressions:
        print("Error: No expressions specified", file=sys.stderr)
        return 1

    # Evaluate each expression and build Trace objects
    traces = []
    evaluator = ExprEvaluator(raw_file, dataset_idx=0)

    for expr in expressions:
        try:
            y_data = evaluator.evaluate(expr)
        except Exception as e:
            print(f"Error evaluating expression '{expr}': {e}", file=sys.stderr)
            return 1

        # Get X data from the first variable
        try:
            x_data = evaluator.evaluate(first_var_name)
        except Exception:
            # Fallback: read first data column directly
            data_matrix = dataset.get('data')
            if data_matrix is not None and data_matrix.size > 0:
                x_data = data_matrix[:, 0].copy()
            else:
                print(f"Error: Cannot read X axis data from {input_file}", file=sys.stderr)
                return 1

        # Trim to common length
        n = min(len(x_data), len(y_data))
        trace = Trace(
            name=expr,
            expression=expr,
            x_data=x_data[:n].copy(),
            y_data=y_data[:n].copy(),
            dataset_idx=0,
            metadata={'x_var_name': first_var_name},
        )
        traces.append(trace)

    # Extract to raw file
    try:
        extract_traces_to_raw(output_file, traces, raw_file, target_format=target_format, output_is_ac=is_ac)
    except Exception as e:
        print(f"Error writing {output_file}: {e}", file=sys.stderr)
        return 1

    print(f"Extracted {len(traces)} traces to {output_file} ({target_format})")
    return 0


def _run_convert() -> int:
    """Handle --convert CLI mode: convert raw file between formats.

    Usage: pqwave --convert <inputfile> (-ltspice|-ngspice|-qspice) <outputfile>

    Operates without QApplication — pure models-layer operation.
    """
    args = sys.argv[sys.argv.index('--convert') + 1:]
    if len(args) < 2:
        print(
            "Usage: pqwave --convert <inputfile> (-ltspice|-ngspice|-qspice) <outputfile>",
            file=sys.stderr,
        )
        return 1

    input_file = args[0]

    # Parse format flag + output file from remaining args
    target_format = None
    output_file = None

    i = 1
    while i < len(args):
        a = args[i]
        if a in ('-ltspice', '-ngspice', '-qspice'):
            target_format = a.lstrip('-')
            if i + 1 < len(args):
                output_file = args[i + 1]
            break
        i += 1

    if not target_format or not output_file:
        print(
            "Usage: pqwave --convert <inputfile> (-ltspice|-ngspice|-qspice) <outputfile>",
            file=sys.stderr,
        )
        return 1

    # Load raw file
    try:
        raw_file = RawFile(input_file)
    except Exception as e:
        print(f"Error loading {input_file}: {e}", file=sys.stderr)
        return 1

    if not raw_file.datasets:
        print(f"Error: No datasets found in {input_file}", file=sys.stderr)
        return 1

    dataset = raw_file.datasets[0]
    title = dataset.get('title', 'pqwave conversion')
    date = dataset.get('date', '')
    plotname = dataset.get('plotname', '')
    flags = dataset.get('flags', '')
    variables = dataset.get('variables', [])
    data = dataset.get('data')
    is_ac_or_complex = dataset.get('_is_ac_or_complex', False)

    if data is None or data.size == 0:
        print(f"Error: No data found in {input_file}", file=sys.stderr)
        return 1

    try:
        write_raw_file(
            output_path=output_file,
            title=title,
            date=date,
            plotname=plotname,
            flags=flags,
            variables=variables,
            data=data,
            target_format=target_format,
            is_ac_or_complex=is_ac_or_complex,
        )
    except Exception as e:
        print(f"Error writing {output_file}: {e}", file=sys.stderr)
        return 1

    print(f"Converted {input_file} to {output_file} ({target_format})")
    return 0


def main():
    """Main entry point for pqwave."""
    # Handle --extract before argparse (uses non-standard flags like -ltspice)
    if '--extract' in sys.argv:
        return _run_extract()

    # Handle --convert before argparse (uses non-standard flags like -ltspice)
    if '--convert' in sys.argv:
        return _run_convert()

    parser = argparse.ArgumentParser(
        description="pqwave - SPICE Waveform Viewer",
        usage=(
            "pqwave [-h] [options] [raw_file]\n"
            "       or: pqwave --extract <input> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice) <output>\n"
            "       or: pqwave --convert <input> (-ltspice|-ngspice|-qspice) <output>"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Xschem integration arguments
    parser.add_argument(
        "--xschem-port",
        type=int,
        default=2026,
        help="TCP port for xschem integration server (default: 2026). Set to 0 to disable."
    )
    parser.add_argument(
        "--xschem-ba-port",
        type=int,
        default=2021,
        help="TCP port for xschem back-annotation (xschem_listen_port, default: 2021)."
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
        "--extract",
        action="store_true",
        help="Extract traces: pqwave --extract <input> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice) <output>"
    )
    parser.add_argument(
        "--convert",
        action="store_true",
        help="Convert raw format: pqwave --convert <input> (-ltspice|-ngspice|-qspice) <output>"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="pqwave 0.2.5"
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
        window = MainWindow(initial_file=args.raw_file, xschem_ba_port=args.xschem_ba_port)
    else:
        window = MainWindow(xschem_ba_port=args.xschem_ba_port)

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