#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Measure function metadata registry for the Run Measure feature.

Provides a structured catalog of all built-in measurement functions with
signatures, descriptions, and categories. Used by MeasuresCombo and
MeasuresHelpDialog. Imports FunctionInfo from function_registry.
"""

from pqwave.ui.function_registry import FunctionInfo


_MEASURE_FUNCTIONS: list[FunctionInfo] = [
    # ---- Statistical ----
    FunctionInfo("min", "min(x)", "Minimum value of the waveform", "Statistical", 1),
    FunctionInfo("max", "max(x)", "Maximum value of the waveform", "Statistical", 1),
    FunctionInfo("avg", "avg(x)", "Arithmetic mean over the interval", "Statistical", 1),
    FunctionInfo("rms", "rms(x)", "Root-mean-square value over the interval", "Statistical", 1),
    FunctionInfo("pp", "pp(x)", "Peak-to-peak value: max(x) - min(x)", "Statistical", 1),
    FunctionInfo("integ", "integ(x)", "Numerical integral (area under curve)", "Statistical", 1),
    FunctionInfo("min_at", "min_at(x)", "X-axis value where the minimum occurs", "Statistical", 1),
    FunctionInfo("max_at", "max_at(x)", "X-axis value where the maximum occurs", "Statistical", 1),

    # ---- Timing ----
    FunctionInfo("rise_time", "rise_time(x)", "10% to 90% rise time", "Timing", 1),
    FunctionInfo("fall_time", "fall_time(x)", "90% to 10% fall time", "Timing", 1),
    FunctionInfo("period", "period(x)", "Time between consecutive like-directed threshold crossings", "Timing", 1),
    FunctionInfo("frequency", "frequency(x)", "1 / period(x)", "Timing", 1),
    FunctionInfo("duty_cycle", "duty_cycle(x)", "Pulse width divided by period, as a percentage (0-100)", "Timing", 1),
    FunctionInfo("pulse_width", "pulse_width(x)", "Width of a single pulse at threshold level", "Timing", 1),
    FunctionInfo("settling_time", "settling_time(x)", "Time to settle within settle_frac of final value", "Timing", 1),
    FunctionInfo("slew_rate", "slew_rate(x)", "Maximum absolute derivative in the measurement window", "Timing", 1),

    # ---- Overshoot ----
    FunctionInfo("overshoot", "overshoot(x)", "Overshoot as a percentage: (peak - settled) / settled * 100", "Overshoot", 1),
    FunctionInfo("undershoot", "undershoot(x)", "Undershoot as a percentage: (settled - trough) / settled * 100", "Overshoot", 1),

    # ---- SPICE Primitives ----
    FunctionInfo("find_at", "find_at(x, x_pos)", "Value of x at a specific x-axis coordinate", "SPICE Primitives", 2),
    FunctionInfo("when_cross", "when_cross(x, val)", "X-axis value where x crosses val", "SPICE Primitives", 2),
    FunctionInfo("deriv_at", "deriv_at(x, x_pos)", "Derivative at a specific x-axis coordinate", "SPICE Primitives", 2),
    FunctionInfo("find_when", "find_when(expr, cond, val)", "Value of expr when cond crosses val", "SPICE Primitives", 3),
    FunctionInfo("find_when_eq", "find_when_eq(expr, var1, var2)", "Value of expr when var1 equals var2", "SPICE Primitives", 3),
    FunctionInfo("when_eq", "when_eq(var1, var2)", "X-axis point where var1 equals var2", "SPICE Primitives", 2),
    FunctionInfo("deriv_when", "deriv_when(expr, var, val)", "Derivative when signal crosses threshold", "SPICE Primitives", 3),
    FunctionInfo("deriv_when_eq", "deriv_when_eq(expr, var1, var2)", "Derivative when two vectors are equal", "SPICE Primitives", 3),
    FunctionInfo("trig_targ", "trig_targ(vector, _func=..., trig_..., targ_...)", "Distance or function between trigger and target points", "SPICE Primitives", 0),

    # ---- Spectrum (deferred, requires FFT) ----
    FunctionInfo("thd", "thd(x)", "Total harmonic distortion (%) — requires FFT", "Spectrum", 1),
    FunctionInfo("sinad", "sinad(x)", "Signal-to-noise and distortion ratio (dB) — requires FFT", "Spectrum", 1),
    FunctionInfo("snr", "snr(x)", "Signal-to-noise ratio (dB) — requires FFT", "Spectrum", 1),
    FunctionInfo("sfdr", "sfdr(x)", "Spurious-free dynamic range (dB) — requires FFT", "Spectrum", 1),
]


def get_all_measure_functions() -> list[FunctionInfo]:
    """Return all measure functions."""
    return list(_MEASURE_FUNCTIONS)


def get_measure_functions_by_category() -> dict[str, list[FunctionInfo]]:
    """Return measure functions grouped by category."""
    result: dict[str, list[FunctionInfo]] = {}
    for info in _MEASURE_FUNCTIONS:
        result.setdefault(info.category, []).append(info)
    return result


def lookup_measure(name: str) -> FunctionInfo | None:
    """Look up a measure function by name."""
    name_lower = name.lower()
    for info in _MEASURE_FUNCTIONS:
        if info.name == name_lower:
            return info
    return None
