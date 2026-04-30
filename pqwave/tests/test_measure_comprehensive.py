#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Comprehensive test suite for SPICE .meas script parsing and measurement evaluation.

Covers:
  - LTspice .meas syntax (FIND AT, FIND WHEN, WHEN, DERIV, PARAM, AVG/MAX/MIN/
    PP/RMS/INTEG with TRIG/TARG, TD, RISE/FALL/CROSS=count|LAST)
  - ngspice extended forms (SP/TF/NOISE analysis types, MIN_AT/MAX_AT, FROM/TO,
    par() expressions, DERIVATIVE in AT/WHEN/interval variants)
  - pqwave internal function-call syntax
  - Synthetic data (sine, square, ramp) for deterministic numeric verification
  - Real bridge.raw transient data for end-to-end validation
"""

from __future__ import annotations

import math
import os
import re
import sys

import numpy as np
import pytest

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pqwave.measure.measure_script_parser import parse_meas_script
from pqwave.measure.measure_engine import evaluate_measure


# ============================================================================
# Synthetic data helpers
# ============================================================================

def _sine_data(n: int = 1000, freq: float = 1.0, amp: float = 5.0,
               offset: float = 0.0, t_stop: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a sine wave: y = offset + amp * sin(2*pi*freq*t)."""
    t = np.linspace(0, t_stop, n)
    y = offset + amp * np.sin(2 * math.pi * freq * t)
    return t, y


