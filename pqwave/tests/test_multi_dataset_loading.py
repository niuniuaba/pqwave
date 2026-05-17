"""Integration tests for multi-dataset loading."""
import pytest
import numpy as np
from pqwave.models.state import ApplicationState
from pqwave.models.trace import Trace


@pytest.fixture
def state():
    """Return a fresh state (reset for testing)."""
    s = ApplicationState()
    s.clear_datasets()
    if hasattr(s, 'mc_collection'):
        s.mc_collection = None
    return s


class TestMultiDatasetState:
    def test_add_dataset_appends(self, state):
        assert len(state.datasets) == 0
        state.datasets.append("dummy1")
        assert len(state.datasets) == 1
        state.datasets.append("dummy2")
        assert len(state.datasets) == 2

    def test_remove_dataset_cleans_traces(self, state):
        state.datasets = ["ds0", "ds1"]
        panel = state.register_panel("test_p")
        state.active_panel_id = "test_p"
        t0 = Trace(name="t0", expression="v(out)", x_data=np.array([1.0, 2.0]),
                    y_data=np.array([3.0, 4.0]), dataset_idx=0)
        t1 = Trace(name="t1", expression="v(in)", x_data=np.array([1.0, 2.0]),
                    y_data=np.array([5.0, 6.0]), dataset_idx=1)
        state.panels["test_p"].traces = [t0, t1]
        state.remove_dataset(0)
        assert len(state.datasets) == 1
        assert len(state.panels["test_p"].traces) == 1
        assert state.panels["test_p"].traces[0].name == "t1"

    def test_remove_dataset_adjusts_indices(self, state):
        state.datasets = ["ds0", "ds1", "ds2"]
        panel = state.register_panel("test_p")
        state.active_panel_id = "test_p"
        t2 = Trace(name="t2", expression="v(a)", x_data=np.array([1.0]),
                    y_data=np.array([2.0]), dataset_idx=2)
        state.panels["test_p"].traces = [t2]
        state.remove_dataset(0)
        assert state.panels["test_p"].traces[0].dataset_idx == 1

    def test_clear_datasets(self, state):
        state.datasets = ["ds0", "ds1"]
        panel = state.register_panel("test_p")
        state.active_panel_id = "test_p"
        state.panels["test_p"].traces = [Trace(name="t", expression="x",
            x_data=np.array([1.0]), y_data=np.array([2.0]), dataset_idx=0)]
        state.clear_datasets()
        assert len(state.datasets) == 0
