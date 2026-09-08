#!/usr/bin/env python3
"""Instantiate all major components to verify the core model layer works.

Runs both ways: as pytest tests, and as `python pqwave/tests/test_instantiate.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BRIDGE_RAW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tests", "bridge.raw")


def test_rawfile():
    """RawFile loads a real .raw file and exposes at least one dataset."""
    from pqwave.models.rawfile import RawFile
    rf = RawFile(_BRIDGE_RAW)
    assert rf.datasets, "RawFile parsed no datasets"
    assert rf.get_variable_names(0), "dataset 0 has no variables"
    print(f"✓ RawFile loaded, datasets: {len(rf.datasets)}")


def test_dataset():
    """Dataset wraps a parsed raw file with usable variable/point counts."""
    from pqwave.models.rawfile import RawFile
    from pqwave.models.dataset import Dataset
    ds = Dataset(RawFile(_BRIDGE_RAW), 0)
    assert ds.n_variables > 0, "Dataset reported zero variables"
    assert ds.n_points > 0, "Dataset reported zero points"
    names = ds.get_variable_names()
    assert names, "get_variable_names() returned nothing"
    print(f"✓ Dataset created: {ds}")
    print(f"  Variables: {ds.n_variables}, Points: {ds.n_points}")


def test_expression():
    """ExprEvaluator evaluates a literal and a real variable."""
    from pqwave.models.expression import ExprEvaluator
    from pqwave.models.rawfile import RawFile
    rf = RawFile(_BRIDGE_RAW)
    evaluator = ExprEvaluator(rf, 0)
    result = evaluator.evaluate('2 + 3')
    assert len(result) == evaluator.n_points, "literal did not broadcast to full length"
    assert (result == 5).all(), f"'2 + 3' evaluated to {result[0]}"
    var = rf.get_variable_names(0)[0]
    assert len(evaluator.evaluate(var)) == evaluator.n_points, "variable eval wrong length"
    print(f"✓ ExprEvaluator simple expression: {result[0]}")


def test_application_state():
    """ApplicationState is a process-wide singleton."""
    from pqwave.models.state import ApplicationState
    state = ApplicationState()
    assert state is ApplicationState(), "ApplicationState is not a singleton"
    print(f"✓ ApplicationState singleton: {state}")


def test_color_manager():
    """ColorManager hands out distinct colours and tracks usage."""
    from pqwave.utils.colors import ColorManager
    cm = ColorManager()
    first = cm.get_next_color()
    second = cm.get_next_color()
    assert isinstance(first, tuple) and len(first) == 3, f"bad colour {first!r}"
    assert first != second, "ColorManager reused a colour immediately"
    cm.reset()
    assert cm.get_next_color() == first, "reset() did not restart the palette"
    print(f"✓ ColorManager works, first colour: {first}")


def test_log_axis():
    """LogAxisItem toggles log/linear mode without corrupting its state."""
    from pqwave.utils.log_axis import LogAxisItem
    axis = LogAxisItem(orientation='left')
    axis.setLogMode(y=True)
    assert axis.logMode == 1, "setLogMode(y=True) did not enable log mode"
    axis.setLogMode(y=False)
    assert axis.logMode == 0, "setLogMode(y=False) did not clear log mode"
    assert axis.isDbMode() is False, "axis should start outside dB mode"
    axis.setDbMode(True)
    assert axis.isDbMode() is True, "setDbMode(True) did not stick"
    print("✓ LogAxisItem log/dB mode toggles work")


def main():
    """Run every check, reporting rather than aborting on the first failure."""
    print("Testing instantiation of all major components...")
    print("=" * 50)
    failures = []
    for fn in (test_rawfile, test_dataset, test_expression,
               test_application_state, test_color_manager, test_log_axis):
        try:
            fn()
        except Exception as exc:  # report-and-continue is the point here
            print(f"✗ {fn.__name__} failed: {exc}")
            failures.append(fn.__name__)
    print("=" * 50)
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All instantiation tests completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
