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

try:
    from pqwave.ui.fft_engine import (
        compute_fft as _fft_compute,
        compute_thd_from_spectrum as _fft_thd,
        compute_sinad_from_spectrum as _fft_sinad,
        compute_snr_from_spectrum as _fft_snr,
        compute_sfdr_from_spectrum as _fft_sfdr,
    )
    _HAS_FFT_ENGINE = True
except ImportError:
    _HAS_FFT_ENGINE = False

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
        remainder = rest[i + 1:].strip()
        if remainder.endswith(')'):
            remainder = remainder[:-1].strip()
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


def _apply_td(
    x: np.ndarray, y: np.ndarray, kwargs: dict[str, str]
) -> tuple[np.ndarray, np.ndarray]:
    """Discard data before TD=val delay time."""
    if "td" in kwargs:
        td_val = _parse_value(kwargs.pop("td"))
        mask = x >= td_val
        if not np.any(mask):
            raise ValueError(f"No data points after TD={td_val}")
        return x[mask], y[mask]
    return x, y


def _find_crossings(x: np.ndarray, y: np.ndarray, threshold: float,
                    edge: str = "any") -> list[float]:
    """Find x-coordinates where y crosses threshold.

    edge: 'rise', 'fall', or 'any'. Uses linear interpolation for sub-sample accuracy.
    """
    crossings: list[float] = []
    for i in range(len(y) - 1):
        y0, y1 = y[i], y[i + 1]
        if edge == "rise":
            cond = y0 <= threshold < y1
        elif edge == "fall":
            cond = y0 >= threshold > y1
        else:
            cond = (y0 <= threshold < y1) or (y0 >= threshold > y1)
        if cond:
            frac = (threshold - y0) / (y1 - y0) if y1 != y0 else 0.0
            crossings.append(x[i] + frac * (x[i + 1] - x[i]))
    return crossings


def _find_crossing_index(
    x: np.ndarray, y: np.ndarray, threshold: float,
    kwargs: dict[str, str],
) -> tuple[list[float], int]:
    """Determine which crossing to use from rise=/fall=/cross= kwargs.

    Returns (crossings_list, 0-based index).
    """
    total_rise = len(_find_crossings(x, y, threshold, "rise"))
    total_fall = len(_find_crossings(x, y, threshold, "fall"))
    total_any = len(_find_crossings(x, y, threshold, "any"))

    specified = False
    edge = "rise"
    idx = 0

    if "rise" in kwargs:
        edge_n_str = kwargs.pop("rise")
        if edge_n_str.lower() == "last":
            if total_rise > 0:
                idx = total_rise - 1
                edge = "rise"
                specified = True
        else:
            n = int(_parse_value(edge_n_str))
            if n > 0:
                idx = n - 1
                edge = "rise"
                specified = True
    elif "fall" in kwargs:
        edge_n_str = kwargs.pop("fall")
        if edge_n_str.lower() == "last":
            if total_fall > 0:
                idx = total_fall - 1
                edge = "fall"
                specified = True
        else:
            n = int(_parse_value(edge_n_str))
            if n > 0:
                idx = n - 1
                edge = "fall"
                specified = True
    elif "cross" in kwargs:
        edge_n_str = kwargs.pop("cross")
        if edge_n_str.lower() == "last":
            if total_any > 0:
                idx = total_any - 1
                edge = "any"
                specified = True
        else:
            n = int(_parse_value(edge_n_str))
            if n > 0:
                idx = n - 1
                edge = "any"
                specified = True

    if not specified:
        idx = 0 if total_rise > 0 else -1
        edge = "rise"

    crossings = _find_crossings(x, y, threshold, edge)
    if idx < 0 or idx >= len(crossings):
        raise ValueError(
            f"Crossing {edge}={idx + 1} not found "
            f"(have {len(crossings)} {edge} crossings at {threshold})"
        )
    return crossings, idx


# ---- Trigger point resolution ----

