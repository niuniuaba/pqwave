"""Tests for ApplicationState MC integration."""
from pqwave.models.state import ApplicationState
from pqwave.models.mc_collection import MCRun, MCRunCollection


def test_state_has_mc_collection_field():
    state = ApplicationState()
    # mc_collection starts as None
    assert state.mc_collection is None


def test_state_mc_collection_set_and_clear():
    state = ApplicationState()
    runs = [MCRun(dataset_idx=0, step_index=i) for i in range(5)]
    mc = MCRunCollection(runs=runs, display_mode="envelope")
    state.mc_collection = mc
    assert state.mc_collection is not None
    assert state.mc_collection.display_mode == "envelope"
    state.mc_collection = None
    assert state.mc_collection is None
