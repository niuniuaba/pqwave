#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Power analyzer — pure-numpy computation of P(t) = V(t) × I(t) over a
specified time range, with optional switching/conduction loss separation
via a user-supplied voltage threshold.
"""

from __future__ import annotations

import numpy as np


def power_analysis(
    v_data: np.ndarray,
    i_data: np.ndarray,
    t_data: np.ndarray,
    xmin: float,
    xmax: float,
    v_threshold: float | None = None,
) -> dict:
    """Compute power analysis over [xmin, xmax].

    Args:
        v_data: Voltage samples (same length as t_data)
        i_data: Current samples
        t_data: Time samples (monotonic)
        xmin, xmax: Analysis window bounds in time units
        v_threshold: Vds(on) threshold for ON/OFF detection.
            If None, only summary (no cycle breakdown) is returned.

    Returns:
        Dict with keys:
        - avg_power: float
        - total_energy: float
        - p_inst: np.ndarray (P(t) over the window)
        - t_seg: np.ndarray (time over the window)
        - cycles: list of per-cycle dicts (empty if no threshold)
        - num_cycles: int
    """
    mask = (t_data >= xmin) & (t_data <= xmax)
    if not mask.any():
        return _empty_result()

    t_seg = t_data[mask]
    v_seg = v_data[mask]
    i_seg = i_data[mask]

    p_inst = v_seg * i_seg
    dt = np.diff(t_seg)
    avg_power = float(np.mean(p_inst))
    # Trapezoidal integral
    total_energy = float(np.sum((p_inst[:-1] + p_inst[1:]) / 2.0 * dt))

    cycles = []
    if v_threshold is not None:
        cycles = _detect_cycles(t_seg, v_seg, i_seg, p_inst, v_threshold)

    return {
        'avg_power': avg_power,
        'total_energy': total_energy,
        'p_inst': p_inst,
        't_seg': t_seg,
        'cycles': cycles,
        'num_cycles': len(cycles),
    }


def _detect_cycles(
    t: np.ndarray, v: np.ndarray, i: np.ndarray, p: np.ndarray,
    v_threshold: float,
) -> list[dict]:
    """Detect switching cycles via V crossing the threshold.

    Each cycle is defined as rising-edge-through-threshold to the next
    rising-edge-through-threshold.  Within each cycle, conduction is
    the interval where V < v_threshold; switching is the rest.
    """
    above = v > v_threshold
    # Rising edge: transition from below to above
    rising = (~above[:-1]) & above[1:]
    edge_idx = np.where(rising)[0]

    if len(edge_idx) < 2:
        return []

    cycles = []
    for k in range(len(edge_idx) - 1):
        a = edge_idx[k]
        b = edge_idx[k + 1]
        if b <= a:
            continue

        t_cyc = t[a:b]
        p_cyc = p[a:b]
        v_cyc = v[a:b]
        i_cyc = i[a:b]
        dt_cyc = np.diff(t_cyc)

        e_total = float(np.sum((p_cyc[:-1] + p_cyc[1:]) / 2.0 * dt_cyc))

        # Conduction: V below threshold.  Switching: V above threshold.
        cond_mask = v_cyc < v_threshold
        sw_mask = ~cond_mask
        e_cond = _integrate(p_cyc, t_cyc, cond_mask)
        e_sw = _integrate(p_cyc, t_cyc, sw_mask)

        period = t[b] - t[a]
        freq = 1.0 / period if period > 0 else 0.0

        v_on = v_cyc[cond_mask]
        i_on = i_cyc[cond_mask]
        v_avg = float(np.mean(v_on)) if len(v_on) > 0 else 0.0
        i_avg = float(np.mean(i_on)) if len(i_on) > 0 else 0.0
        duty = float(np.sum(cond_mask)) / len(v_cyc) if len(v_cyc) > 0 else 0.0

        cycles.append({
            'cycle': k + 1,
            'e_sw': e_sw,
            'e_cond': e_cond,
            'e_total': e_total,
            'freq': freq,
            'v_avg_on': v_avg,
            'i_avg_on': i_avg,
            'duty': duty,
        })

    return cycles


def _integrate(p: np.ndarray, t: np.ndarray, mask: np.ndarray) -> float:
    """Trapezoidal integral of P over masked time intervals.

    Handles non-contiguous masks by finding contiguous runs and integrating
    each separately, avoiding spurious energy from gaps between intervals.
    """
    if not mask.any():
        return 0.0
    total = 0.0
    # Find contiguous True runs in the mask
    edges = np.diff(np.concatenate(([0], mask.astype(int), [0])))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    for a, b in zip(starts, ends):
        if b - a < 2:
            continue
        seg_p = p[a:b]
        seg_t = t[a:b]
        dt = np.diff(seg_t)
        total += float(np.sum((seg_p[:-1] + seg_p[1:]) / 2.0 * dt))
    return total


def _empty_result() -> dict:
    return {
        'avg_power': 0.0,
        'total_energy': 0.0,
        'p_inst': np.array([]),
        't_seg': np.array([]),
        'cycles': [],
        'num_cycles': 0,
    }
