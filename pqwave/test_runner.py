#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test runner for pqwave.

This module provides functionality to discover and run all test files
in the tests directory when the --test command-line argument is used.
"""

import sys
import os
import subprocess
import glob
import importlib.util  # noqa: F401
from typing import List, Tuple, Optional


def discover_test_files() -> List[str]:
    """Discover all test files in tests directory

    Returns:
        List of absolute paths to test files
    """
    # Get the directory containing test_runner.py (pqwave directory)
    pqwave_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(pqwave_dir, 'tests')

    if not os.path.exists(test_dir):
        print(f"ERROR: Test directory not found: {test_dir}")
        return []

    # Find all test_*.py files
    test_pattern = os.path.join(test_dir, 'test_*.py')
    test_files = sorted(glob.glob(test_pattern))

    # Filter out any non-Python files and __pycache__ entries
    test_files = [
        f for f in test_files
        if os.path.isfile(f) and not f.endswith('__pycache__')
    ]

    return test_files


def check_test_dependencies() -> bool:
    """Check if required dependencies for tests are available

    Returns:
        True if all dependencies are available, False otherwise
    """
    missing_deps = []

    # Check for spicelib - required for many tests
    try:
        import spicelib  # noqa: F401  (presence probe only)
    except ImportError:
        missing_deps.append('spicelib')

    # Check for PyQt6 - required for UI tests
    try:
        import PyQt6  # noqa: F401  (presence probe only)
    except ImportError:
        missing_deps.append('PyQt6')

    # Check for pyqtgraph
    try:
        import pyqtgraph  # noqa: F401  (presence probe only)
    except ImportError:
        missing_deps.append('pyqtgraph')

    # Check for numpy
    try:
        import numpy  # noqa: F401  (presence probe only)
    except ImportError:
        missing_deps.append('numpy')

    if missing_deps:
        print(f"ERROR: Missing test dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install spicelib PyQt6 pyqtgraph numpy")
        return False

    return True


def run_test_file(test_path: str) -> Tuple[bool, str, Optional[int]]:
    """Run a single test file

    Args:
        test_path: Path to test file

    Returns:
        Tuple of (success, output, exit_code)
    """
    try:
        # Set environment for UI tests
        env = os.environ.copy()
        env['QT_QPA_PLATFORM'] = 'offscreen'

        # Add project root to PYTHONPATH so tests can import pqwave
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pythonpath = env.get('PYTHONPATH', '')
        if pythonpath:
            env['PYTHONPATH'] = f"{project_root}{os.pathsep}{pythonpath}"
        else:
            env['PYTHONPATH'] = project_root

        test_name = os.path.basename(test_path)

        # Run the file under pytest rather than as a bare script.
        #
        # Executing it as a script let a module with no `__main__` block (or with
        # checks that only print) exit 0 and be reported as "passed" while
        # verifying nothing. pytest also turns returning a value from a test into
        # a visible failure signal instead of a silent pass, and collects
        # functions that pytest would otherwise never reach.
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest", test_path,
                "-q", "--no-header", "-p", "no:cacheprovider",
                # A test that returns a bool instead of asserting must not be
                # trusted; make that an error so it can never pass vacuously.
                "-W", "error::pytest.PytestReturnNotNoneWarning",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=60  # per-file allowance; UI files need a little headroom
        )

        output = result.stdout

        # Include stderr in output if present
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr

        # rc 5 means the glob found no tests at all -- that is a broken test
        # file, not a success, so report it as a failure.
        if result.returncode == 5:
            output = ("No tests collected from this file (it is probably a "
                      "manual script); it cannot count as passing.\n" + output)

        success = result.returncode == 0
        return success, output, result.returncode

    except subprocess.TimeoutExpired:
        return False, (
            f"{test_name} timed out after 60 seconds: {test_path}\n"
            "A per-file timeout usually means the file is waiting on a socket or "
            "a subprocess it never releases."
        ), 124
    except Exception as e:
        return False, f"Failed to run {test_name} ({test_path}): {e}", 1


def run_all_tests() -> int:
    """Run all test files and return exit code

    Returns:
        0 if all tests passed, 1 if any test failed
    """
    print("Running pqwave test suites...")
    print("=" * 60)

    # Check dependencies first
    if not check_test_dependencies():
        print("Aborting tests due to missing dependencies")
        return 1

    # Discover test files
    test_files = discover_test_files()
    if not test_files:
        print("ERROR: No test files found")
        return 1

    print(f"Found {len(test_files)} test files")
    print()

    # Run all tests
    results = []
    for test_file in test_files:
        test_name = os.path.basename(test_file)
        print(f"Running {test_name}...")

        success, output, exit_code = run_test_file(test_file)
        results.append((test_name, success, output, exit_code))

        if success:
            print(f"  ✓ {test_name} passed")
        else:
            print(f"  ✗ {test_name} failed (exit code: {exit_code})")
            if output and output.strip():
                # Show first few lines of output for debugging
                lines = output.strip().split('\n')
                if len(lines) > 10:
                    print("  Output (first 10 lines):")
                    for line in lines[:10]:
                        print(f"    {line}")
                    print(f"    ... and {len(lines) - 10} more lines")
                else:
                    print("  Output:")
                    for line in lines:
                        print(f"    {line}")

        print()  # Blank line between tests

    # Print summary
    print("=" * 60)
    passed = sum(1 for _, success, _, _ in results if success)
    total = len(results)

    print(f"Test Results: {passed}/{total} passed")

    # Show failed tests summary
    failures = [(name, output, exit_code)
                for name, success, output, exit_code in results if not success]
    if failures:
        print("\nFailed tests:")
        for name, output, exit_code in failures:
            print(f"  - {name} (exit code: {exit_code})")
            if output and len(output.strip()) < 200:
                # Show brief output for short failures
                print(f"    {output.strip()}")

    # Return appropriate exit code
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


def main():
    """Entry point for standalone test runner"""
    return run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
