"""TraceTypeManager — manages signal type transitions and bus grouping.

Orchestrates toggling between analog/digital/bus trace types.  Modifies
Trace.metadata in-place and notifies the TraceManager when a plot item
needs recreation (type change) or legend refresh.
"""

import re
from typing import List, Callable, Optional, Tuple

import numpy as np

from pqwave.models.trace import Trace
from pqwave.digital.threshold_config import ThresholdConfig
from pqwave.logging_config import get_logger

logger = get_logger(__name__)


class TraceTypeManager:
    """Manages signal type transitions for traces in a panel.

    Does not own traces — operates on Trace objects from ApplicationState.
    """

    def __init__(self, on_recreate: Optional[Callable[[int], None]] = None):
        self._on_recreate = on_recreate

    def set_on_recreate(self, callback: Callable[[int], None]) -> None:
        self._on_recreate = callback

    def set_analog(self, trace: Trace, trace_idx: int) -> None:
        if trace.trace_type == 'analog':
            return
        trace.trace_type = 'analog'
        trace.digital_config = None
        trace.bus_signals = None
        if self._on_recreate:
            self._on_recreate(trace_idx)

    def set_digital(self, trace: Trace, trace_idx: int,
                    config: Optional[ThresholdConfig] = None) -> None:
        if trace.trace_type == 'digital' and config is None:
            return
        trace.trace_type = 'digital'
        trace.bus_signals = None
        if config is not None:
            trace.digital_config = {
                'v_high': config.v_high, 'v_low': config.v_low,
                'v_undef': config.v_undef, 'description': config.description,
            }
        elif trace.digital_config is None:
            if len(trace.y_data) > 0:
                y_lo, y_hi = float(trace.y_data.min()), float(trace.y_data.max())
            else:
                y_lo, y_hi = 0.0, 5.0
            auto = ThresholdConfig.from_range(y_lo, y_hi)
            trace.digital_config = {
                'v_high': auto.v_high, 'v_low': auto.v_low,
                'v_undef': auto.v_undef, 'description': auto.description,
            }
        if self._on_recreate:
            self._on_recreate(trace_idx)

    def toggle(self, trace: Trace, trace_idx: int) -> None:
        if trace.trace_type == 'bus':
            return  # bus traces can't toggle; ungroup first
        if trace.trace_type == 'analog':
            self.set_digital(trace, trace_idx)
        else:
            self.set_analog(trace, trace_idx)

    def group_as_bus(self, traces: List[Trace], name: str,
                     indices: List[int]) -> Optional[Trace]:
        if len(traces) < 1:
            return None

        for t in traces:
            t.trace_type = 'digital'

        # Auto-infer bit order from trace name numeric suffixes.
        ordered = _reorder_by_bit_suffix(traces, indices)
        traces, indices = ordered

        x_data = traces[0].x_data.copy()
        n_pts = len(x_data)
        bus_values = _compute_bus_values(traces, n_pts)

        bus_trace = Trace(
            name=name, expression=name,
            x_data=x_data, y_data=bus_values,
            color=traces[0].color,
            dataset_idx=traces[0].dataset_idx,
        )
        bus_trace.trace_type = 'bus'
        bus_trace.bus_signals = [t.expression for t in traces]
        bus_trace.metadata['bus_display_format'] = 'hex'
        bus_trace.metadata['bus_members_hidden'] = False
        return bus_trace

    def ungroup_bus(self, bus_trace: Trace) -> None:
        if bus_trace.trace_type != 'bus':
            return
        bus_trace.trace_type = 'digital'
        bus_trace.bus_signals = None

    def set_bus_format(self, bus_trace: Trace, fmt: str) -> None:
        if fmt in ('hex', 'bin', 'dec'):
            bus_trace.metadata['bus_display_format'] = fmt


def _extract_bit_suffix(name: str) -> int | None:
    """Extract a bit-number suffix from a trace name.

    Recognises ``d[0]``, ``d0``, ``data_7``, ``bus<3>``.
    Returns the integer or None.
    """
    # bracket: d[0], bus[15]
    m = re.search(r'\[(\d+)\]', name)
    if m:
        return int(m.group(1))
    # angle bracket: bus<3>
    m = re.search(r'<(\d+)>', name)
    if m:
        return int(m.group(1))
    # underscore: data_7, sig_15
    m = re.search(r'_(\d+)$', name)
    if m:
        return int(m.group(1))
    # plain trailing digits: d0, q7  (must have non-digit prefix)
    m = re.search(r'(\d+)$', name)
    if m and m.start() > 0 and not name[m.start() - 1].isdigit():
        return int(m.group(1))
    return None


def _reorder_by_bit_suffix(
    traces: List[Trace], indices: List[int]
) -> Tuple[List[Trace], List[int]]:
    """Reorder *traces* and *indices* so bit 0 (LSB) comes first.

    If every trace has a parseable bit suffix the list is sorted by it.
    Otherwise the original order is preserved.
    """
    suffixes = [_extract_bit_suffix(t.expression) for t in traces]
    if any(s is None for s in suffixes):
        return traces, indices  # keep selection order
    ordered = sorted(zip(suffixes, traces, indices), key=lambda x: x[0])
    return (
        [t for _, t, _ in ordered],
        [i for _, _, i in ordered],
    )


def _compute_bus_values(traces: List[Trace], n_pts: int) -> np.ndarray:
    bus_vals = np.zeros(n_pts, dtype=np.int32)
    # Preserve caller order for user-controlled LSB/MSB assignment
    for i, t in enumerate(traces):
        bit_mask = 1 << i
        y = t.y_data
        if len(y) != n_pts:
            logger.warning(
                "_compute_bus_values: skipping trace '%s' — "
                "length mismatch (%d vs expected %d)",
                t.expression, len(y), n_pts,
            )
            continue
        y_min, y_max = float(y.min()), float(y.max())
        threshold = (y_min + y_max) / 2.0
        bus_vals += np.where(y > threshold, bit_mask, 0).astype(np.int32)
    return bus_vals.astype(np.float64)
