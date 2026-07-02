#!/usr/bin/env python3
"""Basic tests for pqwave"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_import():
    """Test that the module can be imported"""
    import pqwave
    print("✓ pqwave module imported successfully")


def test_version():
    """Test version information"""
    import pqwave
    # Check if version is defined in module
    assert hasattr(pqwave, "__version__"), "pqwave module missing __version__ attribute"
    print(f"✓ Version found: {pqwave.__version__}")


def test_main_function():
    """Test that main function exists"""
    import pqwave
    assert hasattr(pqwave, "main"), "pqwave module missing main() function"
    print("✓ main function found")


def main():
    """Run all tests"""
    print("Running basic tests for pqwave...")
    print("=" * 40)

    tests = [
        test_import,
        test_version,
        test_main_function,
    ]

    results = []
    for test in tests:
        results.append(test())

    print("=" * 40)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✓ All {total} tests passed!")
        return 0
    else:
        print(f"✗ {total - passed} of {total} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
