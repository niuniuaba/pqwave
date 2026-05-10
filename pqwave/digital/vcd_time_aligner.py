"""VCD time alignment — maps VCD event timestamps to a raw file time grid.

Uses vectorized np.searchsorted for O(N log M) alignment.
"""

import numpy as np
from pqwave.logging_config import get_logger

logger = get_logger(__name__)


def align_vcd_to_raw(
    raw_time: np.ndarray,
    vcd_time: np.ndarray,
    vcd_values: np.ndarray,
) -> np.ndarray:
    """Align VCD event data to a raw file's time grid via ZOH.

    For each raw timestamp, finds the last VCD event at or before that time.
    Output has the same length as raw_time.

    Args:
        raw_time: Time grid from the raw file (monotonic).
        vcd_time: VCD event timestamps (monotonic).
        vcd_values: VCD values at each event timestamp.

    Returns:
        Aligned values at each raw time point.
    """
    n_vcd = len(vcd_time)
    if n_vcd == 0:
        logger.warning("align_vcd_to_raw: empty VCD signal, returning -1.0 for all points")
        return np.full(len(raw_time), -1.0, dtype=np.float64)

    idx = np.searchsorted(vcd_time, raw_time, side='right') - 1
    idx = np.clip(idx, 0, n_vcd - 1)
    return vcd_values[idx]


def vcd_to_step_arrays(vcd_time: np.ndarray,
                        vcd_values: np.ndarray) -> tuple:
    """Convert sparse VCD events to stair-step (x, y) arrays.

    Each transition i→i+1 produces two points:
      (t_i+1, v_i) and (t_i+1, v_i+1)

    When rendered with line-mode PlotCurveItem, this draws vertical edges
    at each transition — matching the analog view in mixed-signal mode.
    """
    n = len(vcd_time)
    if n == 0:
        return vcd_time.copy(), vcd_values.copy()
    if n == 1:
        return (np.array([vcd_time[0], vcd_time[0] + 1e-9], dtype=np.float64),
                np.array([vcd_values[0], vcd_values[0]], dtype=np.float64))

    n_out = 2 * (n - 1) + 1  # two points per transition + final
    step_t = np.empty(n_out, dtype=np.float64)
    step_v = np.empty(n_out, dtype=np.float64)
    out_idx = 0
    for i in range(n - 1):
        t_curr = vcd_time[i]
        t_next = vcd_time[i + 1]
        v_curr = vcd_values[i]
        step_t[out_idx] = t_curr
        step_v[out_idx] = v_curr
        out_idx += 1
        eps = (t_next - t_curr) * 0.0001 if t_next > t_curr else 1e-12
        step_t[out_idx] = t_next - eps
        step_v[out_idx] = v_curr
        out_idx += 1

    step_t[out_idx] = vcd_time[-1]
    step_v[out_idx] = vcd_values[-1]

    return step_t, step_v


def vcd_to_uniform_grid(
    vcd_time: np.ndarray,
    vcd_values: np.ndarray,
    n_pts: int = 1600,
) -> tuple:
    """Convert sparse VCD events to a uniform time grid (VCD-only mode).

    Returns (uniform_time, uniform_values).
    """
    n_vcd = len(vcd_time)
    if n_vcd < 2 or n_pts <= 0:
        return vcd_time.copy(), vcd_values.copy()

    t_min, t_max = vcd_time[0], vcd_time[-1]
    if t_max <= t_min:
        return np.array([t_min]), np.array([vcd_values[0]])

    uniform_t = np.linspace(t_min, t_max, min(n_pts, n_vcd * 2),
                            dtype=np.float64)
    uniform_v = align_vcd_to_raw(uniform_t, vcd_time, vcd_values)
    return uniform_t, uniform_v
