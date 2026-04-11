#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ApplicationState - Global application state management.

This module provides a singleton class that manages the global state of the
application, including datasets, traces, axis configurations, and UI settings.
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from .dataset import Dataset
from .trace import Trace, AxisAssignment


class AxisId(Enum):
    """Axis identifiers."""
    X = 'X'
    Y1 = 'Y1'
    Y2 = 'Y2'


@dataclass
class AxisConfig:
    """Configuration for a single axis."""
    label: str = ''
    log_mode: bool = False
    range: Optional[Tuple[float, float]] = None
    visible: bool = True
    grid: bool = True
    auto_range: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'label': self.label,
            'log_mode': self.log_mode,
            'range': self.range,
            'visible': self.visible,
            'grid': self.grid,
            'auto_range': self.auto_range
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AxisConfig':
        """Create from dictionary."""
        return cls(
            label=data.get('label', ''),
            log_mode=data.get('log_mode', False),
            range=data.get('range'),
            visible=data.get('visible', True),
            grid=data.get('grid', True),
            auto_range=data.get('auto_range', True)
        )


class ApplicationState:
    """Singleton class managing global application state.

    This class follows the singleton pattern to ensure there's only one
    instance of application state throughout the application.
    """

    _instance: Optional['ApplicationState'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize default state."""
        self.datasets: List[Dataset] = []
        self.current_dataset_idx: int = 0
        self.current_x_var: Optional[str] = None
        self.traces: List[Trace] = []

        # Axis configurations
        self.axis_configs: Dict[AxisId, AxisConfig] = {
            AxisId.X: AxisConfig(label='X'),
            AxisId.Y1: AxisConfig(label='Y1'),
            AxisId.Y2: AxisConfig(label='Y2')
        }

        # UI settings
        self.grid_visible: bool = True
        self.legend_visible: bool = True
        self.status_bar_visible: bool = True
        self.toolbar_visible: bool = True
        self.plot_title: str = ''

    # Dataset management

    @property
    def current_dataset(self) -> Optional[Dataset]:
        """Get the current dataset."""
        if self.datasets and 0 <= self.current_dataset_idx < len(self.datasets):
            return self.datasets[self.current_dataset_idx]
        return None

    def add_dataset(self, dataset: Dataset) -> int:
        """Add a dataset and return its index."""
        self.datasets.append(dataset)
        return len(self.datasets) - 1

    def remove_dataset(self, dataset_idx: int) -> bool:
        """Remove a dataset by index."""
        if 0 <= dataset_idx < len(self.datasets):
            # Remove traces associated with this dataset
            self.traces = [t for t in self.traces if t.dataset_idx != dataset_idx]
            # Adjust dataset indices for traces with higher indices
            for trace in self.traces:
                if trace.dataset_idx > dataset_idx:
                    trace.dataset_idx -= 1
            # Remove the dataset
            self.datasets.pop(dataset_idx)
            # Adjust current_dataset_idx if needed
            if self.current_dataset_idx >= len(self.datasets):
                self.current_dataset_idx = max(0, len(self.datasets) - 1)
            return True
        return False

    def set_current_dataset(self, dataset_idx: int) -> bool:
        """Set current dataset index."""
        if 0 <= dataset_idx < len(self.datasets):
            self.current_dataset_idx = dataset_idx
            return True
        return False

    def clear_datasets(self) -> None:
        """Clear all datasets and associated traces."""
        self.datasets.clear()
        self.traces.clear()
        self.current_dataset_idx = 0

    # Trace management

    def add_trace(self, trace: Trace) -> None:
        """Add a trace."""
        self.traces.append(trace)

    def remove_trace(self, trace_idx: int) -> bool:
        """Remove a trace by index."""
        if 0 <= trace_idx < len(self.traces):
            self.traces.pop(trace_idx)
            return True
        return False

    def clear_traces(self) -> None:
        """Remove all traces."""
        self.traces.clear()

    def get_traces_for_dataset(self, dataset_idx: int) -> List[Trace]:
        """Get all traces for a specific dataset."""
        return [t for t in self.traces if t.dataset_idx == dataset_idx]

    # Axis configuration

    def get_axis_config(self, axis_id: AxisId) -> AxisConfig:
        """Get configuration for an axis."""
        return self.axis_configs[axis_id]

    def set_axis_config(self, axis_id: AxisId, config: AxisConfig) -> None:
        """Set configuration for an axis."""
        self.axis_configs[axis_id] = config

    def set_axis_log_mode(self, axis_id: AxisId, log_mode: bool) -> None:
        """Set log mode for an axis."""
        self.axis_configs[axis_id].log_mode = log_mode

    def set_axis_range(self, axis_id: AxisId, range_min: float, range_max: float) -> None:
        """Set range for an axis."""
        self.axis_configs[axis_id].range = (range_min, range_max)
        self.axis_configs[axis_id].auto_range = False

    def set_axis_auto_range(self, axis_id: AxisId) -> None:
        """Enable auto-ranging for an axis."""
        self.axis_configs[axis_id].auto_range = True
        self.axis_configs[axis_id].range = None

    # State serialization

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire state to serializable dictionary."""
        return {
            'datasets': [
                {
                    'title': ds.title,
                    'plotname': ds.plotname,
                    'n_variables': ds.n_variables,
                    'n_points': ds.n_points
                }
                for ds in self.datasets
            ],
            'current_dataset_idx': self.current_dataset_idx,
            'traces': [trace.to_dict() for trace in self.traces],
            'axis_configs': {axis.value: config.to_dict() for axis, config in self.axis_configs.items()},
            'grid_visible': self.grid_visible,
            'legend_visible': self.legend_visible,
            'status_bar_visible': self.status_bar_visible,
            'toolbar_visible': self.toolbar_visible,
            'plot_title': self.plot_title
        }

    def __repr__(self) -> str:
        return f"ApplicationState(datasets={len(self.datasets)}, traces={len(self.traces)}, current={self.current_dataset_idx})"