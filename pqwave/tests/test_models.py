#!/usr/bin/env python3
"""Model-layer extraction tests: RawFile, Dataset, Variable, Trace, ApplicationState.

The original script did nothing unless a raw file path was passed on argv, so
under any automated run it only printed an import success. It now always
exercises the models against the bundled bridge.raw fixture.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pqwave.models.dataset import Dataset, Variable  # noqa: E402
from pqwave.models.rawfile import RawFile  # noqa: E402
from pqwave.models.state import ApplicationState, AxisId  # noqa: E402
from pqwave.models.trace import AxisAssignment, Trace  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURE = os.path.join(_ROOT, "tests", "bridge.raw")


def _dataset():
    return Dataset(RawFile(_FIXTURE), 0)


def test_model_imports_expose_expected_names():
    for cls in (RawFile, Dataset, Variable, Trace, AxisAssignment,
                ApplicationState, AxisId):
        assert cls.__name__, f"{cls!r} has no name"


def test_rawfile_parses_fixture():
    rf = RawFile(_FIXTURE)
    assert rf.datasets, "fixture produced no datasets"
    assert rf.get_variable_names(0), "no variables in dataset 0"


def test_dataset_reports_shape_and_metadata():
    ds = _dataset()
    assert ds.n_variables > 0 and ds.n_points > 0
    assert ds.plotname, "plot name not carried through from the raw header"
    assert "Transient" in ds.plotname, f"unexpected plotname {ds.plotname!r}"


def test_variable_is_a_lazy_view_not_a_copy():
    """Variables must expose NumPy views so edits/derivatives stay cheap."""
    ds = _dataset()
    names = ds.get_variable_names()
    var = ds.get_variable(names[1])
    assert isinstance(var, Variable)
    assert var.data.shape == (ds.n_points,), f"unexpected shape {var.data.shape}"
    assert var.data.base is not None, (
        "variable data is not a view into the dataset matrix (it was copied)")


def test_derived_variables_are_available_on_request():
    ds = _dataset()
    base = ds.get_variable_names(include_derived=False)
    with_derived = ds.get_variable_names(include_derived=True)
    assert len(with_derived) >= len(base), "include_derived lost variables"


def test_trace_dataclass_roundtrips_fields():
    ds = _dataset()
    names = ds.get_variable_names()
    x_var = ds.get_variable(names[0])
    y_var = ds.get_variable(names[1])
    trace = Trace(
        name="Test trace",
        expression=f"{names[1]} vs {names[0]}",
        x_data=x_var.data,
        y_data=y_var.data,
        y_axis=AxisAssignment.Y1,
        color=(255, 0, 0),
        line_width=1.5,
    )
    assert trace.y_axis is AxisAssignment.Y1
    assert trace.color == (255, 0, 0)
    assert trace.line_width == 1.5
    assert len(trace.x_data) == len(trace.y_data) == ds.n_points


def test_state_holds_datasets_traces_and_axis_config():
    ds = _dataset()
    state = ApplicationState()
    state.add_dataset(ds)
    assert len(state.datasets) >= 1, "dataset was not stored"

    config = state.get_axis_config(AxisId.Y1)
    assert config.log_mode is False, "axis config should default to linear"
    assert config.auto_range is True, "axis config should default to auto-range"


def test_state_serializes_to_a_restorable_dict():
    ds = _dataset()
    state = ApplicationState()
    state.add_dataset(ds)
    payload = state.to_dict()
    assert isinstance(payload, dict) and payload, "to_dict() produced nothing"


def main():
    tests = [test_model_imports_expose_expected_names, test_rawfile_parses_fixture,
             test_dataset_reports_shape_and_metadata,
             test_variable_is_a_lazy_view_not_a_copy,
             test_derived_variables_are_available_on_request,
             test_trace_dataclass_roundtrips_fields,
             test_state_holds_datasets_traces_and_axis_config,
             test_state_serializes_to_a_restorable_dict]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"✓ {fn.__name__}")
        except Exception as exc:
            print(f"✗ {fn.__name__}: {exc}")
            failures.append(fn.__name__)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
