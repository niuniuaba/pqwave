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
        version="pqwave 0.2.2.0"
    )

    args = parser.parse_args()

    app = QApplication(sys.argv)

    # Create window with optional initial file
    if args.raw_file:
        print(f"Opening file from command line: {args.raw_file}")
        window = MainWindow(initial_file=args.raw_file)
    else:
        window = MainWindow()

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())