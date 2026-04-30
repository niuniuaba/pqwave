#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Measure engine — evaluates measurement expressions and returns scalar results.

Parses function calls like avg(v(out), from=1m, to=10m), resolves vector
names via a caller-supplied data lookup, and computes the corresponding
scalar measurement using numpy.
"""

from __future__ import annotations

import re
from typing import Callable

import numpy as np

from pqwave.ui.measure_registry import lookup_measure

_METRIC_SUFFIXES: dict[str, float] = {
    "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
    "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12,
    "mil": 25.4e-6,
}


def _parse_value(s: str) -> float:
    """Parse a numeric string with optional SPICE metric suffix."""
    s = s.strip().rstrip("x").lower()
    if not s:
        raise ValueError("empty value string")
    for suffix, scale in sorted(_METRIC_SUFFIXES.items(),
                                key=lambda kv: -len(kv[0])):
        if s.endswith(suffix) and len(s) > len(suffix):
            return float(s[:-len(suffix)]) * scale
    return float(s)


def _parse_expr(expr: str) -> tuple[str, str, list[str], dict[str, str]]:
    """Parse a measure expression.

    Returns (func_name, vector_name, positional_args, kwargs).
    positional_args excludes the vector (first arg).
    kwargs values are kept as strings for lazy parsing.
    """
    s = expr.strip()
    m = re.match(r'^([a-zA-Z_]\w*)\s*\(', s)
    if not m:
        raise ValueError(f"Invalid measure expression: {expr!r}")
    func_name = m.group(1).lower()
    rest = s[m.end():]

    # Find the vector argument end — track paren depth.
    # Break at top-level comma (depth==1) or closing paren (depth==0).
    depth = 1
    i = 0
    while i < len(rest) and depth > 0:
        ch = rest[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                break
        elif ch == ',' and depth == 1:
            break
        i += 1

    if depth == 0:
        # Hit closing paren — no more args: e.g. "avg(v(r1))"
        vector_name = rest[:i].strip()
        remainder = rest[i + 1:].strip()
    elif depth == 1 and i < len(rest) and rest[i] == ',':
        # Hit top-level comma: e.g. "when_cross(v(r1), 96)"
        vector_name = rest[:i].strip()
        remainder = rest[i + 1:].strip().rstrip(')')
    else:
        raise ValueError(f"Unmatched parentheses in: {expr!r}")

    positional: list[str] = []
    kwargs: dict[str, str] = {}

    if remainder:
        parts = []
        d = 0
        start = 0
        for j, ch in enumerate(remainder):
            if ch == '(':
                d += 1
            elif ch == ')':
                d -= 1
            elif ch == ',' and d == 0:
                parts.append(remainder[start:j].strip())
                start = j + 1
        parts.append(remainder[start:].strip())

        for part in parts:
            if '=' in part:
                k, v = part.split('=', 1)
                kwargs[k.strip().lower()] = v.strip()
            else:
                positional.append(part.strip())

    return func_name, vector_name, positional, kwargs


def _window_data(
    x: np.ndarray, y: np.ndarray, kwargs: dict[str, str]
) -> tuple[np.ndarray, np.ndarray]:
    """Clip data to the [from, to] range specified in kwargs."""
    x_from = x[0]
    x_to = x[-1]
    if "from" in kwargs:
        x_from = _parse_value(kwargs.pop("from"))
    if "to" in kwargs:
        x_to = _parse_value(kwargs.pop("to"))

    mask = (x >= x_from) & (x <= x_to)
    if not np.any(mask):
        raise ValueError(f"No data points in range [{x_from}, {x_to}]")
    return x[mask], y[mask]


def _find_crossings(x: np.ndarray, y: np.ndarray, threshold: float,
                    edge: str = "rise") -> list[float]:
    """Find x-coordinates where y crosses threshold.

    edge: 'rise' or 'fall'. Uses linear interpolation for sub-sample accuracy.
    """
    crossings: list[float] = []
    for i in range(len(y) - 1):
        y0, y1 = y[i], y[i + 1]
        if edge == "rise":
            if y0 < threshold <= y1:
                frac = (threshold - y0) / (y1 - y0) if y1 != y0 else 0.0
                crossings.append(x[i] + frac * (x[i + 1] - x[i]))
        else:
            if y0 > threshold >= y1:
                frac = (y0 - threshold) / (y0 - y1) if y0 != y1 else 0.0
                crossings.append(x[i] + frac * (x[i + 1] - x[i]))
    return crossings


# ---- Individual measure functions ----

def _measure_min(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(np.min(y))

def _measure_max(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(np.max(y))

def _measure_avg(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(np.mean(y))

def _measure_rms(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(np.sqrt(np.mean(y ** 2)))

def _measure_pp(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(np.max(y) - np.min(y))

def _measure_integ(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(np.trapz(y, x))

def _measure_min_at(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(x[np.argmin(y)])

def _measure_max_at(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    return float(x[np.argmax(y)])

def _measure_rise_time(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    threshold = _parse_value(kwargs.pop("threshold", "")) if "threshold" in kwargs else (np.min(y) + np.max(y)) / 2
    rise_n = int(_parse_value(kwargs.pop("rise", "1"))) if "rise" in kwargs else 1
    low_pct = float(kwargs.pop("low_pct", "10")) / 100.0
    high_pct = float(kwargs.pop("high_pct", "90")) / 100.0

    y_min, y_max = np.min(y), np.max(y)
    low_level = y_min + low_pct * (y_max - y_min)
    high_level = y_min + high_pct * (y_max - y_min)

    low_cross = _find_crossings(x, y, low_level, "rise")
    high_cross = _find_crossings(x, y, high_level, "rise")

    idx = rise_n - 1
    if idx >= len(low_cross) or idx >= len(high_cross):
        raise ValueError(
            f"rise_time: edge {rise_n} not found "
            f"(found {len(low_cross)} low, {len(high_cross)} high crossings)"
        )
    return float(high_cross[idx] - low_cross[idx])

def _measure_fall_time(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    fall_n = int(_parse_value(kwargs.pop("fall", "1"))) if "fall" in kwargs else 1
    high_pct = float(kwargs.pop("high_pct", "90")) / 100.0
    low_pct = float(kwargs.pop("low_pct", "10")) / 100.0

    y_min, y_max = np.min(y), np.max(y)
    high_level = y_min + high_pct * (y_max - y_min)
    low_level = y_min + low_pct * (y_max - y_min)

    high_cross = _find_crossings(x, y, high_level, "fall")
    low_cross = _find_crossings(x, y, low_level, "fall")

    idx = fall_n - 1
    if idx >= len(high_cross) or idx >= len(low_cross):
        raise ValueError(f"fall_time: edge {fall_n} not found")
    return float(high_cross[idx] - low_cross[idx])

def _measure_period(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    threshold = _parse_value(kwargs.pop("threshold", "")) if "threshold" in kwargs else (np.min(y) + np.max(y)) / 2
    rise_n = int(_parse_value(kwargs.pop("rise", "1"))) if "rise" in kwargs else 1

    crossings = _find_crossings(x, y, threshold, "rise")
    idx = rise_n - 1
    if idx + 1 >= len(crossings):
        raise ValueError(
            f"period: need at least {rise_n + 1} rising edges, found {len(crossings)}"
        )
    return float(crossings[idx + 1] - crossings[idx])

def _measure_frequency(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    period = _measure_period(x, y, kwargs)
    return 1.0 / period

def _measure_duty_cycle(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    threshold = _parse_value(kwargs.pop("threshold", "")) if "threshold" in kwargs else (np.min(y) + np.max(y)) / 2
    rise_n = int(_parse_value(kwargs.pop("rise", "1"))) if "rise" in kwargs else 1

    rise_cross = _find_crossings(x, y, threshold, "rise")
    fall_cross = _find_crossings(x, y, threshold, "fall")

    r_idx = rise_n - 1
    if r_idx >= len(rise_cross):
        raise ValueError(f"duty_cycle: rising edge {rise_n} not found")
    t_rise = rise_cross[r_idx]
    later_falls = [f for f in fall_cross if f > t_rise]
    if not later_falls:
        raise ValueError(f"duty_cycle: no falling edge after rising edge {rise_n}")
    t_fall = later_falls[0]

    if r_idx + 1 >= len(rise_cross):
        raise ValueError(f"duty_cycle: need at least {rise_n + 1} rising edges")
    period = rise_cross[r_idx + 1] - t_rise
    return float((t_fall - t_rise) / period * 100.0)

def _measure_pulse_width(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    threshold = _parse_value(kwargs.pop("threshold", "")) if "threshold" in kwargs else (np.min(y) + np.max(y)) / 2
    rise_n = int(_parse_value(kwargs.pop("rise", "1"))) if "rise" in kwargs else 1

    rise_cross = _find_crossings(x, y, threshold, "rise")
    fall_cross = _find_crossings(x, y, threshold, "fall")

    idx = rise_n - 1
    if idx >= len(rise_cross):
        raise ValueError(f"pulse_width: rising edge {rise_n} not found")
    t_rise = rise_cross[idx]
    later_falls = [f for f in fall_cross if f > t_rise]
    if not later_falls:
        raise ValueError(f"pulse_width: no falling edge after rising edge {rise_n}")
    return float(later_falls[0] - t_rise)

def _measure_settling_time(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    settle_frac = float(kwargs.pop("settle_frac", "0.02"))
    final_val = y[-1]
    band = abs(final_val) * settle_frac if final_val != 0 else settle_frac
    for i in range(len(y) - 1, -1, -1):
        if abs(y[i] - final_val) > band:
            return float(x[-1] - x[i])
    return 0.0

def _measure_slew_rate(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    dydx = np.abs(np.diff(y) / np.diff(x))
    return float(np.max(dydx))

def _measure_overshoot(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    final_val = y[-1]
    peak = np.max(y)
    if final_val == 0:
        return 0.0
    return float((peak - final_val) / abs(final_val) * 100.0)

def _measure_undershoot(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    final_val = y[-1]
    trough = np.min(y)
    if final_val == 0:
        return 0.0
    return float((final_val - trough) / abs(final_val) * 100.0)

def _measure_find_at(x: np.ndarray, y: np.ndarray, kwargs: dict,
                     positional: list[str]) -> float:
    if positional:
        x_pos = _parse_value(positional[0])
    else:
        x_pos = _parse_value(kwargs.pop("at", "0"))
    return float(np.interp(x_pos, x, y))

def _measure_when_cross(x: np.ndarray, y: np.ndarray, kwargs: dict,
                        positional: list[str]) -> float:
    if positional:
        val = _parse_value(positional[0])
    else:
        val = _parse_value(kwargs.pop("val", "0"))
    rise_n = int(_parse_value(kwargs.pop("rise", "0"))) if "rise" in kwargs else None
    fall_n = int(_parse_value(kwargs.pop("fall", "0"))) if "fall" in kwargs else None

    if rise_n is not None and rise_n > 0:
        crossings = _find_crossings(x, y, val, "rise")
        idx = rise_n - 1
    elif fall_n is not None and fall_n > 0:
        crossings = _find_crossings(x, y, val, "fall")
        idx = fall_n - 1
    else:
        crossings = _find_crossings(x, y, val, "rise")
        idx = 0

    if idx >= len(crossings):
        raise ValueError(f"when_cross: crossing not found (have {len(crossings)})")
    return float(crossings[idx])

def _measure_deriv_at(x: np.ndarray, y: np.ndarray, kwargs: dict,
                      positional: list[str]) -> float:
    if positional:
        x_pos = _parse_value(positional[0])
    else:
        x_pos = _parse_value(kwargs.pop("at", "0"))
    idx = np.searchsorted(x, x_pos)
    idx = max(1, min(idx, len(x) - 2))
    return float((y[idx + 1] - y[idx - 1]) / (x[idx + 1] - x[idx - 1]))


# ---- Spectrum (deferred) ----

def _measure_thd(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    raise NotImplementedError("thd requires FFT support (not yet implemented)")

def _measure_sinad(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    raise NotImplementedError("sinad requires FFT support (not yet implemented)")

def _measure_snr(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    raise NotImplementedError("snr requires FFT support (not yet implemented)")

def _measure_sfdr(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    raise NotImplementedError("sfdr requires FFT support (not yet implemented)")


def _measure_find_when(
    find_vector: str,
    positional: list[str],
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    evaluate_fn: Callable,
) -> float:
    """Evaluate find_when(find_expr, condition_vector, threshold).

    find_when(v(r1), v(r1), 96) → value of v(r1) when condition v(r1) crosses 96.
    The threshold may be a scalar string ("96") or a measure expression ("max(v(r1))").
    """
    if len(positional) < 2:
        raise ValueError(
            "find_when requires at least 2 args: condition_vector, threshold"
        )

    cond_vector = positional[0]
    threshold_str = positional[1]

    # Get data for the find expression
    result = get_data(find_vector)
    if result is None:
        raise ValueError(f"Vector not found: {find_vector!r}")
    find_x, find_y = result

    # Get data for the condition vector
    result = get_data(cond_vector)
    if result is None:
        raise ValueError(f"Vector not found: {cond_vector!r}")
    cond_x, cond_y = result

    # Evaluate threshold — try as a measure expression first (e.g. max(v(r1))),
    # fall back to numeric parsing
    try:
        threshold = evaluate_fn(threshold_str, get_data)
    except Exception:
        threshold = _parse_value(threshold_str)

    # Determine crossing edge
    if "rise" in kwargs:
        edge_n = int(_parse_value(kwargs.pop("rise")))
        crossings = _find_crossings(cond_x, cond_y, threshold, "rise")
        idx = edge_n - 1
    elif "fall" in kwargs:
        edge_n = int(_parse_value(kwargs.pop("fall")))
        crossings = _find_crossings(cond_x, cond_y, threshold, "fall")
        idx = edge_n - 1
    else:
        crossings = _find_crossings(cond_x, cond_y, threshold, "rise")
        idx = 0

    if idx >= len(crossings):
        raise ValueError(
            f"find_when: crossing not found at threshold {threshold} "
            f"(have {len(crossings)} crossings)"
        )
    return float(np.interp(crossings[idx], find_x, find_y))


_IMPLS: dict[str, Callable] = {
    "min": _measure_min,
    "max": _measure_max,
    "avg": _measure_avg,
    "rms": _measure_rms,
    "pp": _measure_pp,
    "integ": _measure_integ,
    "min_at": _measure_min_at,
    "max_at": _measure_max_at,
    "rise_time": _measure_rise_time,
    "fall_time": _measure_fall_time,
    "period": _measure_period,
    "frequency": _measure_frequency,
    "duty_cycle": _measure_duty_cycle,
    "pulse_width": _measure_pulse_width,
    "settling_time": _measure_settling_time,
    "slew_rate": _measure_slew_rate,
    "overshoot": _measure_overshoot,
    "undershoot": _measure_undershoot,
    "find_at": _measure_find_at,
    "find_when": _measure_find_when,
    "when_cross": _measure_when_cross,
    "deriv_at": _measure_deriv_at,
    "thd": _measure_thd,
    "sinad": _measure_sinad,
    "snr": _measure_snr,
    "sfdr": _measure_sfdr,
}


def evaluate_measure(
    expr: str,
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
) -> float:
    """Evaluate a single measurement expression.

    Args:
        expr: e.g. "avg(v(out), from=1m, to=10m)"
        get_data: callable(vector_name) -> (x_data, y_data) or None

    Returns:
        Scalar float result.
    """
    func_name, vector_name, positional, kwargs = _parse_expr(expr)

    impl = _IMPLS.get(func_name)
    if impl is None:
        raise ValueError(f"Unknown measure function: {func_name!r}")

    # find_when has its own data-lookup calling convention
    if func_name == "find_when":
        return impl(vector_name, positional, kwargs, get_data, evaluate_measure)

    result = get_data(vector_name)
    if result is None:
        raise ValueError(f"Vector not found: {vector_name!r}")
    x_data, y_data = result

    if "from" in kwargs or "to" in kwargs:
        x_data, y_data = _window_data(x_data, y_data, kwargs)

    if func_name in ("find_at", "when_cross", "deriv_at"):
        return impl(x_data, y_data, kwargs, positional)
    return impl(x_data, y_data, kwargs)
