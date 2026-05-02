#!/usr/bin/env python3
"""Test extracted model classes"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    try:
        from pqwave.models.rawfile import RawFile
        from pqwave.models.dataset import Dataset, Variable
        from pqwave.models.trace import Trace, AxisAssignment
        from pqwave.models.state import ApplicationState, AxisId, AxisConfig
        print("✓ Successfully imported all model classes")
    except ImportError as e:
        print(f"✗ Failed to import model classes: {e}")
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
                    # Test Dataset creation
                    ds = Dataset(rf, 0)
                    print(f"✓ Created Dataset: {ds}")
                    print(f"  Title: {ds.title}")
                    print(f"  Plotname: {ds.plotname}")
                    print(f"  Variables: {ds.n_variables}")
                    print(f"  Points: {ds.n_points}")

                    # Test variable access
                    var_names = ds.get_variable_names(include_derived=True)
                    print(f"  Variable names ({len(var_names)}):")
                    for i, name in enumerate(var_names[:5]):  # Show first 5
                        print(f"    {i+1}. {name}")
                    if len(var_names) > 5:
                        print(f"    ... and {len(var_names) - 5} more")

                    # Test getting a variable
                    if var_names:
                        var = ds.get_variable(var_names[0])
                        if var:
                            print(f"✓ Retrieved variable '{var_names[0]}': {var}")
                            print(f"  Data shape: {var.data.shape}")
                            print(f"  Is complex: {var.is_complex}")

                    # Test ApplicationState
                    state = ApplicationState()
                    print(f"✓ Created ApplicationState: {state}")

                    # Add dataset to state
                    state.add_dataset(ds)
                    print(f"  Added dataset to state, total datasets: {len(state.datasets)}")

                    # Test creating and adding a trace
                    if ds.n_variables >= 2:
                        x_var = ds.get_variable(var_names[0])
                        y_var = ds.get_variable(var_names[1])
                        if x_var and y_var:
                            trace = Trace(
                                name=f"Test trace",
                                expression=f"{var_names[1]} vs {var_names[0]}",
                                x_data=x_var.data,
                                y_data=y_var.data,
                                y_axis=AxisAssignment.Y1,
                                color=(255, 0, 0),
                                line_width=1.5
                            )
                            state.add_trace(trace)
                            print(f"✓ Added trace to state, total traces: {len(state.traces)}")
                            print(f"  Trace: {trace}")

                    # Test axis configuration
                    config = state.get_axis_config(AxisId.Y1)
                    print(f"✓ Retrieved Y1 axis config: log_mode={config.log_mode}, auto_range={config.auto_range}")

                    # Test state serialization
                    state_dict = state.to_dict()
                    print(f"✓ State serialized to dict with keys: {list(state_dict.keys())}")

            except Exception as e:
                print(f"✗ Error testing models: {e}")
                import traceback
                traceback.print_exc()
                sys.exit(1)
        else:
            print(f"✗ File not found: {raw_file}")
    else:
        print("ℹ No raw file provided for model test")
        print("  Usage: python test_models.py <rawfile>")

    print("\n✓ Model extraction test completed")
