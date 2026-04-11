#!/usr/bin/env python3
"""Test extracted RawFile class"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pqwave.models.rawfile import RawFile
    print("✓ Successfully imported RawFile from pqwave.models.rawfile")
except ImportError as e:
    print(f"✗ Failed to import RawFile: {e}")
    sys.exit(1)

# Test with a sample raw file if provided
if len(sys.argv) > 1:
    raw_file = sys.argv[1]
    if os.path.exists(raw_file):
        try:
            rf = RawFile(raw_file)
            print(f"✓ Successfully parsed {raw_file}")
            print(f"  Number of datasets: {len(rf.datasets)}")
            if rf.datasets:
                var_names = rf.get_variable_names()
                print(f"  Variables: {len(var_names)}")
                for i, var in enumerate(var_names[:10]):  # Show first 10
                    print(f"    {i+1}. {var}")
                if len(var_names) > 10:
                    print(f"    ... and {len(var_names) - 10} more")
        except Exception as e:
            print(f"✗ Error parsing {raw_file}: {e}")
            sys.exit(1)
    else:
        print(f"✗ File not found: {raw_file}")
else:
    print("ℹ No raw file provided for parsing test")
    print("  Usage: python test_rawfile.py <rawfile>")

print("\n✓ RawFile extraction test completed")