#!/usr/bin/env python3
"""Basic tests for pqwave"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_import():
    """Test that the module can be imported"""
    try:
        import pqwave
        print("✓ pqwave module imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import pqwave: {e}")
        return False

def test_version():
    """Test version information"""
    try:
        import pqwave
        # Check if version is defined in module
        if hasattr(pqwave, '__version__'):
            print(f"✓ Version found: {pqwave.__version__}")
        else:
            print("ℹ No __version__ attribute found")
        return True
    except Exception as e:
        print(f"✗ Error checking version: {e}")
        return False

def test_main_function():
    """Test that main function exists"""
    try:
        import pqwave
        if hasattr(pqwave, 'main'):
            print("✓ main function found")
            return True
        else:
            print("✗ main function not found")
            return False
    except Exception as e:
        print(f"✗ Error checking main function: {e}")
        return False

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