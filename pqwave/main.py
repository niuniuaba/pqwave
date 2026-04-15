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
from PyQt6.QtWidgets import QApplication

from pqwave.ui.main_window import MainWindow
from pqwave.logging_config import setup_logging


def main():
    """Main entry point for pqwave."""
    parser = argparse.ArgumentParser(
        description="pqwave - SPICE Waveform Viewer",
        epilog="Example: pqwave simulation.raw"
    )
    parser.add_argument(
        "raw_file",
        nargs="?",  # Optional positional argument
        help="SPICE raw file to open"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="pqwave 0.2.2"
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

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())