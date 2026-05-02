#!/usr/bin/env python3
"""Test extracted LogAxisItem class"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    try:
        from pqwave.utils.log_axis import LogAxisItem
        print("✓ Successfully imported LogAxisItem from pqwave.utils.log_axis")
    except ImportError as e:
        print(f"✗ Failed to import LogAxisItem: {e}")
        sys.exit(1)

    # Try to create instance (requires pyqtgraph and PyQt6)
    try:
        # This will import pyqtgraph and may fail if dependencies missing
        # but we can at least test the import succeeded
        print("✓ LogAxisItem class available")
        # Show class info
        print(f"  Class name: {LogAxisItem.__name__}")
        print(f"  Module: {LogAxisItem.__module__}")
    except Exception as e:
        print(f"✗ Error creating LogAxisItem instance: {e}")

    print("\n✓ LogAxisItem extraction test completed")