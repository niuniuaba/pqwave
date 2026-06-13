#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main entry point for pqwave.

This module provides the main() function that serves as the entry point
for the pqwave application, both for command-line usage and for the
package entry point defined in pyproject.toml.
"""

import sys
import os
import argparse
import socket
import json
from PyQt6.QtWidgets import QApplication

from pqwave.ui.main_window import MainWindow
from pqwave.logging_config import setup_logging
from pqwave.bridge.xschem.wave_receiver import WaveReceiver, WaveCommandHandler
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

    Usage: pqwave --extract <inputfile> <expr1[,expr2[,...]]> (-ltspice|-ngspice|-qspice|-vcd) <outputfile>

    Operates without QApplication — pure models-layer operation.
    """
    args = sys.argv[sys.argv.index('--extract') + 1:]
    if len(args) < 3:
        print("Usage: pqwave --extract <inputfile> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice|-vcd) <outputfile>", file=sys.stderr)
        return 1

    input_file = args[0]
    expr_str = args[1]

    # Parse format flag + output file from remaining args
    target_format = None
    output_file = None

    i = 2
    while i < len(args):
        a = args[i]
        if a in ('-ltspice', '-ngspice', '-qspice', '-vcd'):
            target_format = a.lstrip('-')
            if i + 1 < len(args):
                output_file = args[i + 1]
            break
        i += 1

    if not target_format or not output_file:
        print("Usage: pqwave --extract <inputfile> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice|-vcd) <outputfile>", file=sys.stderr)
        return 1

    if input_file.lower().endswith('.vcd'):
        return _run_extract_vcd(input_file, expr_str, target_format, output_file)
    return _run_extract_raw(input_file, expr_str, target_format, output_file)


def _run_extract_raw(input_file: str, expr_str: str, target_format: str, output_file: str) -> int:
    """Extract traces from a SPICE raw file."""
    try:
        raw_file = RawFile(input_file)
    except Exception as e:
        print(f"Error loading {input_file}: {e}", file=sys.stderr)
        return 1

    if not raw_file.datasets:
        print(f"Error: No datasets found in {input_file}", file=sys.stderr)
        return 1

    dataset = raw_file.datasets[0]

    plotname = dataset.get('plotname', '').lower()
    flags = dataset.get('flags', '').lower()
    is_ac = 'ac' in plotname or 'complex' in flags

    variables = dataset.get('variables', [])
    if not variables:
        print(f"Error: No variables found in {input_file}", file=sys.stderr)
        return 1

    first_var_name = variables[0]['name']

    expressions = [e.strip() for e in expr_str.split(',') if e.strip()]
    if not expressions:
        print("Error: No expressions specified", file=sys.stderr)
        return 1

    traces = []
    evaluator = ExprEvaluator(raw_file, dataset_idx=0)

    for expr in expressions:
        try:
            y_data = evaluator.evaluate(expr)
        except Exception as e:
            print(f"Error evaluating expression '{expr}': {e}", file=sys.stderr)
            return 1

        try:
            x_data = evaluator.evaluate(first_var_name)
        except Exception:
            data_matrix = dataset.get('data')
            if data_matrix is not None and data_matrix.size > 0:
                x_data = data_matrix[:, 0].copy()
            else:
                print(f"Error: Cannot read X axis data from {input_file}", file=sys.stderr)
                return 1

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

    try:
        extract_traces_to_raw(output_file, traces, raw_file, target_format=target_format, output_is_ac=is_ac)
    except Exception as e:
        print(f"Error writing {output_file}: {e}", file=sys.stderr)
        return 1

    print(f"Extracted {len(traces)} traces to {output_file} ({target_format})")
    return 0


