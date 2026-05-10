#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Trace model for plotted waveforms.

A Trace represents a single waveform plot with associated data and visual
properties. It is independent of UI components and can be serialized/deserialized.
"""

import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class DigitalConfigDict(TypedDict, total=False):
    """Expected schema for Trace.digital_config metadata dict."""
    v_high: float
    v_low: float
    v_undef: float
    description: str


class AxisAssignment(Enum):
    """Y-axis assignment for a trace."""
    Y1 = 'Y1'
    Y2 = 'Y2'


@dataclass
class Trace:
    """Represents a plotted trace (waveform).

    Attributes:
        name: Display name (usually the expression)
        expression: Original expression string (e.g., 'v(out)')
        x_data: X-axis data array
        y_data: Y-axis data array
        y_axis: Which Y axis to plot on (Y1 or Y2)
        color: RGB tuple (r, g, b) with values 0-255
        line_width: Line width in pixels
        visible: Whether the trace is visible
        dataset_idx: Index of the source dataset (for multi-dataset support)
        selected: Whether the trace is selected in the legend
        metadata: Additional metadata (e.g., variable names, units)
    """
    name: str
    expression: str
    x_data: np.ndarray
    y_data: np.ndarray
    y_axis: AxisAssignment = AxisAssignment.Y1
    color: Tuple[int, int, int] = (0, 0, 255)  # Blue
    line_width: float = 1.0
    visible: bool = True
    dataset_idx: int = 0
    selected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate data after initialization."""
        if len(self.x_data) != len(self.y_data):
            raise ValueError(f"x_data length ({len(self.x_data)}) != y_data length ({len(self.y_data)})")

    @property
    def trace_type(self) -> str:
        """Signal type: 'analog', 'digital', or 'bus'.  Stored in metadata
        for backward-compatible serialization (old JSON files default to
        'analog')."""
        return self.metadata.get('trace_type', 'analog')

    @trace_type.setter
    def trace_type(self, value: str) -> None:
        self.metadata['trace_type'] = value

    @property
    def digital_config(self) -> Optional[DigitalConfigDict]:
        """Per-trace digital threshold configuration, if set."""
        return self.metadata.get('digital_config', None)

    @digital_config.setter
    def digital_config(self, value: Optional[DigitalConfigDict]) -> None:
        if value is None:
            self.metadata.pop('digital_config', None)
        else:
            self.metadata['digital_config'] = value

    @property
    def bus_signals(self) -> Optional[List[str]]:
        """List of trace expression strings that form this bus, if bus type."""
        return self.metadata.get('bus_signals', None)

    @bus_signals.setter
    def bus_signals(self, value: Optional[List[str]]) -> None:
        if value is None:
            self.metadata.pop('bus_signals', None)
        else:
            self.metadata['bus_signals'] = value

    @property
    def n_points(self) -> int:
        """Number of data points in the trace."""
        return len(self.x_data)

    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Get (x_min, x_max, y_min, y_max) bounds of the trace."""
        x_min, x_max = np.min(self.x_data), np.max(self.x_data)
        y_min, y_max = np.min(self.y_data), np.max(self.y_data)
        return (x_min, x_max, y_min, y_max)

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to serializable dictionary (includes data arrays)."""
        safe_meta = {
            k: v for k, v in self.metadata.items()
            if k not in ('vcd_times', 'vcd_values', '_bus_bot_item')
        }
        return {
            'name': self.name,
            'expression': self.expression,
            'x_data': self.x_data.tolist(),
            'y_data': self.y_data.tolist(),
            'y_axis': self.y_axis.value,
            'color': self.color,
            'line_width': self.line_width,
            'visible': self.visible,
            'selected': self.selected,
            'dataset_idx': self.dataset_idx,
            'metadata': safe_meta
        }

    def to_per_file_dict(self) -> Dict[str, Any]:
        """Convert trace to dict without data arrays (for per-file state)."""
        # Strip data-heavy VCD metadata that is reconstructed on reload.
        safe_meta = {
            k: v for k, v in self.metadata.items()
            if k not in ('vcd_times', 'vcd_values', '_bus_bot_item')
        }
        return {
            'name': self.name,
            'expression': self.expression,
            'y_axis': self.y_axis.value,
            'color': self.color,
            'line_width': self.line_width,
            'visible': self.visible,
            'selected': self.selected,
            'dataset_idx': self.dataset_idx,
            'metadata': safe_meta,
        }

    @classmethod
    def from_per_file_dict(cls, data: Dict[str, Any]) -> 'Trace':
        """Create trace from per-file dict (no data arrays)."""
        return cls(
            name=data['name'],
            expression=data['expression'],
            x_data=np.array([]),
            y_data=np.array([]),
            y_axis=AxisAssignment(data['y_axis']),
            color=tuple(data['color']),
            line_width=data['line_width'],
            visible=data['visible'],
            dataset_idx=data['dataset_idx'],
            selected=data.get('selected', False),
            metadata=data.get('metadata', {})
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Trace':
        """Create trace from dictionary."""
        x_data = np.array(data['x_data'])
        y_data = np.array(data['y_data'])
        return cls(
            name=data['name'],
            expression=data['expression'],
            x_data=x_data,
            y_data=y_data,
            y_axis=AxisAssignment(data['y_axis']),
            color=tuple(data['color']),
            line_width=data['line_width'],
            visible=data['visible'],
            dataset_idx=data['dataset_idx'],
            selected=data.get('selected', False),
            metadata=data.get('metadata', {})
        )

    def __repr__(self) -> str:
        return f"Trace(name='{self.name}', expression='{self.expression}', points={self.n_points}, y_axis={self.y_axis.value})"