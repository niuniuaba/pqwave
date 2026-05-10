"""Digital signal rendering: threshold detection and step-waveform generation.

Converts dense analog samples to sparse step-function vertex arrays suitable
for DigitalStepCurveItem rendering.
"""

import numpy as np
from typing import Tuple

from pqwave.digital.threshold_config import ThresholdConfig

MAX_STEP_VERTICES = 3200


def threshold_and_step(
    x_data: np.ndarray,
    y_data: np.ndarray,
    config: ThresholdConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert analog sample data to digital step-function vertices.

    Applies Schmitt-trigger hysteresis: on a rising edge the signal must
    cross V_high to become 1; on a falling edge it must cross V_low to
    become 0.  Intermediate values preserve the previous state.

    Transition times are found by linear interpolation between sample
    points for accurate edge placement.

    Returns (times, levels) — numpy arrays of step vertices.
    Levels: 0.0 (low), 1.0 (high), -0.5 (unknown).
    """
    n = len(y_data)
    if n < 2:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    y = np.asarray(y_data, dtype=np.float64)
    x = np.asarray(x_data, dtype=np.float64)
    v_high = config.v_high
    v_low = config.v_low

    states = np.full(n, -1, dtype=np.int8)

    if y[0] > v_high:
        states[0] = 1
    elif y[0] < v_low:
        states[0] = 0

    prev = states[0]
    for i in range(1, n):
        if prev == 1:
            if y[i] < v_low:
                prev = 0
        elif prev == 0:
            if y[i] > v_high:
                prev = 1
        else:
            if y[i] > v_high:
                prev = 1
            elif y[i] < v_low:
                prev = 0
        states[i] = prev

    transitions = _find_transitions(x, y, states, v_high, v_low)
    times, levels = _build_vertices(transitions, x[-1])
    if len(times) > MAX_STEP_VERTICES:
        times, levels = _downsample_step(times, levels)

    return times, levels


def _find_transitions(x, y, states, v_high, v_low):
    transitions = []
    for i in range(1, len(states)):
        s_prev, s_curr = states[i - 1], states[i]
        if s_curr == s_prev:
            continue

        y_prev, y_curr = y[i - 1], y[i]
        x_prev, x_curr = x[i - 1], x[i]

        if s_curr == 1:
            threshold = v_high
        elif s_curr == 0:
            threshold = v_low
        else:
            threshold = (v_high + v_low) / 2.0

        dy = y_curr - y_prev
        if abs(dy) > 1e-15:
            t_cross = x_prev + (threshold - y_prev) * (x_curr - x_prev) / dy
            t_cross = max(x_prev, min(x_curr, t_cross))
        else:
            t_cross = x_curr

        transitions.append((t_cross, s_prev, s_curr))
    return transitions


def _build_vertices(transitions, end_time):
    if not transitions:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    n_verts = len(transitions) * 2 + 3  # +start, +end extension, +final
    times = np.empty(n_verts, dtype=np.float64)
    levels = np.empty(n_verts, dtype=np.float64)

    first_t, first_prev, _ = transitions[0]
    times[0] = first_t
    levels[0] = _state_to_level(first_prev)

    idx = 1
    for t_cross, s_before, s_after in transitions:
        times[idx] = t_cross
        levels[idx] = _state_to_level(s_before)
        idx += 1
        times[idx] = t_cross
        levels[idx] = _state_to_level(s_after)
        idx += 1

    # Extend final level to end of data so the waveform doesn't truncate
    # at the last transition.  The loop above already wrote the last
    # transition point; only add the final hold segment.
    last_level = _state_to_level(transitions[-1][2])
    times[idx] = end_time
    levels[idx] = last_level

    return times[:idx + 1], levels[:idx + 1]


def _state_to_level(state):
    if state == 1:
        return 1.0
    elif state == 0:
        return 0.0
    return -0.5


def _downsample_step(times, levels):
    target = MAX_STEP_VERTICES
    n = len(times)
    if n <= target:
        return times, levels

    n_trans = (n - 2) // 2
    keep_every = max(1, n_trans // (target // 2))

    new_times = [times[0]]
    new_levels = [levels[0]]

    for i in range(1, n - 1, 2):
        trans_idx = (i - 1) // 2
        if trans_idx % keep_every == 0:
            # Insert flat segment at last kept level to bridge skipped
            # transitions (prevents diagonal jumps across gaps).
            if new_levels and new_levels[-1] != levels[i]:
                new_times.append(times[i])
                new_levels.append(new_levels[-1])
            new_times.extend([times[i], times[i + 1]])
            new_levels.extend([levels[i], levels[i + 1]])

    new_times.append(times[-1])
    new_levels.append(levels[-1])
    return np.array(new_times), np.array(new_levels)
