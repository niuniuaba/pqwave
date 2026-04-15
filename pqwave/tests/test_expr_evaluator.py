#!/usr/bin/env python3
"""Test extracted ExprEvaluator class"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pqwave.models.expression import ExprEvaluator
    from pqwave.models.rawfile import RawFile
    print("✓ Successfully imported ExprEvaluator and RawFile")
except ImportError as e:
    print(f"✗ Failed to import: {e}")
    sys.exit(1)

# Test with a sample raw file if provided
if len(sys.argv) > 1:
    raw_file = sys.argv[1]
    if os.path.exists(raw_file):
        try:
            rf = RawFile(raw_file)
            evaluator = ExprEvaluator(rf, 0)
            print(f"✓ Successfully created ExprEvaluator for {raw_file}")
            print(f"  Number of points: {evaluator.n_points}")

            # Test with some basic expressions
            var_names = rf.get_variable_names()
            if var_names:
                # Try a simple variable
                simple_var = var_names[0]
                try:
                    result = evaluator.evaluate(simple_var)
                    print(f"✓ Evaluated '{simple_var}': shape = {result.shape}")
                except Exception as e:
                    print(f"✗ Error evaluating '{simple_var}': {e}")

                # Try a simple arithmetic expression if we have at least 2 variables
                if len(var_names) >= 2:
                    test_expr = f"{var_names[1]} + 1.5"
                    try:
                        result = evaluator.evaluate(test_expr)
                        print(f"✓ Evaluated '{test_expr}': shape = {result.shape}")
                    except Exception as e:
                        print(f"✗ Error evaluating '{test_expr}': {e}")
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
    else:
        print(f"✗ File not found: {raw_file}")
else:
    print("ℹ No raw file provided for evaluation test")
    print("  Usage: python test_expr_evaluator.py <rawfile>")

print("\n✓ ExprEvaluator extraction test completed")