def _find_trigger_point(
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    prefix: str = "trig_",
) -> float:
    """Parse trigger kwargs and find time/freq point.

    Triggers can be of two forms:
      - {prefix}at=<val> → return val directly
      - {prefix}val=<val> with optional {prefix}rise/{prefix}fall/{prefix}cross/{prefix}td
        and {prefix}var=<vector> → find crossing time

    prefix is "trig_" for TRIG and "targ_" for TARG.
    """
    at_key = f"{prefix}at"
    var_key = f"{prefix}var"
    val_key = f"{prefix}val"

    if at_key in kwargs:
        return _parse_value(kwargs.pop(at_key))

    var_name = kwargs.pop(var_key, None)
    val_str = kwargs.pop(val_key, None)

    if var_name is None or val_str is None:
        raise ValueError(
            f"{prefix.upper()}requires either {at_key}=<value> or "
            f"{var_key}=<vector> {val_key}=<value>"
        )

    result = get_data(var_name)
    if result is None:
        raise ValueError(f"Vector not found: {var_name!r}")
    x_data, y_data = result

    threshold = _parse_value(val_str)

    # Extract {prefix}rise/fall/cross/td kwargs and strip prefix
    edge_kwargs: dict[str, str] = {}
    plen = len(prefix)
    edge_keys = frozenset({f"{prefix}{k}" for k in ("rise", "fall", "cross", "td")})
    for k in list(kwargs.keys()):
        if k in edge_keys:
            edge_kwargs[k[plen:]] = kwargs.pop(k)

    if "td" in edge_kwargs:
        x_data, y_data = _apply_td(x_data, y_data, {"td": edge_kwargs.pop("td")})

    crossings, idx = _find_crossing_index(x_data, y_data, threshold, edge_kwargs)
    return float(crossings[idx])


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
    return float(np.trapezoid(y, x))

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
    return float(low_cross[idx] - high_cross[idx])

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
    if abs(final_val) < 1e-12:
        return 0.0
    return float((peak - final_val) / abs(final_val) * 100.0)