def _square_data(n: int = 1000, freq: float = 1.0, amp: float = 5.0,
                 offset: float = 0.0, t_stop: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a square wave: y = offset + amp * sign(sin(2*pi*freq*t))."""
    t = np.linspace(0, t_stop, n)
    y = offset + amp * np.where(np.sin(2 * math.pi * freq * t) > 0, 1.0, -1.0)
    return t, y


def _ramp_data(n: int = 1000, slope: float = 1.0, t_stop: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a ramp: y = slope * t."""
    t = np.linspace(0, t_stop, n)
    y = slope * t
    return t, y


_EXPR_CHARS_FOR_TEST = set('+-*/^%&|=!<>, ')


def _eval_expr_on_vectors(
    expr: str, vectors: dict[str, tuple[np.ndarray, np.ndarray]]
) -> tuple[np.ndarray, np.ndarray] | None:
    """Try to evaluate an expression like v(out)*i(vout) using vector data."""
    pattern = re.compile(r'([a-zA-Z_]\w*)\s*\(([^)]+)\)')
    matches = list(pattern.finditer(expr))
    if not matches:
        return None

    var_map: dict[str, str] = {}
    x_data = None
    parts: list[str] = []
    last_end = 0

    for i, m in enumerate(matches):
        prefix = m.group(1)
        name = m.group(2)
        key = f"{prefix}({name})".lower()
        vec = vectors.get(key)
        if vec is None:
            return None
        var_name = f"_v{i}"
        var_map[var_name] = key
        if x_data is None:
            x_data = vec[0]
        parts.append(expr[last_end:m.start()])
        parts.append(var_name)
        last_end = m.end()
    parts.append(expr[last_end:])
    eval_expr = ''.join(parts)

    namespace = {vn: vectors[vk][1] for vn, vk in var_map.items()}
    try:
        y_data = eval(eval_expr, {"__builtins__": {}}, {"np": np, **namespace})
        y_arr = np.asarray(y_data)
        if x_data is None:
            x_data = np.arange(len(y_arr))
        return x_data, y_arr
    except Exception:
        return None


def _make_get_data(vectors: dict[str, tuple[np.ndarray, np.ndarray]]):
    """Return a get_data callable that looks up vectors by name from a dict.

    Falls back to simple expression evaluation when the name contains
    expression characters (operators, commas, spaces) and the literal
    lookup fails — matching production behaviour in _measure_get_data.
    """
    def get_data(name: str) -> tuple[np.ndarray, np.ndarray] | None:
        result = vectors.get(name.lower())
        if result is not None:
            return result
        if any(c in _EXPR_CHARS_FOR_TEST for c in name):
            return _eval_expr_on_vectors(name, vectors)
        return None
    return get_data


# ============================================================================
# Part 1: Script Parser Tests (parse_meas_script)
# ============================================================================

class TestParserFindAt:
    """FIND <expr> AT=<value> — point measurement at a specific x-coordinate."""

    def test_find_at_basic(self):
        results = parse_meas_script(".meas tran res1 FIND v(out) AT=5m")
        assert len(results) == 1
        assert results[0] == ("find_at(v(out), 5m)", "res1")

    def test_find_at_expression(self):
        results = parse_meas_script(".meas tran res2 FIND v(out)*i(vout) AT=10u")
        assert len(results) == 1
        assert results[0] == ("find_at(v(out)*i(vout), 10u)", "res2")

    def test_find_at_no_varname(self):
        results = parse_meas_script(".meas tran FIND v(out) AT=5m")
        assert len(results) == 1
        assert results[0] == ("find_at(v(out), 5m)", "")

    def test_find_at_ac_analysis(self):
        results = parse_meas_script(".meas AC res3 FIND v(out) AT=1k")
        assert len(results) == 1
        assert results[0][0] == "find_at(v(out), 1k)"
        assert results[0][1] == "res3"


class TestParserFindWhen:
    """FIND <expr> WHEN <cond>=<val> — point measurement when a condition is met."""

    def test_find_when_basic(self):
        results = parse_meas_script(".meas tran res2 FIND v(out) WHEN v(x)=3*v(y)")
        assert len(results) == 1
        assert results[0] == ("find_when(v(out), v(x), 3*v(y))", "res2")

    def test_find_when_with_cross(self):
        results = parse_meas_script(
            ".meas tran res3 FIND v(out) WHEN v(x)=3*v(y) cross=3"
        )
        assert len(results) == 1
        expr = results[0][0]
        assert expr.startswith("find_when(v(out), v(x), 3*v(y)")

    def test_find_when_rise_last(self):
        results = parse_meas_script(
            ".meas tran res4 FIND v(out) WHEN v(x)=3*v(y) rise=last"
        )
        assert len(results) == 1
        expr = results[0][0]
        assert "find_when" in expr

    def test_find_when_with_td(self):
        results = parse_meas_script(
            ".meas tran res5 FIND v(out) WHEN v(x)=3*v(y) cross=3 TD=1m"
        )
        assert len(results) == 1
        expr = results[0][0]
        assert "TD=1m" in expr or "td=1m" in expr.lower()


class TestParserWhen:
    """WHEN <cond>=<val> — find the x-coordinate where a condition is met."""

    def test_when_basic(self):
        results = parse_meas_script(".meas tran res6 WHEN v(x)=3*v(y)")
        assert len(results) == 1
        assert results[0] == ("when_cross(v(x), 3*v(y))", "res6")

    def test_when_with_rise(self):
        results = parse_meas_script(
            ".meas tran res7 WHEN v(x)=3*v(y) rise=2"
        )
        assert len(results) == 1
        expr = results[0][0]
        assert "when_cross" in expr
        assert "rise=2" in expr

    def test_when_with_fall_last(self):
        results = parse_meas_script(
            ".meas tran res8 WHEN v(x)=3*v(y) fall=last"
        )
        assert len(results) == 1
        expr = results[0][0]
        assert "when_cross" in expr

    def test_when_with_cross_and_td(self):
        results = parse_meas_script(
            ".meas tran res9 WHEN v(x)=3*v(y) cross=5 TD=1m"
        )
        assert len(results) == 1
        expr = results[0][0]
        assert "when_cross" in expr


class TestParserDeriv:
    """DERIV <expr> AT=<value> — derivative at a specific point."""

    def test_deriv_at_basic(self):
        results = parse_meas_script(".meas tran res10 DERIV v(out) AT=1m")
        assert len(results) == 1
        assert results[0] == ("deriv_at(v(out), 1m)", "res10")


class TestParserParam:
    """PARAM <expression> — evaluate arithmetic on other .meas results."""

    def test_param_expression(self):
        results = parse_meas_script(".meas tran res11 PARAM 3*res1/res2")
        assert len(results) == 1
        assert results[0] == ("3*res1/res2", "res11")


class TestParserRangeMeasurements:
    """AVG/MAX/MIN/PP/RMS/INTEG with optional TRIG/TARG and FROM/TO."""

    def test_avg_simple(self):
        results = parse_meas_script(".meas tran res12 AVG v(out)")
        assert len(results) == 1
        assert results[0] == ("avg(v(out))", "res12")

    def test_max_simple(self):
        results = parse_meas_script(".meas tran res_max MAX v(out)")
        assert len(results) == 1
        assert results[0] == ("max(v(out))", "res_max")

    def test_min_simple(self):
        results = parse_meas_script(".meas tran res_min MIN v(out)")
        assert len(results) == 1
        assert results[0] == ("min(v(out))", "res_min")

    def test_pp_simple(self):
        results = parse_meas_script(".meas tran res_pp PP v(out)")
        assert len(results) == 1
        assert results[0] == ("pp(v(out))", "res_pp")

    def test_rms_simple(self):
        results = parse_meas_script(".meas tran res_rms RMS v(out)")
        assert len(results) == 1
        assert results[0] == ("rms(v(out))", "res_rms")

    def test_integ_simple(self):
        results = parse_meas_script(".meas tran res_integ INTEG v(out)")
        assert len(results) == 1
        assert results[0] == ("integ(v(out))", "res_integ")

    def test_avg_with_from_to(self):
        results = parse_meas_script(
            ".meas tran res13 AVG v(out) from=0 to=10m"
        )
        assert len(results) == 1
        assert results[0] == ("avg(v(out), from=0, to=10m)", "res13")

    def test_rms_with_from_to(self):
        results = parse_meas_script(
            ".meas tran res14 RMS v(out) from=0 to=10m"
        )
        assert len(results) == 1
        assert results[0] == ("rms(v(out), from=0, to=10m)", "res14")

    def test_integ_with_from_to(self):
        results = parse_meas_script(
            ".meas tran res15 INTEG v(out) from=0 to=10m"
        )
        assert len(results) == 1
        assert results[0] == ("integ(v(out), from=0, to=10m)", "res15")

    def test_avg_with_trig_targ(self):
        results = parse_meas_script(
            ".meas tran res7 AVG V(NS01) "
            "TRIG V(NS05) VAL=1.5 TD=1.1u FALL=1 "
            "TARG V(NS03) VAL=1.5 TD=1.1u FALL=1"
        )
        assert len(results) == 1
        assert results[0][1] == "res7"


class TestParserNgspiceForms:
    """ngspice-specific syntax variants."""

    def test_sp_analysis(self):
        results = parse_meas_script(".meas SP res_s11 FIND S(1,1) AT=1GHz")
        assert len(results) == 1
        assert results[0][1] == "res_s11"

    def test_tf_analysis(self):
        results = parse_meas_script(".meas TF res_gain FIND v(out) AT=1k")
        assert len(results) == 1
        assert results[0][1] == "res_gain"

    def test_noise_analysis(self):
        results = parse_meas_script(".meas NOISE out_totn INTEG V(onoise)")
        assert len(results) == 1
        assert results[0] == ("integ(v(onoise))", "out_totn")

    def test_dc_analysis(self):
        results = parse_meas_script(".meas DC res_dc FIND v(out) AT=5")
        assert len(results) == 1
        assert results[0][1] == "res_dc"

    def test_min_at_basic(self):
        results = parse_meas_script(".meas tran res16 MIN_AT v(out)")
        assert len(results) == 1
        assert results[0][0] == "min_at(v(out))"

    def test_max_at_basic(self):
        results = parse_meas_script(".meas tran res17 MAX_AT v(out)")
        assert len(results) == 1
        assert results[0][0] == "max_at(v(out))"

    def test_rise_time(self):
        results = parse_meas_script(".meas tran res18 RISE_TIME v(out)")
        assert len(results) == 1
        assert results[0][0] == "rise_time(v(out))"

    def test_fall_time(self):
        results = parse_meas_script(".meas tran res19 FALL_TIME v(out)")
        assert len(results) == 1
        assert results[0][0] == "fall_time(v(out))"

    def test_period(self):
        results = parse_meas_script(".meas tran res20 PERIOD v(out)")
        assert len(results) == 1
        assert results[0][0] == "period(v(out))"

    def test_frequency(self):
        results = parse_meas_script(".meas tran res21 FREQUENCY v(out)")
        assert len(results) == 1
        assert results[0][0] == "frequency(v(out))"

    def test_duty_cycle(self):
        results = parse_meas_script(".meas tran res22 DUTY_CYCLE v(out)")
        assert len(results) == 1
        assert results[0][0] == "duty_cycle(v(out))"

    def test_pulse_width(self):
        results = parse_meas_script(".meas tran res23 PULSE_WIDTH v(out)")
        assert len(results) == 1
        assert results[0][0] == "pulse_width(v(out))"

    def test_settling_time(self):
        results = parse_meas_script(".meas tran res24 SETTLING_TIME v(out)")
        assert len(results) == 1
        assert results[0][0] == "settling_time(v(out))"

    def test_slew_rate(self):
        results = parse_meas_script(".meas tran res25 SLEW_RATE v(out)")
        assert len(results) == 1
        assert results[0][0] == "slew_rate(v(out))"

    def test_comments_ignored(self):
        results = parse_meas_script("* This is a comment\n.meas tran res26 AVG v(out)")
        assert len(results) == 1
        assert results[0] == ("avg(v(out))", "res26")

    def test_multiple_statements(self):
        script = (
            ".meas tran a AVG v(out)\n"
            ".meas tran b MAX v(out)\n"
            ".meas tran c MIN v(out)"
        )
        results = parse_meas_script(script)
        assert len(results) == 3
        assert results[0] == ("avg(v(out))", "a")
        assert results[1] == ("max(v(out))", "b")
        assert results[2] == ("min(v(out))", "c")


class TestParserEdgeCases:
    """Edge cases for the script parser."""

    def test_case_insensitive(self):
        results = parse_meas_script(".meas TRAN RES Avg V(out)")
        assert len(results) == 1
        assert results[0] == ("avg(v(out))", "res")

    def test_whitespace_handling(self):
        results = parse_meas_script("  .meas   tran   res    FIND   v(out)   AT=5m  ")
        assert len(results) == 1
        assert results[0] == ("find_at(v(out), 5m)", "res")

    def test_vector_with_parens(self):
        results = parse_meas_script(
            ".meas tran res28 FIND v(ac_p)-v(ac_n) AT=5m"
        )
        assert len(results) == 1
        assert results[0][0] == "find_at(v(ac_p)-v(ac_n), 5m)"

    def test_metric_suffixes_in_script(self):
        results = parse_meas_script(".meas tran res29 FIND v(out) AT=1.5k")
        assert len(results) == 1
        assert results[0][0] == "find_at(v(out), 1.5k)"

    def test_direct_function_call(self):
        results = parse_meas_script("avg(v(out), from=0, to=10m)")
        assert len(results) == 1
        assert results[0] == ("avg(v(out), from=0, to=10m)", "")


class TestParserContinuations:
    """Multi-line .meas statements with '+' continuation lines."""

    def test_trig_targ_single_continuation(self):
        script = (
            ".meas tran inv_delay trig v(in) val='vp/2' td=1n fall=1\n"
            "+ targ v(out) val='vp/2' rise=1"
        )
        results = parse_meas_script(script)
        assert len(results) == 1, f"Expected 1, got {len(results)}: {results}"
        assert results[0][1] == "inv_delay"
        assert results[0][0].startswith("trig_targ(v(in)")

    def test_trig_targ_multiple_continuations(self):
        script = (
            ".meas tran res7 AVG V(NS01)\n"
            "+ TRIG V(NS05) VAL=1.5 TD=1.1u FALL=1\n"
            "+ TARG V(NS03) VAL=1.5 TD=1.1u FALL=1"
        )
        results = parse_meas_script(script)
        assert len(results) == 1, f"Expected 1, got {len(results)}: {results}"
        assert results[0][1] == "res7"

    def test_mixed_with_and_without_continuations(self):
        script = (
            ".meas tran a avg v(r1)\n"
            ".meas tran b trig v(in) val=0.5 rise=1\n"
            "+ targ v(out) val=0.5 rise=2\n"
            ".meas tran c max v(r1)"
        )
        results = parse_meas_script(script)
        assert len(results) == 3, f"Expected 3, got {len(results)}: {results}"
        # First result is standalone
        assert results[0][1] == "a"
        # Second is the joined trig/targ
        assert results[1][1] == "b"
        assert "trig_targ" in results[1][0]
        # Third is standalone
        assert results[2][1] == "c"

    def test_continuation_with_leading_whitespace(self):
        script = (
            ".meas tran bw trig v(out)=tmp/sqrt(2) rise=1\n"
            "  +  targ v(out)=tmp/sqrt(2) fall=last"
        )
        results = parse_meas_script(script)
        assert len(results) == 1, f"Expected 1, got {len(results)}: {results}"
        assert results[0][1] == "bw"

    def test_slew_rate_with_continuation(self):
        script = (
            ".meas tran out_slew trig v(out) val='0.2*vp' rise=2\n"
            "+ targ v(out) val='0.8*vp' rise=2"
        )
        results = parse_meas_script(script)
        assert len(results) == 1
        assert results[0][1] == "out_slew"

    def test_three_continuation_lines(self):
        script = (
            ".meas tran tdiff TRIG v(1) VAL=0.5 RISE=1\n"
            "+ TARG v(1) VAL=0.5 RISE=2"
        )
        results = parse_meas_script(script)
        assert len(results) == 1
        assert results[0][1] == "tdiff"

    def test_continuation_ac_analysis(self):
        script = (
            ".meas ac vout_diff trig v(out) val=0.1 rise=1\n"
            "+ targ v(out) val=0.1 fall=1"
        )
        results = parse_meas_script(script)
        assert len(results) == 1
        assert results[0][1] == "vout_diff"

    def test_continuation_bw_measurement(self):
        script = (
            ".meas ac bw trig v(out)=tmp/sqrt(2) rise=1\n"
            "+ targ v(out)=tmp/sqrt(2) fall=last"
        )
        results = parse_meas_script(script)
        assert len(results) == 1
        assert results[0][1] == "bw"

    def test_continuation_no_varname(self):
        script = (
            ".meas tran trig v(in) val='vp/2' rise=1\n"
            "+ targ v(out) val='vp/2' fall=1"
        )
        results = parse_meas_script(script)
        assert len(results) == 1
        assert results[0][1] == ""
        assert "trig_targ" in results[0][0]


class TestParserParExpression:
    """par('expression') unwrapping — ngspice syntax for algebraic expressions."""

    def test_par_find_at(self):
        """FIND par('expr') AT=val → find_at(expr, val)."""
        script = ".meas tran vtest find par('(v(2)*v(1)') at=2.3m"
        results = parse_meas_script(script)
        assert len(results) == 1
        assert results[0][1] == "vtest"
        assert "find_at((v(2)*v(1)" in results[0][0]

    def test_par_find_at_double_quotes(self):
        """FIND par(\"expr\") AT=val."""
        script = '.meas tran res1 find par("v(out)") at=5m'
        results = parse_meas_script(script)
        assert results[0][1] == "res1"
        assert results[0][0] == "find_at(v(out), 5m)"

    def test_par_find_when(self):
        """FIND par('expr') WHEN cond=val."""
        script = ".meas tran result find par('v(out)*i(vout)') when v(x)=3*v(y)"
        results = parse_meas_script(script)
        assert results[0][1] == "result"
        assert results[0][0] == "find_when(v(out)*i(vout), v(x), 3*v(y))"

    def test_par_find_when_eq(self):
        """FIND par('expr') WHEN var1=var2 (vector equality)."""
        script = ".meas tran res2 find par('v(out)*i(vout)') when v(x)=v(y)"
        results = parse_meas_script(script)
        assert results[0][1] == "res2"
        assert results[0][0] == "find_when_eq(v(out)*i(vout), v(x), v(y))"

    def test_par_avg_range(self):
        """AVG par('expr') from=... to=..."""
        script = '.meas tran yavg avg par("v(1)+v(2)") from=2m to=4m'
        results = parse_meas_script(script)
        assert results[0][1] == "yavg"
        assert results[0][0] == "avg(v(1)+v(2), from=2m, to=4m)"

    def test_par_rms_range(self):
        """RMS par('expr') from=... to=..."""
        script = '.meas tran yrms rms par("v(1)*2") from=2m to=4m'
        results = parse_meas_script(script)
        assert results[0][1] == "yrms"
        assert results[0][0] == "rms(v(1)*2, from=2m, to=4m)"

    def test_par_deriv_at(self):
        """DERIV par('expr') AT=val."""
        script = '.meas tran dtest deriv par("v(out)+v(in)") at=10m'
        results = parse_meas_script(script)
        assert results[0][1] == "dtest"
        assert "deriv_at" in results[0][0]
        assert "v(out)+v(in)" in results[0][0]

    def test_par_trig_targ(self):
        """TRIG par('expr') ... TARG par('expr') ..."""
        script = (
            ".meas tran tdiff trig par('v(1)*2') val=0.5 rise=1 "
            "targ par('v(1)*2') val=0.5 rise=2"
        )
        results = parse_meas_script(script)
        assert results[0][0].startswith("trig_targ(v(1)*2")

    def test_par_param(self):
        """param='expression' (unchanged by par unwrapping)."""
        script = ".meas tran yadd param='fval + 7'"
        results = parse_meas_script(script)
        assert results[0][1] == "yadd"
        assert results[0][0] == "fval + 7"

    def test_par_param_double_quotes(self):
        """param=\"expression\" (unchanged by par unwrapping)."""
        script = '.meas tran bw_chk param="(tdiff < vout_diff) ? 1 : 0"'
        results = parse_meas_script(script)
        assert results[0][1] == "bw_chk"
        assert results[0][0] == "(tdiff < vout_diff) ? 1 : 0"


# ============================================================================
# Part 2: Engine Tests with Synthetic Data (evaluate_measure)
# ============================================================================

class TestEngineMinMax:
    """min() and max() on synthetic data."""

    def test_min_sine(self):
        t, y = _sine_data(amp=5.0, offset=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("min(v(out))", gd)
        assert result == pytest.approx(-4.0, abs=0.1)

    def test_max_sine(self):
        t, y = _sine_data(amp=5.0, offset=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("max(v(out))", gd)
        assert result == pytest.approx(6.0, abs=0.1)

    def test_pp(self):
        t, y = _sine_data(amp=5.0, offset=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("pp(v(out))", gd)
        assert result == pytest.approx(10.0, abs=0.2)


class TestEngineAvgRmsInteg:
    """avg(), rms(), integ() on synthetic data."""

    def test_avg_sine(self):
        t, y = _sine_data(amp=5.0, offset=2.0, n=10000, t_stop=10.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("avg(v(out))", gd)
        assert result == pytest.approx(2.0, abs=0.1)

    def test_rms_sine(self):
        t, y = _sine_data(amp=5.0, offset=0.0, n=10000, t_stop=10.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("rms(v(out))", gd)
        assert result == pytest.approx(5.0 / math.sqrt(2), abs=0.1)

    def test_integ_ramp(self):
        t, y = _ramp_data(slope=2.0, n=10000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("integ(v(out))", gd)
        assert result == pytest.approx(1.0, abs=0.01)


class TestEngineFindAt:
    """find_at() — interpolate y at a given x."""

    def test_find_at_ramp(self):
        t, y = _ramp_data(slope=3.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 0.5)", gd)
        assert result == pytest.approx(1.5, abs=0.01)

    def test_find_at_sine_peak(self):
        t, y = _sine_data(amp=5.0, offset=0.0, n=10000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 0.25)", gd)
        assert result == pytest.approx(5.0, abs=0.05)

    def test_find_at_sine_zero(self):
        t, y = _sine_data(amp=5.0, offset=0.0, n=10000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 0.5)", gd)
        assert result == pytest.approx(0.0, abs=0.05)


class TestEngineWhenCross:
    """when_cross() — find x where y crosses a threshold."""

    def test_when_cross_ramp(self):
        t, y = _ramp_data(slope=1.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("when_cross(v(out), 0.5)", gd)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_when_cross_sine_rise(self):
        t, y = _sine_data(amp=5.0, offset=0.0, n=10000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("when_cross(v(out), 0.0, rise=1)", gd)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_when_cross_sine_fall(self):
        t, y = _sine_data(amp=5.0, offset=0.0, n=10000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("when_cross(v(out), 0.0, fall=1)", gd)
        assert result == pytest.approx(0.5, abs=0.02)

    def test_when_cross_missing_uses_default(self):
        t, y = _ramp_data(slope=1.0, n=100)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("when_cross(v(out), 0.4)", gd)
        assert result == pytest.approx(0.4, abs=0.02)


class TestEngineDerivAt:
    """deriv_at() — numerical derivative at a point."""

    def test_deriv_at_ramp(self):
        t, y = _ramp_data(slope=3.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("deriv_at(v(out), 0.5)", gd)
        assert result == pytest.approx(3.0, abs=0.1)

    def test_deriv_at_sine_zero_crossing(self):
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("deriv_at(v(out), 0.0)", gd)
        expected = 2 * math.pi * 5.0  # d/dt of 5*sin(2*pi*t) at t=0
        assert result == pytest.approx(expected, abs=5.0)


class TestEngineWindow:
    """from=/to= windowing on measurements."""

    def test_avg_windowed(self):
        t, y = _ramp_data(slope=10.0, n=10000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("avg(v(out), from=0.2, to=0.5)", gd)
        assert result == pytest.approx(3.5, abs=0.1)

    def test_max_windowed(self):
        t, y = _ramp_data(slope=10.0, n=10000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("max(v(out), from=0.0, to=0.5)", gd)
        assert result == pytest.approx(5.0, abs=0.1)

    def test_min_windowed(self):
        t, y = _ramp_data(slope=10.0, n=10000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("min(v(out), from=0.3, to=0.7)", gd)
        assert result == pytest.approx(3.0, abs=0.1)

    def test_no_data_in_window_raises(self):
        t, y = _ramp_data(slope=1.0, n=100, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(ValueError, match="No data points in range"):
            evaluate_measure("avg(v(out), from=2.0, to=3.0)", gd)


class TestEngineRiseFallTime:
    """rise_time() and fall_time() on square wave data."""

    def test_rise_time_square(self):
        t, y = _square_data(amp=5.0, offset=0.0, n=100000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("rise_time(v(out))", gd)
        assert result < 0.001  # nearly instantaneous

    def test_fall_time_square(self):
        t, y = _square_data(amp=5.0, offset=0.0, n=100000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("fall_time(v(out))", gd)
        assert result < 0.001

    def test_rise_time_with_threshold(self):
        t, y = _square_data(amp=5.0, offset=0.0, n=100000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("rise_time(v(out), threshold=0)", gd)
        assert result > 0.0

    def test_rise_time_custom_pct(self):
        t, y = _square_data(amp=5.0, offset=0.0, n=100000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("rise_time(v(out), low_pct=20, high_pct=80)", gd)
        assert result < 0.001


class TestEnginePeriodFrequency:
    """period() and frequency() on periodic data."""

    def test_period_sine(self):
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1000.0, n=50000, t_stop=0.01)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("period(v(out))", gd)
        assert result == pytest.approx(0.001, abs=0.0001)

    def test_frequency_sine(self):
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1000.0, n=50000, t_stop=0.01)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("frequency(v(out))", gd)
        assert result == pytest.approx(1000.0, abs=10.0)

    def test_period_second_rise(self):
        t, y = _sine_data(amp=5.0, offset=0.0, freq=100.0, n=50000, t_stop=0.05)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("period(v(out), rise=2)", gd)
        assert result == pytest.approx(0.01, abs=0.0005)


class TestEngineDutyPulse:
    """duty_cycle() and pulse_width() on square wave."""

    def test_duty_cycle_square(self):
        t, y = _square_data(amp=5.0, offset=0.0, freq=100.0, n=50000, t_stop=0.05)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("duty_cycle(v(out))", gd)
        assert result == pytest.approx(50.0, abs=5.0)

    def test_pulse_width_square(self):
        t, y = _square_data(amp=5.0, offset=0.0, freq=100.0, n=50000, t_stop=0.02)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("pulse_width(v(out))", gd)
        assert result == pytest.approx(0.005, abs=0.001)


class TestEngineSettlingSlew:
    """settling_time() and slew_rate()."""

    def test_settling_time_ramp(self):
        t, y = _ramp_data(slope=1.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("settling_time(v(out))", gd)
        assert result >= 0.0

    def test_slew_rate_square(self):
        t, y = _square_data(amp=5.0, offset=0.0, n=100000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("slew_rate(v(out))", gd)
        assert result > 0.0

    def test_slew_rate_sine(self):
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("slew_rate(v(out))", gd)
        expected = 2 * math.pi * 5.0
        assert result == pytest.approx(expected, abs=2.0)


class TestEngineOvershoot:
    """overshoot() and undershoot()."""

    def test_overshoot_zero_for_ramp(self):
        t, y = _ramp_data(slope=1.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("overshoot(v(out))", gd)
        assert result == pytest.approx(0.0, abs=0.1)

    def test_undershoot_for_ramp(self):
        t, y = _ramp_data(slope=1.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("undershoot(v(out))", gd)
        assert result == pytest.approx(100.0, abs=0.1)

    def test_overshoot_final_val_zero(self):
        t, y = _sine_data(amp=5.0, offset=0.0, n=1000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("overshoot(v(out))", gd)
        assert result == 0.0  # final_val ≈ 0 → returns 0.0


class TestEngineFindWhen:
    """find_when() — value of one vector when another crosses a threshold."""

    def test_find_when_sine_at_sine_cross(self):
        t1, y1 = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=1.0)
        t2, y2 = _ramp_data(slope=10.0, n=10000)
        gd = _make_get_data({"v(a)": (t1, y1), "v(b)": (t2, y2)})
        result = evaluate_measure("find_when(v(b), v(a), 0.0)", gd)
        assert result == pytest.approx(0.0, abs=0.1)

    def test_find_when_with_rise(self):
        t1, y1 = _sine_data(amp=5.0, offset=2.0, freq=1.0, n=10000, t_stop=1.0)
        t2, y2 = _ramp_data(slope=1.0, n=10000)
        gd = _make_get_data({"v(sig)": (t1, y1), "v(ramp)": (t2, y2)})
        result = evaluate_measure("find_when(v(ramp), v(sig), 2.0, rise=1)", gd)
        assert result == pytest.approx(0.0, abs=0.02)

    def test_find_when_numeric_threshold(self):
        t1, y1 = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=1.0)
        t2, y2 = _ramp_data(slope=1.0, n=10000)
        gd = _make_get_data({"v(x)": (t1, y1), "v(y)": (t2, y2)})
        result = evaluate_measure("find_when(v(y), v(x), 4.0)", gd)
        assert 0.0 < result < 1.0

    def test_find_when_unknown_vector_raises(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(a)": (t, y)})
        with pytest.raises(ValueError, match="Vector not found"):
            evaluate_measure("find_when(v(b), v(a), 0)", gd)


class TestEngineErrorHandling:
    """Error handling in the measure engine."""

    def test_unknown_function_raises(self):
        t, y = _ramp_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(ValueError, match="Unknown measure function"):
            evaluate_measure("nonexistent(v(out))", gd)

    def test_unknown_vector_raises(self):
        t, y = _ramp_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(ValueError, match="Vector not found"):
            evaluate_measure("avg(v(missing))", gd)

    def test_invalid_expression_syntax(self):
        t, y = _ramp_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(ValueError, match="Invalid measure expression"):
            evaluate_measure("123invalid", gd)

    def test_unsupported_thd(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(NotImplementedError, match="thd"):
            evaluate_measure("thd(v(out))", gd)

    def test_unsupported_snr(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(NotImplementedError, match="snr"):
            evaluate_measure("snr(v(out))", gd)


class TestEngineMetricSuffix:
    """Metric suffix parsing in measure arguments."""

    def test_milli(self):
        t, y = _ramp_data(slope=1.0, n=1000, t_stop=1.0)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 500m)", gd)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_micro(self):
        t = np.linspace(0, 0.001, 10000)
        y = t * 1e6
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 500u)", gd)
        assert result == pytest.approx(500.0, abs=1.0)

    def test_nano(self):
        t = np.linspace(0, 1e-6, 10000)
        y = np.linspace(0, 1, 10000)
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 500n)", gd)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_kilo(self):
        t = np.linspace(0, 10000, 1000)
        y = t
        gd = _make_get_data({"v(out)": (t, y)})
        result = evaluate_measure("find_at(v(out), 1.5k)", gd)
        assert result == pytest.approx(1500.0, abs=1.0)


# ============================================================================
# Part 2b: Engine Tests for TRIG/TARG, when_eq, find_when_eq, deriv_when
# ============================================================================

class TestEngineTrigTarg:
    """trig_targ() — distance between two trigger points, optionally with function."""

    def test_trig_targ_standalone_distance(self):
        """TRIG at val on rising edge → TARG at val on next rising edge = period."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        result = evaluate_measure(
            "trig_targ(v(sig), trig_var=v(sig), trig_val=2.5, trig_rise=1,"
            " targ_var=v(sig), targ_val=2.5, targ_rise=2)",
            gd,
        )
        assert result == pytest.approx(1.0, abs=0.01)

    def test_trig_targ_fall_to_rise(self):
        """TRIG on falling edge (t≈0.417) → TARG on next rising edge (t≈1.083)."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        result = evaluate_measure(
            "trig_targ(v(sig), trig_var=v(sig), trig_val=2.5, trig_fall=1,"
            " targ_var=v(sig), targ_val=2.5, targ_rise=2)",
            gd,
        )
        # targ_rise=2 at t≈1.083, trig_fall=1 at t≈0.417, distance ≈ 0.667
        assert result == pytest.approx(0.667, abs=0.02)

    def test_trig_targ_with_trig_at(self):
        """TRIG at fixed time → TARG at crossing."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        result = evaluate_measure(
            "trig_targ(v(sig), trig_at=0.1, targ_var=v(sig), targ_val=2.5, targ_rise=1)",
            gd,
        )
        # First rising cross of 2.5V at ~0.083s, distance = 0.083 - 0.1 = -0.017
        assert -0.03 < result < 0.0

    def test_trig_targ_avg_function(self):
        """AVG v(sig) over TRIG/TARG interval."""
        t = np.linspace(0, 1, 10000)
        y = 2.0 * t  # ramp 0→2
        gd = _make_get_data({"v(ramp)": (t, y)})
        # AVG of y=2t from t=0.2 to t=0.8: (2*0.8²/2 - 2*0.2²/2) / 0.6
        # = (0.64 - 0.04) / 0.6 = 0.6 / 0.6 = 1.0
        result = evaluate_measure(
            "trig_targ(v(ramp), _func=avg, trig_at=0.2, targ_at=0.8)",
            gd,
        )
        assert result == pytest.approx(1.0, abs=0.01)

    def test_trig_targ_min_function(self):
        """MIN v(sig) over TRIG/TARG interval."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        # Window from 0 to 0.5: min of 5*sin(2*pi*t) in [0,0.5] is 0 at t=0
        result = evaluate_measure(
            "trig_targ(v(sig), _func=min, trig_at=0.0, targ_at=0.5)",
            gd,
        )
        assert result < 0.1

    def test_trig_targ_max_function(self):
        """MAX v(sig) over TRIG/TARG interval."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        # Window from 0 to 0.5: max is at t=0.25 where sin(pi/2)=1 → y=5
        result = evaluate_measure(
            "trig_targ(v(sig), _func=max, trig_at=0.0, targ_at=0.5)",
            gd,
        )
        assert result == pytest.approx(5.0, abs=0.01)

    def test_trig_targ_no_data_raises(self):
        """TRIG/TARG range with no data points raises ValueError."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=100, t_stop=1.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        with pytest.raises(ValueError, match="No data points"):
            evaluate_measure(
                "trig_targ(v(sig), _func=avg, trig_at=10.0, targ_at=11.0)",
                gd,
            )

    def test_trig_targ_targ_edge_constraints(self):
        """TARG with rise= constraint is respected (not silently ignored)."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        # TRIG at rise=1 (t≈0.083), TARG at rise=2 (t≈1.083)
        # Distance = 1 period ≈ 1.0 second
        result = evaluate_measure(
            "trig_targ(v(sig), trig_var=v(sig), trig_val=2.5, trig_rise=1,"
            " targ_var=v(sig), targ_val=2.5, targ_rise=2)",
            gd,
        )
        assert result == pytest.approx(1.0, abs=0.02)

    def test_trig_targ_with_cross(self):
        """TRIG/TARG with cross= (any edge) works."""
        t, y = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        gd = _make_get_data({"v(sig)": (t, y)})
        result = evaluate_measure(
            "trig_targ(v(sig), trig_var=v(sig), trig_val=2.5, trig_cross=1,"
            " targ_var=v(sig), targ_val=2.5, targ_cross=2)",
            gd,
        )
        # cross=1 is first crossing (rising at ~0.083)
        # cross=2 is second crossing (falling at ~0.417)
        # distance = 0.417 - 0.083 ≈ 0.333
        assert 0.25 < result < 0.4


class TestEngineWhenEq:
    """when_eq() — find x when two vectors have equal y values."""

    def test_when_eq_ramps_crossing(self):
        """Two ramps cross at a known point."""
        t = np.linspace(0, 1, 10000)
        y_a = 5.0 * t       # 0 → 5
        y_b = np.full_like(t, 2.5)  # constant 2.5
        gd = _make_get_data({"v(a)": (t, y_a), "v(b)": (t, y_b)})
        result = evaluate_measure("when_eq(v(a), v(b))", gd)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_when_eq_rise_constraint(self):
        """when_eq with rise constraint finds the correct crossing."""
        t, y_sin = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        y_const = np.full_like(t, 2.5)
        gd = _make_get_data({"v(sin)": (t, y_sin), "v(ref)": (t, y_const)})
        # rise=1: first rising crossing at ~0.083
        result = evaluate_measure("when_eq(v(sin), v(ref), rise=1)", gd)
        assert result == pytest.approx(0.083, abs=0.01)

    def test_when_eq_fall_constraint(self):
        """when_eq with fall constraint."""
        t, y_sin = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        y_const = np.full_like(t, 2.5)
        gd = _make_get_data({"v(sin)": (t, y_sin), "v(ref)": (t, y_const)})
        # fall=1: first falling crossing at ~0.417
        result = evaluate_measure("when_eq(v(sin), v(ref), fall=1)", gd)
        assert result == pytest.approx(0.417, abs=0.02)

    def test_when_eq_missing_vector_raises(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(a)": (t, y)})
        with pytest.raises(ValueError, match="Vector not found"):
            evaluate_measure("when_eq(v(a), v(missing))", gd)


class TestEngineFindWhenEq:
    """find_when_eq() — find value of one vector when two others have equal y values."""

    def test_find_when_eq_basic(self):
        """FIND v(c) WHEN v(a)=v(b) returns v(c) at crossing."""
        t = np.linspace(0, 1, 10000)
        y_a = 5.0 * t       # ramp 0→5
        y_b = np.full_like(t, 2.5)  # constant
        y_c = 10.0 * t      # ramp 0→10
        gd = _make_get_data({"v(a)": (t, y_a), "v(b)": (t, y_b), "v(c)": (t, y_c)})
        # Crossing at t=0.5, v(c)=5.0
        result = evaluate_measure("find_when_eq(v(c), v(a), v(b))", gd)
        assert result == pytest.approx(5.0, abs=0.1)

    def test_find_when_eq_with_rise(self):
        """FIND with rise constraint on the crossing."""
        t, y_sin = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        y_const = np.full_like(t, 2.5)
        gd = _make_get_data({
            "v(out)": (t, y_sin),
            "v(sin)": (t, y_sin),
            "v(ref)": (t, y_const),
        })
        # When sine crosses 2.5 on first rise (t≈0.083), v(out)=v(sin)=2.5
        result = evaluate_measure(
            "find_when_eq(v(out), v(sin), v(ref), rise=1)", gd
        )
        assert result == pytest.approx(2.5, abs=0.01)

    def test_find_when_eq_missing_vector_raises(self):
        t = np.linspace(0, 1, 100)
        y_a = 5.0 * t
        y_b = np.full_like(t, 2.5)
        gd = _make_get_data({"v(a)": (t, y_a), "v(b)": (t, y_b)})
        with pytest.raises(ValueError, match="Vector not found"):
            evaluate_measure("find_when_eq(v(missing), v(a), v(b))", gd)

    def test_find_when_eq_missing_pos_arg_raises(self):
        t = np.linspace(0, 1, 100)
        gd = _make_get_data({"v(a)": (t, 5.0 * t)})
        with pytest.raises(ValueError, match="find_when_eq requires var1"):
            evaluate_measure("find_when_eq(v(a))", gd)


class TestEngineDerivWhen:
    """deriv_when() — derivative of a vector when another vector crosses a threshold."""

    def test_deriv_when_basic(self):
        """DERIVATIVE v(out) WHEN v(cond)=val returns derivative at crossing."""
        t = np.linspace(0, 1, 10000)
        y_out = 10.0 * t ** 2   # derivative = 20t
        y_cond = 5.0 * t        # ramp 0→5
        gd = _make_get_data({"v(out)": (t, y_out), "v(cond)": (t, y_cond)})
        # When v(cond)=2.5 → t=0.5, derivative of v(out) = 20*0.5 = 10
        result = evaluate_measure("deriv_when(v(out), v(cond), 2.5)", gd)
        assert result == pytest.approx(10.0, abs=0.5)

    def test_deriv_when_with_rise(self):
        """deriv_when with rise constraint."""
        t, y_out = _sine_data(amp=5.0, offset=0.0, freq=1.0, n=10000, t_stop=2.0)
        y_cond = 10.0 * t  # ramp
        gd = _make_get_data({"v(out)": (t, y_out), "v(cond)": (t, y_cond)})
        # When v(cond)=5 → t=0.5, derivative of 5*sin(2*pi*t) = 10*pi*cos(2*pi*t)
        # at t=0.5: 10*pi*cos(pi) = -10*pi ≈ -31.4
        result = evaluate_measure("deriv_when(v(out), v(cond), 5.0, rise=1)", gd)
        assert result == pytest.approx(-10 * math.pi, abs=1.0)

    def test_deriv_when_missing_vector_raises(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(ValueError, match="Vector not found"):
            evaluate_measure("deriv_when(v(out), v(missing), 0.0)", gd)


class TestEngineDerivWhenEq:
    """deriv_when_eq() — derivative when two vectors cross each other."""

    def test_deriv_when_eq_basic(self):
        """DERIVATIVE v(out) WHEN v(1)=v(2) returns derivative at crossing."""
        t = np.linspace(0, 1, 10000)
        y_out = 10.0 * t ** 2          # derivative = 20t
        y1 = 5.0 * t                   # ramp 0→5
        y2 = np.full_like(t, 2.5)      # constant 2.5
        gd = _make_get_data({"v(out)": (t, y_out), "v(1)": (t, y1), "v(2)": (t, y2)})
        # When v(1)=v(2) → 5t=2.5 → t=0.5, deriv of v(out) = 20*0.5 = 10
        result = evaluate_measure("deriv_when_eq(v(out), v(1), v(2))", gd)
        assert result == pytest.approx(10.0, abs=0.5)

    def test_deriv_when_eq_with_rise(self):
        """deriv_when_eq with rise=2 constraint."""
        t = np.linspace(0, 2, 10000)
        y_out = 2.0 * t                       # derivative = 2 everywhere
        y1 = np.sin(2 * math.pi * t)          # sine ±1
        y2 = np.full_like(t, 0.5)             # constant 0.5
        gd = _make_get_data({"v(out)": (t, y_out), "v(1)": (t, y1), "v(2)": (t, y2)})
        # v(1)=v(2) → sin(2πt)=0.5. Rise crossings at t≈0.083, t≈1.083.
        # rise=2 → t≈1.083, deriv of 2t = 2.0
        result = evaluate_measure("deriv_when_eq(v(out), v(1), v(2), rise=2)", gd)
        assert result == pytest.approx(2.0, abs=0.1)

    def test_deriv_when_eq_missing_vector_raises(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(out)": (t, y), "v(1)": (t, y)})
        with pytest.raises(ValueError, match="Vector not found"):
            evaluate_measure("deriv_when_eq(v(out), v(1), v(missing))", gd)

    def test_deriv_when_eq_missing_second_arg_raises(self):
        t, y = _sine_data()
        gd = _make_get_data({"v(out)": (t, y)})
        with pytest.raises(ValueError, match="requires var1 and var2"):
            evaluate_measure("deriv_when_eq(v(out))", gd)


# ============================================================================
# Part 3: End-to-End Tests with bridge.raw
# ============================================================================

@pytest.fixture(scope="module")
def bridge_data():
    """Load bridge.raw once for all end-to-end tests."""
    from pqwave.models.rawfile import RawFile
    test_dir = os.path.dirname(os.path.abspath(__file__))
    raw_path = os.path.join(test_dir, "bridge.raw")
    rf = RawFile(raw_path)
    ds = rf.datasets[0]
    data = ds["data"]
    var_names = [v["name"] for v in ds["variables"]]
    _bridge_get_data._rawfile = rf
    return data, var_names


def _bridge_get_data(data, var_names):
    """Build a get_data callable from bridge.raw data matrix.

    Falls back to ExprEvaluator when vec_name is an algebraic expression
    (e.g. "v(ac_p)-v(ac_n)") and the literal lookup misses — matching
    production behaviour in _measure_get_data.
    """
    name_to_col = {name.lower(): i for i, name in enumerate(var_names)}

    def get_data(vec_name: str) -> tuple[np.ndarray, np.ndarray] | None:
        key = vec_name.lower()
        if key in name_to_col:
            col = name_to_col[key]
            time_col = name_to_col.get("time", 0)
            x = data[:, time_col]
            y = data[:, col]
            return x, y

        # Expression fallback: try ExprEvaluator for compound expressions
        if any(c in _EXPR_CHARS_FOR_TEST for c in vec_name):
            rf = getattr(_bridge_get_data, '_rawfile', None)
            if rf is not None:
                try:
                    from pqwave.models.expression import ExprEvaluator
                    evaluator = ExprEvaluator(rf, 0)
                    y_data = evaluator.evaluate(vec_name)
                    time_col = name_to_col.get("time", 0)
                    x_data = data[:, time_col]
                    return x_data, y_data
                except Exception:
                    return None

        return None

    return get_data


class TestE2EBridgeStatistical:
    """AVG, MAX, MIN, PP, RMS, INTEG on bridge.raw v(r1)."""

    def test_avg_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("avg(v(r1))", gd)
        assert 90.0 < result < 100.0

    def test_max_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("max(v(r1))", gd)
        assert 95.0 < result < 105.0

    def test_min_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("min(v(r1))", gd)
        assert -1.0 < result < 2.0  # float32 noise can produce tiny negative values

    def test_pp_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("pp(v(r1))", gd)
        assert result > 90.0

    def test_rms_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("rms(v(r1))", gd)
        assert 90.0 < result < 100.0

    def test_integ_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("integ(v(r1))", gd)
        assert result > 0.0

    def test_min_at_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("min_at(v(r1))", gd)
        assert 0.0 <= result <= 0.04

    def test_max_at_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("max_at(v(r1))", gd)
        assert 0.03 <= result <= 0.04

    def test_avg_vr2(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("avg(v(r2))", gd)
        assert result > 0.0

    def test_max_vr2(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("max(v(r2))", gd)
        assert result > 0.0

    def test_avg_windowed_vr1(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("avg(v(r1), from=10m, to=30m)", gd)
        assert 90.0 < result < 105.0


class TestE2EBridgeFindAt:
    """find_at() on bridge.raw."""

    def test_find_at_20ms(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("find_at(v(r1), 20m)", gd)
        assert 90.0 < result < 100.0

    def test_find_at_start(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("find_at(v(r1), 0)", gd)
        assert result < 2.0

    def test_find_at_expression(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("find_at(v(ac_p)-v(ac_n), 10m)", gd)
        assert -400.0 < result < 400.0


class TestE2EBridgeWhenCross:
    """when_cross() on bridge.raw."""

    def test_when_cross_vr1_50(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("when_cross(v(r1), 50)", gd)
        assert 0.0 < result < 0.04

    def test_when_cross_vr1_90(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("when_cross(v(r1), 90)", gd)
        assert 0.0 < result < 0.04

    def test_when_cross_fall(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        # v(ac_p) is a clean sine — use it for fall crossing test
        result = evaluate_measure("when_cross(v(ac_p), 0, fall=1)", gd)
        assert 0.0 < result < 0.04


class TestE2EBridgeDerivAt:
    """deriv_at() on bridge.raw."""

    def test_deriv_at_20ms(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        result = evaluate_measure("deriv_at(v(r1), 20m)", gd)
        assert -1e7 < result < 1e7


class TestE2EParseAndEvaluate:
    """Full pipeline: parse SPICE script → evaluate each expression on bridge.raw."""

    def test_full_script(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)

        script = (
            ".meas tran avg_vr1 AVG v(r1)\n"
            ".meas tran max_vr1 MAX v(r1)\n"
            ".meas tran min_vr1 MIN v(r1)\n"
            ".meas tran pp_vr1 PP v(r1)\n"
            ".meas tran rms_vr1 RMS v(r1)\n"
            ".meas tran res_find FIND v(r1) AT=20m\n"
            ".meas tran res_when WHEN v(r1)=50\n"
            ".meas tran res_deriv DERIV v(r1) AT=20m"
        )
        parsed = parse_meas_script(script)
        assert len(parsed) == 8

        for expr, label in parsed:
            result = evaluate_measure(expr, gd)
            assert isinstance(result, float)
            assert np.isfinite(result)

    def test_avg_windowed_parse_evaluate(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(
            ".meas tran w_avg AVG v(r1) from=10m to=30m"
        )
        expr, label = results[0]
        assert label == "w_avg"
        result = evaluate_measure(expr, gd)
        assert 90.0 < result < 105.0

    def test_find_when_parse_evaluate(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(
            ".meas tran fw FIND v(r2) WHEN v(r1)=50"
        )
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert result > 0.0

    def test_rise_time_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran rt RISE_TIME v(r1)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert result > 0.0

    def test_fall_time_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        # v(ac_p) is a ~100 Hz sine with DC offset ~49 V
        results = parse_meas_script(".meas tran ft FALL_TIME v(ac_p)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert 0.001 < result < 0.006

    def test_period_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran pd PERIOD v(ac_p)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert 0.005 < result < 0.015

    def test_frequency_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran freq FREQUENCY v(ac_p)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert 80.0 < result < 120.0

    def test_duty_cycle_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran dc DUTY_CYCLE v(ac_p)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert 30.0 < result < 70.0

    def test_pulse_width_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran pw PULSE_WIDTH v(ac_p)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert 0.003 < result < 0.008

    def test_settling_time_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran st SETTLING_TIME v(r1)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert result >= 0.0

    def test_slew_rate_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran sr SLEW_RATE v(r1)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert result > 0.0

    def test_overshoot_bridge(self, bridge_data):
        data, var_names = bridge_data
        gd = _bridge_get_data(data, var_names)
        results = parse_meas_script(".meas tran os OVERSHOOT v(r1)")
        expr, label = results[0]
        result = evaluate_measure(expr, gd)
        assert result >= 0.0
