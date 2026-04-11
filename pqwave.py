#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pqwave - SPICE Waveform Viewer (legacy wrapper)

This file is maintained for backward compatibility with existing scripts
that execute `python pqwave.py`. It simply imports and runs the modular
entry point from the pqwave package.

For new usage, use `python -m pqwave.main` or the installed `pqwave` command.
"""

import sys
import os

# Add current directory to path to ensure local package import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pqwave.main import main
except ImportError as e:
    print(f"Error importing pqwave package: {e}")
    print("Make sure the pqwave package is installed or in the current directory.")
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())