def _run_extract_vcd(input_file: str, expr_str: str, target_format: str, output_file: str) -> int:
    """Extract signals from a VCD file to raw or VCD format."""
    from pqwave.models.vcdfile import VcdFile
    from pqwave.digital.vcd_time_aligner import vcd_to_step_arrays

    try:
        vcd_file = VcdFile(input_file)
    except Exception as e:
        print(f"Error loading VCD {input_file}: {e}", file=sys.stderr)
        return 1

    signal_names = vcd_file.get_signal_names()
    if not signal_names:
        print(f"Error: No signals found in {input_file}", file=sys.stderr)
        return 1

    expressions = [e.strip() for e in expr_str.split(',') if e.strip()]
    if not expressions:
        print("Error: No expressions specified", file=sys.stderr)
        return 1

    # Resolve all signals and collect data
    vcd_max_time = vcd_file.get_max_time()
    traces = []
    orig_events = []
    valid_expressions = []
    for expr in expressions:
        sig = vcd_file.get_signal(expr)
        if sig is None:
            print(f"Error: Signal '{expr}' not found in {input_file}", file=sys.stderr)
            return 1
        vcd_t, vcd_v = sig.to_arrays(vcd_file.timescale)
        if len(vcd_t) < 1:
            print(f"Warning: Signal '{expr}' has no data, skipping", file=sys.stderr)
            continue
        step_t, step_v = vcd_to_step_arrays(vcd_t, vcd_v)
        # Extend the last value to the VCD file's global max time
        if vcd_max_time > vcd_t[-1]:
            step_t = np.append(step_t, vcd_max_time)
            step_v = np.append(step_v, vcd_v[-1])
            vcd_t_ext = np.append(vcd_t, vcd_max_time)
            vcd_v_ext = np.append(vcd_v, vcd_v[-1])
        else:
            vcd_t_ext, vcd_v_ext = vcd_t, vcd_v
        traces.append(Trace(
            name=expr,
            expression=expr,
            x_data=step_t,
            y_data=step_v,
            dataset_idx=0,
            metadata={
                'x_var_name': 'time',
                'vcd_times': vcd_t_ext,
                'vcd_values': vcd_v_ext,
            },
        ))
        orig_events.append((vcd_t_ext, vcd_v_ext))
        valid_expressions.append(expr)

    if not traces:
        print("Error: No valid signals to extract", file=sys.stderr)
        return 1

    if target_format == 'vcd':
        # VCD output uses original event data for compact representation
        from pqwave.models.raw_converter import write_vcd_file
        vcd_traces = []
        for expr, (t, v) in zip(valid_expressions, orig_events):
            vcd_traces.append(Trace(
                name=expr, expression=expr, x_data=t, y_data=v, dataset_idx=0,
            ))
        try:
            write_vcd_file(output_file, vcd_traces, vcd_file.timescale)
        except Exception as e:
            print(f"Error writing {output_file}: {e}", file=sys.stderr)
            return 1
    else:
        # Raw output: align all signals to a common uniform time grid
        from pqwave.digital.vcd_time_aligner import align_vcd_to_raw
        from pqwave.models.raw_converter import extract_traces_to_raw
        t_min = min(np.min(m[0]) for m in orig_events)
        t_max = max(np.max(m[0]) for m in orig_events)
        max_pts = max(len(m[0]) for m in orig_events)
        n_pts = min(max(1600, max_pts), 100000)
        uniform_t = np.linspace(t_min, t_max, n_pts, dtype=np.float64)

        raw_traces = []
        for expr, (t, v) in zip(valid_expressions, orig_events):
            aligned_v = align_vcd_to_raw(uniform_t, t, v)
            raw_traces.append(Trace(
                name=expr,
                expression=expr,
                x_data=uniform_t.copy(),
                y_data=aligned_v,
                dataset_idx=0,
                metadata={'x_var_name': 'time'},
            ))

        try:
            extract_traces_to_raw(output_file, raw_traces, raw_file=None, target_format=target_format, x_var_name='time')
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


def _run_exec() -> int:
    """Handle --exec <code>: execute Python code headless and print JSON result."""
    idx = sys.argv.index('--exec') + 1
    if idx >= len(sys.argv):
        print("Error: --exec requires a code argument", file=sys.stderr)
        return 1
    code = sys.argv[idx]
    from pqwave.session.api import SessionAPI
    result = SessionAPI.run_headless(code)
    print(result)
    return 0


def _run_help_commands() -> int:
    """Handle --help-commands: list all registered session API commands."""
    from pqwave.session.api import get_command_registry
    registry = get_command_registry()
    if not registry:
        print("No commands registered.")
        return 0
    for name, entry in sorted(registry.items()):
        print(f"  {entry['signature']}")
        print(f"    {entry['help']}\n")
    return 0


def _run_setup_llm() -> int:
    """Handle --setup-llm: open the LLM backend setup wizard."""
    from PyQt6.QtWidgets import QApplication
    from pqwave.llm.setup import show_setup_dialog

    app = QApplication(sys.argv)
    show_setup_dialog()
    return 0


