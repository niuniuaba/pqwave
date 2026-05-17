"""Monte Carlo run collection data model."""
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np


@dataclass
class MCRun:
    """A single run in an MC collection."""
    dataset_idx: int
    step_index: int
    params: dict = field(default_factory=dict)
    label: str = ""

    def __post_init__(self):
        if not self.label:
            parts = [f"run {self.step_index}"]
            for name, val in self.params.items():
                parts.append(f"{name}={val}")
            self.label = ", ".join(parts)


@dataclass
class MCRunCollection:
    """Collection of MC runs loaded from one or more simulation files."""
    runs: List[MCRun]
    nominal_index: int = 0
    parameters: dict = field(default_factory=dict)  # param_name -> [values per run]
    display_mode: str = "spaghetti"   # spaghetti, envelope, single
    envelope_sigma: float = 3.0
    run_filter: Optional[List[int]] = None  # None = all runs

    def __post_init__(self):
        if self.run_filter == "all":
            object.__setattr__(self, "run_filter", None)

    @property
    def has_parameters(self) -> bool:
        return len(self.parameters) > 0

    @property
    def active_runs(self) -> List[int]:
        if self.run_filter is None:
            return list(range(len(self.runs)))
        return self.run_filter

    @property
    def active_count(self) -> int:
        return len(self.active_runs)

    def parameter_values_for_run(self, run_index: int) -> dict:
        result = {}
        for name, values in self.parameters.items():
            if run_index < len(values):
                result[name] = values[run_index]
        return result

    def get_run_data_indices(self, run_index: int) -> tuple:
        """Return (dataset_idx, step_index) for a run by its collection index."""
        run = self.runs[run_index]
        return (run.dataset_idx, run.step_index)

    def to_dict(self) -> dict:
        return {
            "runs": [{"dataset_idx": r.dataset_idx, "step_index": r.step_index,
                       "params": r.params, "label": r.label} for r in self.runs],
            "nominal_index": self.nominal_index,
            "parameters": self.parameters,
            "display_mode": self.display_mode,
            "envelope_sigma": self.envelope_sigma,
            "run_filter": self.run_filter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MCRunCollection":
        runs = [MCRun(**r) for r in data.get("runs", [])]
        return cls(
            runs=runs,
            nominal_index=data.get("nominal_index", 0),
            parameters=data.get("parameters", {}),
            display_mode=data.get("display_mode", "spaghetti"),
            envelope_sigma=data.get("envelope_sigma", 3.0),
            run_filter=data.get("run_filter"),
        )


@dataclass
class CorrelationMatrix:
    """Square correlation matrix stored as flat list (row-major)."""
    params: List[str]
    matrix: List[float]

    @property
    def size(self) -> int:
        return len(self.params)

    def get(self, row: int, col: int) -> float:
        return self.matrix[row * self.size + col]

    def get_dense(self) -> np.ndarray:
        return np.array(self.matrix).reshape(self.size, self.size)

    def get_flat(self) -> List[float]:
        return list(self.matrix)

    @classmethod
    def from_dense(cls, params: List[str], dense: np.ndarray) -> "CorrelationMatrix":
        return cls(params=params, matrix=dense.flatten().tolist())

    def to_dict(self) -> dict:
        return {"params": self.params, "matrix": self.matrix}

    @classmethod
    def from_dict(cls, data: dict) -> "CorrelationMatrix":
        return cls(params=data["params"], matrix=data["matrix"])
