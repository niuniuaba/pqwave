"""BusSignal model for digital bus waveform display.

Manages bus member traces, bit ordering, value computation, and display
format (hex, binary, decimal).
"""

from typing import List, Optional
import numpy as np


class BusSignal:
    """Represents a multi-bit digital bus assembled from individual digital traces.

    Bit 0 (LSB) = member_traces[0], Bit N-1 (MSB) = member_traces[-1].
    """

    def __init__(self, name: str, member_traces: list,
                 bit_order: Optional[List[int]] = None):
        self.name = name
        self._members = member_traces
        self._bit_order = (bit_order if bit_order is not None
                           else list(range(len(member_traces))))
        self._format = 'hex'
        self._expanded = False

    @property
    def width(self) -> int:
        return len(self._members)

    @property
    def display_format(self) -> str:
        return self._format

    @display_format.setter
    def display_format(self, fmt: str) -> None:
        if fmt in ('hex', 'bin', 'dec'):
            self._format = fmt

    @property
    def expanded(self) -> bool:
        return self._expanded

    @expanded.setter
    def expanded(self, value: bool) -> None:
        self._expanded = value

    def compute_values(self, threshold: Optional[float] = None) -> np.ndarray:
        """Compute integer bus values from member trace data."""
        if not self._members:
            return np.array([], dtype=np.int32)
        n_pts = len(self._members[0].y_data)
        bus_vals = np.zeros(n_pts, dtype=np.int32)
        for i, t in enumerate(self._members):
            y = t.y_data
            if len(y) != n_pts:
                continue
            if threshold is None:
                thr = (float(y.min()) + float(y.max())) / 2.0
            else:
                thr = threshold
            bit_mask = 1 << i
            bus_vals += np.where(y > thr, bit_mask, 0).astype(np.int32)
        return bus_vals

    def format_value(self, value: int) -> str:
        w = self.width
        if self._format == 'hex':
            return f"{value:0{(w + 3) // 4}X}"
        elif self._format == 'bin':
            return f"{value:0{w}b}"
        return str(value)

    def member_expressions(self) -> List[str]:
        return [t.expression for t in self._members]
