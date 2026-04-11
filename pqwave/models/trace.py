#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Trace model for plotted waveforms.

A Trace represents a single waveform plot with associated data and visual
properties. It is independent of UI components and can be serialized/deserialized.
"""

import numpy as np
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


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
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate data after initialization."""
        if len(self.x_data) != len(self.y_data):
            raise ValueError(f"x_data length ({len(self.x_data)}) != y_data length ({len(self.y_data)})")

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
        """Convert trace to serializable dictionary."""
        return {
            'name': self.name,
            'expression': self.expression,
            'x_data': self.x_data.tolist(),
            'y_data': self.y_data.tolist(),
            'y_axis': self.y_axis.value,
            'color': self.color,
            'line_width': self.line_width,
            'visible': self.visible,
            'dataset_idx': self.dataset_idx,
            'metadata': self.metadata
        }

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
            metadata=data.get('metadata', {})
        )

    def __repr__(self) -> str:
        return f"Trace(name='{self.name}', expression='{self.expression}', points={self.n_points}, y_axis={self.y_axis.value})"