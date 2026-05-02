#!/usr/bin/env python3
"""Test imports for restructured pqwave."""

import sys
sys.path.insert(0, '.')

if __name__ == '__main__':
    print("Testing imports for restructured pqwave...")

    # Test basic package imports
    try:
        import pqwave
        print("✓ Imported pqwave package")
        print(f"  Version: {pqwave.__version__}")
        print(f"  Author: {pqwave.__author__}")
    except Exception as e:
        print(f"✗ Failed to import pqwave: {e}")
        sys.exit(1)

    # Test model imports
    try:
        from pqwave.models.rawfile import RawFile
        print("✓ Imported RawFile")
    except Exception as e:
        print(f"✗ Failed to import RawFile: {e}")

    try:
        from pqwave.models.expression import ExprEvaluator
        print("✓ Imported ExprEvaluator")
    except Exception as e:
        print(f"✗ Failed to import ExprEvaluator: {e}")

    try:
        from pqwave.models.state import ApplicationState
        print("✓ Imported ApplicationState")
    except Exception as e:
        print(f"✗ Failed to import ApplicationState: {e}")

    # Test UI imports
    try:
        from pqwave.ui.main_window import MainWindow
        print("✓ Imported MainWindow")
    except Exception as e:
        print(f"✗ Failed to import MainWindow: {e}")
        import traceback
        traceback.print_exc()

    try:
        from pqwave.ui.plot_widget import PlotWidget
        print("✓ Imported PlotWidget")
    except Exception as e:
        print(f"✗ Failed to import PlotWidget: {e}")

    try:
        from pqwave.ui.control_panel import ControlPanel
        print("✓ Imported ControlPanel")
    except Exception as e:
        print(f"✗ Failed to import ControlPanel: {e}")

    try:
        from pqwave.ui.trace_manager import TraceManager
        print("✓ Imported TraceManager")
    except Exception as e:
        print(f"✗ Failed to import TraceManager: {e}")

    try:
        from pqwave.ui.axis_manager import AxisManager
        print("✓ Imported AxisManager")
    except Exception as e:
        print(f"✗ Failed to import AxisManager: {e}")

    try:
        from pqwave.ui.menu_manager import MenuManager
        print("✓ Imported MenuManager")
    except Exception as e:
        print(f"✗ Failed to import MenuManager: {e}")

    # Test utility imports
    try:
        from pqwave.utils.colors import ColorManager
        print("✓ Imported ColorManager")
    except Exception as e:
        print(f"✗ Failed to import ColorManager: {e}")

    try:
        from pqwave.utils.log_axis import LogAxisItem
        print("✓ Imported LogAxisItem")
    except Exception as e:
        print(f"✗ Failed to import LogAxisItem: {e}")

    print("\nAll imports tested.")
