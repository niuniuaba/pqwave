"""Tests for MCRun and MCRunCollection dataclasses."""
import numpy as np
from pqwave.models.mc_collection import MCRun, MCRunCollection, CorrelationMatrix


class TestMCRun:
    def test_default_label_is_run_index(self):
        run = MCRun(dataset_idx=0, step_index=3)
        assert run.label == "run 3"

    def test_label_with_params(self):
        run = MCRun(dataset_idx=0, step_index=1, params={"C1": 1.05e-9, "L1": 10.5e-6})
        assert "C1=1.05e-09" in run.label
        assert "L1=1.05e-05" in run.label

    def test_run_holds_correct_indices(self):
        run = MCRun(dataset_idx=2, step_index=5)
        assert run.dataset_idx == 2
        assert run.step_index == 5


class TestMCRunCollection:
    def test_empty_collection(self):
        mc = MCRunCollection(runs=[])
        assert mc.nominal_index == 0
        assert mc.display_mode == "spaghetti"
        assert mc.envelope_sigma == 3.0
        assert mc.run_filter is None

    def test_collection_with_runs(self):
        runs = [MCRun(dataset_idx=0, step_index=i) for i in range(5)]
        mc = MCRunCollection(runs=runs, display_mode="envelope", envelope_sigma=2.0)
        assert mc.active_runs == [0, 1, 2, 3, 4]
        assert mc.active_count == 5

    def test_run_filter_excludes_runs(self):
        runs = [MCRun(dataset_idx=0, step_index=i) for i in range(10)]
        mc = MCRunCollection(runs=runs, run_filter=[0, 2, 4])
        assert mc.active_runs == [0, 2, 4]
        assert mc.active_count == 3

    def test_run_filter_all_is_none(self):
        runs = [MCRun(dataset_idx=0, step_index=i) for i in range(3)]
        mc = MCRunCollection(runs=runs, run_filter="all")
        assert mc.run_filter is None
        assert mc.active_runs == [0, 1, 2]

    def test_has_parameters_true_when_annotated(self):
        runs = [MCRun(dataset_idx=0, step_index=0, params={"X": 0})]
        mc = MCRunCollection(runs=runs, parameters={"X": [0.0]})
        assert mc.has_parameters is True

    def test_has_parameters_false_when_empty(self):
        runs = [MCRun(dataset_idx=0, step_index=0)]
        mc = MCRunCollection(runs=runs)
        assert mc.has_parameters is False

    def test_parameter_values_for_run(self):
        mc = MCRunCollection(
            runs=[MCRun(dataset_idx=0, step_index=i) for i in range(3)],
            parameters={"C1": [1e-9, 1.05e-9, 0.95e-9]}
        )
        assert mc.parameter_values_for_run(1) == {"C1": 1.05e-9}

    def test_get_run_data_indices(self):
        runs = [
            MCRun(dataset_idx=0, step_index=5),
            MCRun(dataset_idx=1, step_index=0),
            MCRun(dataset_idx=0, step_index=7),
        ]
        mc = MCRunCollection(runs=runs)
        assert mc.get_run_data_indices(0) == (0, 5)
        assert mc.get_run_data_indices(1) == (1, 0)


class TestCorrelationMatrix:
    def test_from_symmetric_list(self):
        cm = CorrelationMatrix(
            params=["vth0", "u0", "tox"],
            matrix=[1.0, -0.6, 0.3, -0.6, 1.0, 0.1, 0.3, 0.1, 1.0],
        )
        assert cm.size == 3
        assert cm.get(0, 0) == 1.0
        assert cm.get(0, 1) == -0.6
        assert cm.get(1, 0) == -0.6
        assert cm.get(2, 2) == 1.0

    def test_get_dense_matrix(self):
        cm = CorrelationMatrix(
            params=["a", "b"],
            matrix=[1.0, 0.5, 0.5, 1.0],
        )
        dense = cm.get_dense()
        assert dense.shape == (2, 2)
        assert dense[0, 1] == 0.5
        assert dense[1, 0] == 0.5

    def test_get_flat_returns_original(self):
        cm = CorrelationMatrix(params=["x", "y"], matrix=[1.0, 0.3, 0.3, 1.0])
        assert cm.get_flat() == [1.0, 0.3, 0.3, 1.0]
