#!/usr/bin/env python3
"""Test extracted RawFile class"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    try:
        from pqwave.models.rawfile import RawFile
        print("✓ Successfully imported RawFile from pqwave.models.rawfile")
    except ImportError as e:
        print(f"✗ Failed to import RawFile: {e}")
        sys.exit(1)


def test_xyce_dialect_fallback():
    """Test that RawFile falls back to xyce/ngspice dialect when auto-detect fails."""
    from pqwave.models.rawfile import RawFile

    # bridge_xyce.raw is a Qucs+Xyce file without a Command: header line
    # that spicelib cannot auto-detect
    xyce_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "bridge_xyce.raw"
    )
    if not os.path.exists(xyce_file):
        print("SKIP: bridge_xyce.raw not found")
        return

    rf = RawFile(xyce_file)
    assert len(rf.datasets) == 1, f"Expected 1 dataset, got {len(rf.datasets)}"
    var_names = rf.get_variable_names()
    assert len(var_names) == 10, f"Expected 10 variables, got {len(var_names)}"
    assert "time" in var_names, "Expected 'time' variable"
    assert "VOUT" in var_names, "Expected 'VOUT' variable"
    assert rf.get_num_points() == 499, f"Expected 499 points, got {rf.get_num_points()}"
    print("OK: Xyce dialect fallback works")


if __name__ == '__main__':
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