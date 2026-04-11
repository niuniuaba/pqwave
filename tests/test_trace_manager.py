#!/usr/bin/env python3
"""Test TraceManager imports and basic functionality."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pqwave.ui.trace_manager import TraceManager
    from pqwave.utils.colors import ColorManager
    print("✓ Successfully imported TraceManager and ColorManager")
except ImportError as e:
    print(f"✗ Failed to import: {e}")
    sys.exit(1)

# Test ColorManager
cm = ColorManager()
color = cm.get_next_color()
print(f"✓ ColorManager works, first color: {color}")

# Test TraceManager static method
expr = 'v(out) v(in)'
split = TraceManager.split_expressions(expr)
print(f"✓ split_expressions('{expr}'): {split}")

print("\n✓ TraceManager test completed")