def _run_qucs_bridge() -> int:
    """Handle --qucs-bridge: post-simulation hook for Qucs-S.

    Qucs-S invokes this as: pqwave <NgspiceParams> <netlist_file>
    where NgspiceParams = "--qucs-bridge" and CWD = S4Qworkdir.

    The netlist file is identified by its .cir extension (Qucs-S may
    insert extra flags like -b between --qucs-bridge and the netlist).
    """
    from pqwave.bridge.qucs_s.wrapper import QucsBridgeRunner

    args = sys.argv[sys.argv.index('--qucs-bridge') + 1:]
    # The netlist is always a .cir file — find it among the remaining args.
    netlist_candidates = [a for a in args if a.endswith('.cir')]
    if not netlist_candidates:
        print("Usage: pqwave --qucs-bridge <netlist_file>", file=sys.stderr)
        return 1

    netlist_name = netlist_candidates[-1]
    workdir = os.getcwd()

    runner = QucsBridgeRunner()
    return runner.run(workdir, netlist_name)


def _run_setup_qucs_integration() -> int:
    """Handle --setup-qucs-integration: configure Qucs-S to use pqwave."""
    import shutil as _shutil
    from pqwave.bridge.qucs_s.config import (
        get_config_path, is_configured_for_pqwave,
        apply_bridge_config, detect_ngspice, read_config,
    )

    print("=== pqwave Qucs-S Integration Setup ===\n")

    # Check for Qucs-S config
    config_path = get_config_path()
    try:
        cfg = read_config()
        print(f"Qucs-S config found: {config_path}")
    except Exception:
        print(f"Qucs-S config not found at {config_path}")
        print("Is Qucs-S installed?")
        return 1

    # Check if already configured
    if is_configured_for_pqwave():
        print("Qucs-S is already configured to use pqwave.")
        current_exe = cfg.get("General", "NgspiceExecutable", fallback="unknown")
        current_params = cfg.get("General", "NgspiceParams", fallback="")
        print(f"  NgspiceExecutable = {current_exe}")
        print(f"  NgspiceParams      = {current_params}")
        return 0

    # Find ngspice
    ngspice = detect_ngspice()
    if ngspice:
        print(f"Ngspice found: {ngspice}")
    else:
        print("WARNING: ngspice not found. The bridge will resolve it at runtime.")

    # Resolve pqwave path (executable only — subcommand goes in NgspiceParams)
    pqwave_exe = _shutil.which("pqwave")
    pqwave_params = "--qucs-bridge"
    if not pqwave_exe:
        # Fallback: python -m pqwave.main --qucs-bridge
        pqwave_exe = sys.executable
        pqwave_params = "-m pqwave.main --qucs-bridge"
    print(f"pqwave executable: {pqwave_exe}")
    print(f"pqwave params:     {pqwave_params}")

    # Show current vs proposed
    print("\nCurrent config:")
    print(f"  NgspiceExecutable = {cfg.get('General', 'NgspiceExecutable', fallback='(not set)')}")
    print(f"  NgspiceParams      = {cfg.get('General', 'NgspiceParams', fallback='(not set)')}")
    print("\nProposed config:")
    print(f"  NgspiceExecutable = {pqwave_exe}")
    print(f"  NgspiceParams      = {pqwave_params}")
    print("\nQucs-S will run: \"{0}\" {1} <netlist>".format(pqwave_exe, pqwave_params))

    # Confirm
    try:
        answer = input("\nApply these changes? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return 1
    if answer not in ('y', 'yes'):
        print("Aborted.")
        return 1

    # Apply
    try:
        backup = apply_bridge_config(
            pqwave_exe=pqwave_exe,
            pqwave_params=pqwave_params,
        )
        print(f"\n✓ Configuration applied.")
        print(f"  Backup saved to: {backup}")
        print(f"\nOpen Qucs-S and simulate any schematic — results will open in pqwave automatically.")
        return 0
    except Exception as e:
        print(f"\n✗ Failed to apply configuration: {e}")
        return 1


def main():
    """Main entry point for pqwave."""
    # Handle --qucs-bridge before argparse (post-simulation hook for Qucs-S)
    if '--qucs-bridge' in sys.argv:
        return _run_qucs_bridge()

    # Handle --setup-qucs-integration before argparse
    if '--setup-qucs-integration' in sys.argv:
        return _run_setup_qucs_integration()

    # Handle --extract before argparse (uses non-standard flags like -ltspice)
    if '--extract' in sys.argv:
        return _run_extract()

    # Handle --convert before argparse (uses non-standard flags like -ltspice)
    if '--convert' in sys.argv:
        return _run_convert()

    # Handle --exec before argparse (headless code execution)
    if '--exec' in sys.argv:
        return _run_exec()

    # Handle --help-commands before argparse (lists session API commands)
    if '--help-commands' in sys.argv:
        return _run_help_commands()

    # Handle --setup-llm before argparse (opens LLM setup wizard)
    if '--setup-llm' in sys.argv:
        return _run_setup_llm()

    parser = argparse.ArgumentParser(
        description="pqwave - SPICE Waveform Viewer",
        usage=(
            "pqwave [-h] [options] [files ...]\n"
            "       or: pqwave --exec <code>\n"
            "       or: pqwave --extract <input> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice|-vcd) <output>\n"
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
        "files",
        nargs="*",  # Zero or more positional arguments
        help="Files to open (.raw, .vcd, .json for project)"
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract traces: pqwave --extract <input> <expr1[,expr2,...]> (-ltspice|-ngspice|-qspice|-vcd) <output>"
    )
    parser.add_argument(
        "--convert",
        action="store_true",
        help="Convert raw format: pqwave --convert <input> (-ltspice|-ngspice|-qspice) <output>"
    )
    parser.add_argument(
        "--exec",
        action="store_true",
        help="Execute Python code headless: pqwave --exec '<code>'"
    )
    parser.add_argument(
        "--help-commands",
        action="store_true",
        help="List all registered session API commands"
    )
    parser.add_argument(
        "--setup-llm",
        action="store_true",
        help="Open the LLM backend setup wizard"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="pqwave 0.3.1"
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

    # Bridge auto-connect arguments (used by editor Wave menus)
    parser.add_argument(
        "--connect",
        choices=["xschem", "lepton", "qucs", "kicad"],
        default=None,
        help="Auto-connect to bridge on startup (used by editor Wave menu)"
    )
    parser.add_argument(
        "--sch-path",
        metavar="PATH",
        default=None,
        help="Schematic file path for auto-connect (used with --connect)"
    )

    args = parser.parse_args()

    # Setup logging based on command-line arguments
    logger = setup_logging(
        debug=args.debug,
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file
    )

    # Handle wave receiver integration
    wave_servers = []  # Track active servers for cleanup

    # Send command and exit if requested
    if args.xschem_send:
        _send_command_to_server(args.xschem_port, args.xschem_send)
        return 0

    # Create wave receiver and command handler if enabled
    wave_receiver = None
    # Validate no port conflicts
    _ports_used = {}
    for _name, _port in [
        ("xschem server (--xschem-port)", args.xschem_port),
        ("xschem back-annotation (--xschem-ba-port)", args.xschem_ba_port),
    ]:
        if _port == 0:
            continue
        if _port in _ports_used:
            print(
                f"ERROR: Port conflict: {_name} and {_ports_used[_port]} "
                f"both use port {_port}. Specify distinct ports and try again.",
                file=sys.stderr,
            )
            sys.exit(1)
        _ports_used[_port] = _name

    # Validate xschem cross-probe port against reserved ports
    reserved_for_cross_probe = {2026: "xschem wave receiver"}
    if args.xschem_ba_port in reserved_for_cross_probe:
        print(
            f"ERROR: xschem back-annotation port {args.xschem_ba_port} "
            f"conflicts with {reserved_for_cross_probe[args.xschem_ba_port]} "
            f"(port {args.xschem_ba_port}). Use --xschem-ba-port to change.",
            file=sys.stderr
        )
        sys.exit(1)

    wave_cmd_handler = None
    xschem_port_busy = False
    if not args.no_xschem_server and args.xschem_port != 0:
        # Check port availability before binding — if another session owns
        # the port, we'll ask the user before deciding to run standalone.
        port_available = False
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('localhost', args.xschem_port))
            probe.close()
            port_available = True
        except socket.error:
            xschem_port_busy = True
        if port_available:
            wave_receiver = WaveReceiver(port=args.xschem_port)
            wave_cmd_handler = WaveCommandHandler()
            wave_cmd_handler.set_receiver(wave_receiver)
            # Store command handler in application state for window access
            ApplicationState().wave_cmd_handler = wave_cmd_handler
            # Connect signals for logging
            wave_receiver.command_received.connect(wave_cmd_handler.handle_command)
            # Log command handler signals for debugging
            wave_cmd_handler.table_set_received.connect(
                lambda raw_file, client_addr, connection_state, logger=logger: logger.debug(f"table_set: {raw_file} from {client_addr}")
            )
            wave_cmd_handler.copyvar_received.connect(
                lambda var_name, color, client_addr, connection_state, logger=logger: logger.debug(f"copyvar: {var_name} color {color} from {client_addr}")
            )
            wave_cmd_handler.open_file_received.connect(
                lambda raw_file, client_addr, connection_state, logger=logger: logger.debug(f"open_file: {raw_file} from {client_addr}")
            )
            wave_cmd_handler.add_trace_received.connect(
                lambda var_name, axis, color, client_addr, connection_state, logger=logger: logger.debug(f"add_trace: {var_name} axis {axis} from {client_addr}")
            )
            wave_cmd_handler.invalid_command_received.connect(
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
    # Prevent Qt from loading GTK theme plugin which triggers portal permission
    # checks for theme settings. When the portal denies access (snap/sandbox
    # environments, or when D-Bus portal is unavailable), Qt's window
    # decorations break (white title bar, no min/max/close buttons).
    # Force these settings BEFORE QApplication is constructed:
    #   QT_QPA_PLATFORMTHEME=''  — disable platform theme plugin (no GTK/GNOME)
    #   QT_STYLE_OVERRIDE=Fusion — ensure Fusion style is used for widgets
    # Fusion style provides consistent cross-platform widget rendering and
    # does not depend on any desktop environment theming infrastructure.
    os.environ.setdefault('QT_QPA_PLATFORMTHEME', '')
    os.environ.setdefault('QT_STYLE_OVERRIDE', 'Fusion')
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # If xschem port is busy, ask user whether to launch standalone
    if xschem_port_busy:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            None,
            "Port Conflict",
            f"TCP port {args.xschem_port} is already in use by another session.\n\n"
            "Launch without TCP server?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Ok,
        )
        if reply == QMessageBox.StandardButton.Close:
            return 0

    # Script launcher: single .py file executes before GUI
    py_scripts = [f for f in args.files if f.lower().endswith('.py')]
    if len(py_scripts) == 1 and len(args.files) == 1:
        logger.info(f"Running script: {py_scripts[0]}")
        from pqwave.session.api import SessionAPI, get_command_registry
        from functools import partial
        import builtins as _blt
        _builtin_names = set(dir(_blt))
        session = SessionAPI()
        ns = {"session": session, "np": __import__("numpy")}
        for name, entry in get_command_registry().items():
            if name not in _builtin_names:
                ns[name] = partial(entry["fn"], session)
        try:
            with open(py_scripts[0], "r", encoding="utf-8") as fh:
                exec(fh.read(), ns)
        except Exception as e:
            logger.error(f"Script error: {e}")
            print(f"Script error: {e}", file=sys.stderr)
            return 1
        logger.info("Script executed, launching GUI with resulting state")
        args.files.remove(py_scripts[0])

    # Validate: .json must be the only file argument
    json_files = [f for f in args.files if f.lower().endswith('.json')]
    other_files = [f for f in args.files if not f.lower().endswith('.json')]
    if json_files and other_files:
        logger.error("Cannot mix .json project file with .raw/.vcd files")
        print("Error: Cannot open .json project file together with .raw/.vcd files.", file=sys.stderr)
        return 1
    if len(json_files) > 1:
        logger.error("Only one .json project file can be opened at a time")
        print("Error: Only one .json project file can be opened at a time.", file=sys.stderr)
        return 1

    # Create window
    initial_files = json_files + other_files  # .json first, then raws/vcds
    if initial_files:
        logger.info(f"Opening files from command line: {initial_files}")
        window = MainWindow(
            initial_files=initial_files,
            xschem_ba_port=args.xschem_ba_port,
            auto_connect=getattr(args, 'connect', None),
            auto_connect_sch_path=getattr(args, 'sch_path', None),
        )
    else:
        window = MainWindow(
            xschem_ba_port=args.xschem_ba_port,
            auto_connect=getattr(args, 'connect', None),
            auto_connect_sch_path=getattr(args, 'sch_path', None),
        )

    # Start wave receiver after window is created (so signals are connected)
    if wave_receiver is not None:
        if wave_receiver.start():
            logger.info(f"Wave receiver started on port {args.xschem_port}")
            wave_servers.append(wave_receiver)
        else:
            logger.warning("Wave receiver failed to start (port conflict)")

    # Cleanup wave servers on exit
    app.aboutToQuit.connect(lambda: [server.stop() for server in wave_servers])

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())