def _measure_undershoot(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    final_val = y[-1]
    trough = np.min(y)
    if abs(final_val) < 1e-12:
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

    crossings, idx = _find_crossing_index(x, y, val, kwargs)
    return float(crossings[idx])


def _measure_when_eq(
    var1: str,
    positional: list[str],
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    _evaluate_fn: Callable,
) -> float:
    """Evaluate WHEN var1=var2 → return time of first equal crossing."""
    if len(positional) < 1:
        raise ValueError("when_eq requires a second vector: when_eq(v1, v2)")

    var2 = positional[0]
    result1 = get_data(var1)
    result2 = get_data(var2)
    if result1 is None:
        raise ValueError(f"Vector not found: {var1!r}")
    if result2 is None:
        raise ValueError(f"Vector not found: {var2!r}")

    # Both vectors should share the same x-axis
    x, y1 = result1
    _, y2 = result2
    diff = y1 - y2

    return _measure_when_cross(x, diff, kwargs, ["0"])


def _measure_deriv_at(x: np.ndarray, y: np.ndarray, kwargs: dict,
                      positional: list[str]) -> float:
    if positional:
        x_pos = _parse_value(positional[0])
    else:
        x_pos = _parse_value(kwargs.pop("at", "0"))
    idx = np.searchsorted(x, x_pos)
    idx = max(1, min(idx, len(x) - 2))
    return float((y[idx + 1] - y[idx - 1]) / (x[idx + 1] - x[idx - 1]))


# ---- Spectrum ----

def _get_fft_config():
    """Return the global FFT configuration from ApplicationState."""
    from pqwave.models.state import ApplicationState
    return ApplicationState().fft_config


def _compute_spectrum(x: np.ndarray, y: np.ndarray, kwargs: dict
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Run FFT on time-domain data, respecting global config and per-call overrides."""
    cfg = _get_fft_config()
    window = kwargs.pop("window", cfg.window)
    fft_size = int(kwargs.pop("fft_size", str(cfg.fft_size)) if "fft_size" in kwargs else cfg.fft_size)
    dc_removal_str = kwargs.pop("dc_removal", None)
    if dc_removal_str is not None:
        dc_removal = dc_removal_str.lower() in ("yes", "true", "1")
    else:
        dc_removal = cfg.dc_removal
    # spectral analysis functions assume dB magnitude; ignore config preference
    kwargs.pop("representation", None)
    return _fft_compute(x, y, window=window, fft_size=fft_size,
                        dc_removal=dc_removal, representation="db")


def _measure_thd(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    """Compute THD (Total Harmonic Distortion) as a ratio (0-1).

    Kwargs: fundamental (Hz), max_harmonics, window, fft_size, dc_removal.
    """
    fundamental = kwargs.pop("fundamental", None)
    if fundamental is not None:
        fundamental = float(fundamental)
    max_harmonics = int(kwargs.pop("max_harmonics", "10"))
    freq, mag = _compute_spectrum(x, y, kwargs)
    return _fft_thd(freq, mag, fundamental, max_harmonics)


def _measure_sinad(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    """Compute SINAD in dBc (positive = better).

    Kwargs: fundamental (Hz), max_harmonics, window, fft_size, dc_removal.
    """
    fundamental = kwargs.pop("fundamental", None)
    if fundamental is not None:
        fundamental = float(fundamental)
    max_harmonics = int(kwargs.pop("max_harmonics", "10"))
    freq, mag = _compute_spectrum(x, y, kwargs)
    return _fft_sinad(freq, mag, fundamental, max_harmonics)


def _measure_snr(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    """Compute SNR in dBc (positive = better).

    Kwargs: fundamental (Hz), max_harmonics, window, fft_size, dc_removal.
    """
    fundamental = kwargs.pop("fundamental", None)
    if fundamental is not None:
        fundamental = float(fundamental)
    max_harmonics = int(kwargs.pop("max_harmonics", "10"))
    freq, mag = _compute_spectrum(x, y, kwargs)
    return _fft_snr(freq, mag, fundamental, max_harmonics)


def _measure_sfdr(x: np.ndarray, y: np.ndarray, kwargs: dict) -> float:
    """Compute SFDR in dBc (positive = better).

    Kwargs: fundamental (Hz), window, fft_size, dc_removal.
    """
    fundamental = kwargs.pop("fundamental", None)
    if fundamental is not None:
        fundamental = float(fundamental)
    freq, mag = _compute_spectrum(x, y, kwargs)
    return _fft_sfdr(freq, mag, fundamental)


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

    # Apply TD, FROM/TO windowing before finding crossing
    if "td" in kwargs:
        cond_x, cond_y = _apply_td(cond_x, cond_y, {"td": kwargs.pop("td")})
    if "from" in kwargs or "to" in kwargs:
        cond_x, cond_y = _window_data(cond_x, cond_y, kwargs)

    crossings, idx = _find_crossing_index(cond_x, cond_y, threshold, kwargs)
    return float(np.interp(crossings[idx], find_x, find_y))


def _measure_find_when_eq(
    find_vector: str,
    positional: list[str],
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    _evaluate_fn: Callable,
) -> float:
    """Evaluate FIND v(out) WHEN v(1)=v(2) → value of v(out) when vectors cross."""
    if len(positional) < 2:
        raise ValueError("find_when_eq requires var1 and var2")

    var1 = positional[0]
    var2 = positional[1]

    result = get_data(find_vector)
    if result is None:
        raise ValueError(f"Vector not found: {find_vector!r}")
    find_x, find_y = result

    result1 = get_data(var1)
    result2 = get_data(var2)
    if result1 is None:
        raise ValueError(f"Vector not found: {var1!r}")
    if result2 is None:
        raise ValueError(f"Vector not found: {var2!r}")

    cond_x, y1 = result1
    _, y2 = result2
    diff = y1 - y2

    # Apply TD, FROM/TO
    if "td" in kwargs:
        cond_x, diff = _apply_td(cond_x, diff, {"td": kwargs.pop("td")})
    if "from" in kwargs or "to" in kwargs:
        cond_x, diff = _window_data(cond_x, diff, kwargs)

    crossings, idx = _find_crossing_index(cond_x, diff, 0.0, kwargs)
    return float(np.interp(crossings[idx], find_x, find_y))


def _measure_deriv_when(
    deriv_vector: str,
    positional: list[str],
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    evaluate_fn: Callable,
) -> float:
    """Evaluate DERIV v(out) WHEN v(1)=val [rise=1 ...] → derivative at crossing."""
    if len(positional) < 2:
        raise ValueError("deriv_when requires condition_vector and threshold")

    cond_vector = positional[0]
    threshold_str = positional[1]

    result = get_data(deriv_vector)
    if result is None:
        raise ValueError(f"Vector not found: {deriv_vector!r}")
    deriv_x, deriv_y = result

    result = get_data(cond_vector)
    if result is None:
        raise ValueError(f"Vector not found: {cond_vector!r}")
    cond_x, cond_y = result

    try:
        threshold = evaluate_fn(threshold_str, get_data)
    except Exception:
        threshold = _parse_value(threshold_str)

    if "td" in kwargs:
        cond_x, cond_y = _apply_td(cond_x, cond_y, {"td": kwargs.pop("td")})
    if "from" in kwargs or "to" in kwargs:
        cond_x, cond_y = _window_data(cond_x, cond_y, kwargs)

    crossings, idx = _find_crossing_index(cond_x, cond_y, threshold, kwargs)
    t = crossings[idx]

    # Numeric derivative at time t
    di = np.searchsorted(deriv_x, t)
    di = max(1, min(di, len(deriv_x) - 2))
    return float((deriv_y[di + 1] - deriv_y[di - 1]) / (deriv_x[di + 1] - deriv_x[di - 1]))


def _measure_deriv_when_eq(
    deriv_vector: str,
    positional: list[str],
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    _evaluate_fn: Callable,
) -> float:
    """Evaluate DERIV v(out) WHEN v(1)=v(2) → derivative at vector crossing."""
    if len(positional) < 2:
        raise ValueError("deriv_when_eq requires var1 and var2")

    var1 = positional[0]
    var2 = positional[1]

    result = get_data(deriv_vector)
    if result is None:
        raise ValueError(f"Vector not found: {deriv_vector!r}")
    deriv_x, deriv_y = result

    result1 = get_data(var1)
    result2 = get_data(var2)
    if result1 is None:
        raise ValueError(f"Vector not found: {var1!r}")
    if result2 is None:
        raise ValueError(f"Vector not found: {var2!r}")

    cond_x, y1 = result1
    _, y2 = result2
    diff = y1 - y2

    if "td" in kwargs:
        cond_x, diff = _apply_td(cond_x, diff, {"td": kwargs.pop("td")})
    if "from" in kwargs or "to" in kwargs:
        cond_x, diff = _window_data(cond_x, diff, kwargs)

    crossings, idx = _find_crossing_index(cond_x, diff, 0.0, kwargs)
    t = crossings[idx]

    di = np.searchsorted(deriv_x, t)
    di = max(1, min(di, len(deriv_x) - 2))
    return float((deriv_y[di + 1] - deriv_y[di - 1]) / (deriv_x[di + 1] - deriv_x[di - 1]))


def _measure_trig_targ(
    vector_name: str,
    positional: list[str],
    kwargs: dict[str, str],
    get_data: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    _evaluate_fn: Callable,
) -> float:
    """Evaluate TRIG ... TARG ... → distance along abscissa between two trigger points.

    If a function keyword is present (avg/min/max/pp/rms/integ), evaluate it
    over the [t_trig, t_targ] interval instead.

    vector_name is unused for plain TRIG/TARG (distance); populated for
    function+TRIG/TARG variants.
    """
    t_trig = _find_trigger_point(kwargs, get_data, prefix="trig_")
    t_targ = _find_trigger_point(kwargs, get_data, prefix="targ_")

    # Check if function keyword was preserved
    func_name = kwargs.pop("_func", None)
    if func_name:
        result = get_data(vector_name)
        if result is None:
            raise ValueError(f"Vector not found: {vector_name!r}")
        x_data, y_data = result
        t_lo, t_hi = min(t_trig, t_targ), max(t_trig, t_targ)
        mask = (x_data >= t_lo) & (x_data <= t_hi)
        if not np.any(mask):
            raise ValueError(f"No data points in range [{t_lo}, {t_hi}]")
        x_win, y_win = x_data[mask], y_data[mask]
        impl = _IMPLS.get(func_name)
        if impl is None:
            raise ValueError(f"Unknown function: {func_name!r}")
        return impl(x_win, y_win, kwargs)
    else:
        return float(t_targ - t_trig)


_SPECIAL: frozenset[str] = frozenset({
    "find_when", "find_when_eq", "when_eq",
    "deriv_when", "deriv_when_eq", "trig_targ",
})

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
    "find_when_eq": _measure_find_when_eq,
    "when_cross": _measure_when_cross,
    "when_eq": _measure_when_eq,
    "deriv_at": _measure_deriv_at,
    "deriv_when": _measure_deriv_when,
    "deriv_when_eq": _measure_deriv_when_eq,
    "trig_targ": _measure_trig_targ,
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

    if func_name in _SPECIAL:
        return impl(vector_name, positional, kwargs, get_data, evaluate_measure)

    result = get_data(vector_name)
    if result is None:
        raise ValueError(f"Vector not found: {vector_name!r}")
    x_data, y_data = result

    # Apply TD delay
    if "td" in kwargs:
        x_data, y_data = _apply_td(x_data, y_data, kwargs)

    if "from" in kwargs or "to" in kwargs:
        x_data, y_data = _window_data(x_data, y_data, kwargs)

    if func_name in ("find_at", "when_cross", "deriv_at"):
        return impl(x_data, y_data, kwargs, positional)
    return impl(x_data, y_data, kwargs)
