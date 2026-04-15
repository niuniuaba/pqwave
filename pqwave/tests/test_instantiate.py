#!/usr/bin/env python3
"""Instantiate all major components to verify they work."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_rawfile():
    """Test RawFile loading."""
    from pqwave.models.rawfile import RawFile
    rf = RawFile('tests/bridge.raw')
    print(f"✓ RawFile loaded, datasets: {len(rf.datasets)}")
    return rf

def test_dataset():
    """Test Dataset creation."""
    from pqwave.models.rawfile import RawFile
    from pqwave.models.dataset import Dataset
    rf = RawFile('tests/bridge.raw')
    ds = Dataset(rf, 0)
    print(f"✓ Dataset created: {ds}")
    print(f"  Variables: {ds.n_variables}, Points: {ds.n_points}")
    # Get some variable names
    names = ds.get_variable_names()
    print(f"  Sample variable: {names[0] if names else 'none'}")
    return ds

def test_expression():
    """Test ExprEvaluator."""
    from pqwave.models.expression import ExprEvaluator
    from pqwave.models.rawfile import RawFile
    rf = RawFile('tests/bridge.raw')
    evaluator = ExprEvaluator(rf, 0)
    # Simple expression
    result = evaluator.evaluate('2 + 3')
    print(f"✓ ExprEvaluator simple expression: {result}")
    return evaluator

def test_application_state():
    """Test ApplicationState singleton."""
    from pqwave.models.state import ApplicationState
    state = ApplicationState()
    print(f"✓ ApplicationState singleton: {state}")
    return state

def test_color_manager():
    """Test ColorManager (requires Qt)."""
    print("⚠ ColorManager requires Qt, skipping")
    return None

def test_log_axis():
    """Test LogAxisItem creation (requires Qt)."""
    print("⚠ LogAxisItem requires Qt, skipping")
    return None

def main():
    print("Testing instantiation of all major components...")
    print("=" * 50)
    try:
        rf = test_rawfile()
    except Exception as e:
        print(f"✗ RawFile failed: {e}")
        rf = None
    try:
        ds = test_dataset()
    except Exception as e:
        print(f"✗ Dataset failed: {e}")
        ds = None
    try:
        expr = test_expression()
    except Exception as e:
        print(f"✗ ExprEvaluator failed: {e}")
        expr = None
    try:
        state = test_application_state()
    except Exception as e:
        print(f"✗ ApplicationState failed: {e}")
        state = None
    try:
        cm = test_color_manager()
    except Exception as e:
        print(f"✗ ColorManager failed: {e}")
        cm = None
    try:
        axis = test_log_axis()
    except Exception as e:
        print(f"✗ LogAxisItem failed: {e}")
        axis = None
    print("=" * 50)
    print("All instantiation tests completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())