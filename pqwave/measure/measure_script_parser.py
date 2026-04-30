#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parser for .meas-style script files.

Maps SPICE/ngspice aliases to internal pqwave measure function names
and returns a list of (expression, label) tuples for batch execution.
"""

from __future__ import annotations

import re
from typing import Callable

# Known SPICE .meas function keywords. Used to distinguish
# ".meas tran when v(r1)=96" (when = function) from
# ".meas tran result find v(out) at=1k" (result = VARNAME).
_SPICE_KEYWORDS: frozenset[str] = frozenset({
    'find', 'when', 'deriv', 'avg', 'rms', 'integ',
    'integral', 'derivative',
    'min', 'max', 'pp', 'min_at', 'max_at',
    'rise_time', 'fall_time', 'period', 'frequency',
    'duty_cycle', 'pulse_width', 'settling_time', 'slew_rate',
    'overshoot', 'undershoot', 'thd', 'sinad', 'snr', 'sfdr',
    'param', 'trig', 'targ',
})


def _prefix_kwargs(section: str, prefix: str) -> str:
    """Prefix kwarg keys in a space-separated kwarg string.

    "val=0.5 rise=1" with prefix "trig_" → "trig_val=0.5 trig_rise=1"
    """
    parts = section.strip().split()
    result_parts = []
    for part in parts:
        if '=' in part:
            k, v = part.split('=', 1)
            result_parts.append(f'{prefix}{k}={v}')
        else:
            result_parts.append(part)
    return ' '.join(result_parts)


# Helper callables for complex alias transformations.
# Each receives the re.Match object and returns the transformed string.

def _alias_trig_targ_with_func(m: re.Match) -> str:
    """.meas tran result AVG v(out) TRIG ... TARG ... → trig_targ(v(out), _func=avg, trig_..., targ_...)"""
    func = m.group(1).lower()
    vector = m.group(2)
    trig_section = m.group(3)
    targ_section = m.group(4)
    trig = _prefix_kwargs(trig_section, "trig_")
    targ = _prefix_kwargs(targ_section, "targ_")
    return f"trig_targ({vector}, _func={func}, {trig}, {targ})"


def _alias_trig_targ_standalone(m: re.Match) -> str:
    """Trig/Targ alone = distance between two points
    .meas tran result TRIG ... TARG ... → trig_targ(trig_..., targ_...)
    """
    trig_section = m.group(1)
    targ_section = m.group(2)
    trig = _prefix_kwargs(trig_section, "trig_")
    targ = _prefix_kwargs(targ_section, "targ_")
    return f"trig_targ({trig}, {targ})"


def _alias_find_when_eq(m: re.Match) -> str:
    """.meas tran result FIND v(out) WHEN v(1)=v(2) → find_when_eq(v(out), v(1), v(2))"""
    find_expr = m.group(1)
    when_var1 = m.group(2)
    when_var2 = m.group(3)
    return f"find_when_eq({find_expr}, {when_var1}, {when_var2})"


def _alias_when_eq(m: re.Match) -> str:
    """.meas tran result WHEN v(out)=v(ref) → when_eq(v(out), v(ref))"""
    var1 = m.group(1)
    var2 = m.group(2)
    return f"when_eq({var1}, {var2})"


def _alias_deriv_when_eq(m: re.Match) -> str:
    """DERIVATIVE v(out) WHEN v(1)=v(2) → deriv_when_eq(v(out), v(1), v(2))
    With extra kwargs (td=, cross=, rise=, fall=) preserved."""
    deriv_expr = m.group(1)
    when_var1 = m.group(2)
    when_var2 = m.group(3)
    extra = m.group(4) if m.lastindex >= 4 and m.group(4) else ""
    if extra:
        return f"deriv_when_eq({deriv_expr}, {when_var1}, {when_var2}, {extra.strip()})"
    return f"deriv_when_eq({deriv_expr}, {when_var1}, {when_var2})"


def _alias_deriv_when(m: re.Match) -> str:
    """DERIVATIVE v(out) WHEN v(1)=val ... → deriv_when(v(out), v(1), val, ...)"""
    deriv_expr = m.group(1)
    when_var = m.group(2)
    val = m.group(3)
    extra = m.group(4) if m.lastindex >= 4 and m.group(4) else ""
    if extra:
        return f"deriv_when({deriv_expr}, {when_var}, {val}, {extra.strip()})"
    return f"deriv_when({deriv_expr}, {when_var}, {val})"


# Patterns for SPICE alias mapping.
# Each is (regex, replacement_template_or_callable).
# Order matters: more-specific patterns must come before less-specific ones.
# replacement can be a string template (with \1, \2, etc.) or a callable(match)→str.
_ALIASES: list[tuple[str, str | Callable[[re.Match], str]]] = [
    # ---- TRIG/TARG with function (e.g. AVG v(out) TRIG ... TARG ...) ----
    # Must precede standalone TRIG/TARG to capture function keyword.
    (r'^(avg|min|max|pp|rms|integ)\s+(\S+(?:\s*\([^)]*\))?)\s+'
     r'trig\s+(.+?)\s+targ\s+(.+)$',
     _alias_trig_targ_with_func),

    # ---- TRIG/TARG standalone (distance between two trigger points) ----
    (r'^trig\s+(.+?)\s+targ\s+(.+)$',
     _alias_trig_targ_standalone),

    # ---- FIND ... WHEN var1=var2 (vector equality, must precede find_when) ----
    # RHS/LHS of equality must start with letter to avoid matching arithmetic
    # expressions like "3*v(y)" as vector references.
    (r'^find\s+(\S+(?:\s*\([^)]*\))?)\s+when\s+'
     r'([a-zA-Z_]\S*(?:\s*\([^)]*\))?)\s*=\s*([a-zA-Z_]\S*(?:\s*\([^)]*\))?)$',
     _alias_find_when_eq),

    # ---- find expr when cond=val  →  find_when(expr, cond, val) ----
    # Must precede find_at pattern because "when" contains "at=..." sequences
    (r'^find\s+(.+?)\s+when\s+(.+?)\s*=\s*(.+)$',
     r'find_when(\1, \2, \3)'),

    # ---- find v(out) at=val  →  find_at(v(out), val) ----
    (r'^find\s+(\S+(?:\s*\([^)]*\))?)\s+at\s*=\s*(\S+)',
     r'find_at(\1, \2)'),

    # ---- WHEN var1=var2 (when two vectors cross, must precede when var=val) ----
    # Both sides must start with letter to avoid matching arithmetic RHS like "3*v(y)".
    (r'^when\s+([a-zA-Z_]\S*(?:\s*\([^)]*\))?)\s*=\s*([a-zA-Z_]\S*(?:\s*\([^)]*\))?)$',
     _alias_when_eq),

    # ---- when v(out)=val rise=1  →  when_cross(v(out), val, rise=1) ----
    (r'^when\s+(\S+(?:\s*\([^)]*\))?)\s*=\s*(\S+)\s+(.+)$',
     r'when_cross(\1, \2, \3)'),

    # ---- when v(out)=val  →  when_cross(v(out), val) (no extra args) ----
    (r'^when\s+(\S+(?:\s*\([^)]*\))?)\s*=\s*(\S+)$',
     r'when_cross(\1, \2)'),

    # ---- DERIVATIVE v(out) WHEN v(1)=v(2) ... (vector equality, must precede) ----
    # Equality sides must start with letter to avoid matching scalar RHS.
    (r'^deriv\s+(\S+(?:\s*\([^)]*\))?)\s+when\s+'
     r'([a-zA-Z_]\S*(?:\s*\([^)]*\))?)\s*=\s*([a-zA-Z_]\S*(?:\s*\([^)]*\))?)\s+(.+)$',
     _alias_deriv_when_eq),

    (r'^deriv\s+(\S+(?:\s*\([^)]*\))?)\s+when\s+'
     r'([a-zA-Z_]\S*(?:\s*\([^)]*\))?)\s*=\s*([a-zA-Z_]\S*(?:\s*\([^)]*\))?)$',
     _alias_deriv_when_eq),

    # ---- DERIVATIVE v(out) WHEN v(1)=val extra...  →  deriv_when(v(out), v(1), val, extra) ----
    (r'^deriv\s+(\S+(?:\s*\([^)]*\))?)\s+when\s+'
     r'(\S+(?:\s*\([^)]*\))?)\s*=\s*(\S+)\s+(.+)$',
     _alias_deriv_when),

    # ---- DERIVATIVE v(out) WHEN v(1)=val  →  deriv_when(v(out), v(1), val) ----
    (r'^deriv\s+(\S+(?:\s*\([^)]*\))?)\s+when\s+'
     r'(\S+(?:\s*\([^)]*\))?)\s*=\s*(\S+)$',
     _alias_deriv_when),

    # ---- deriv v(out) at=val  →  deriv_at(v(out), val) ----
    (r'^deriv\s+(\S+(?:\s*\([^)]*\))?)\s+at\s*=\s*(\S+)',
     r'deriv_at(\1, \2)'),

    # ---- param='expression' (ngspice style with ='...') ----
    (r"^param\s*=\s*'(.+)'$", r'\1'),

    # ---- param="expression" (ngspice style with ="..." / ="..." quotes) ----
    (r'^param\s*=\s*"(.+)"$', r'\1'),

    # ---- param expression (LTspice style pass-through) ----
    (r'^param\s+(.+)$', r'\1'),

    # ---- avg v(out) from=0 to=10m  →  avg(v(out), from=0, to=10m) ----
    (r'^avg\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'avg(\1, \2)'),

    # ---- rms v(out) from=0 to=10m  →  rms(v(out), from=0, to=10m) ----
    (r'^rms\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'rms(\1, \2)'),

    # ---- integ v(out) from=0 to=10m  →  integ(v(out), from=0, to=10m) ----
    (r'^integ\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'integ(\1, \2)'),

    # ---- Single-arg functions with extra args: min/max/pp/min_at/max_at ----
    (r'^(min|max|pp|min_at|max_at)\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'\1(\2, \3)'),

    # ---- Single-arg functions (no extra args) ----
    (r'^(min|max|avg|rms|pp|integ|min_at|max_at|rise_time|fall_time|'
     r'period|frequency|duty_cycle|pulse_width|settling_time|slew_rate|'
     r'overshoot|undershoot|thd|sinad|snr|sfdr)\s+(\S+(?:\s*\([^)]*\))?)$',
     r'\1(\2)'),
]

# Matches ".meas ac VARNAME <rest>" or ".meas tran VARNAME <rest>"
_MEAS_PREFIX = re.compile(
    r'^\.?meas\s+(ac|tran|dc|sp|tf|noise|op)\s+(\S+)\s+(.+)$',
    re.IGNORECASE,
)

# Matches ".meas tran <rest>" or "meas ac <rest>" without an explicit VARNAME
_MEAS_NO_NAME = re.compile(
    r'^\.?meas\s+(ac|tran|dc|sp|tf|noise|op)\s+(.+)$',
    re.IGNORECASE,
)


def _join_continuations(text: str) -> str:
    """Join SPICE + continuation lines to their parent lines.

    Lines starting with '+' (after optional whitespace) continue the
    preceding non-comment, non-empty line.  The '+' is replaced with a
    space when joining.
    """
    lines = text.splitlines()
    joined: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('+') and joined and joined[-1].strip():
            # Append content after '+' to the previous line
            continuation = stripped[1:].strip()
            if continuation:
                joined[-1] = joined[-1] + ' ' + continuation
        else:
            joined.append(line)
    return '\n'.join(joined)


def parse_meas_script(text: str) -> list[tuple[str, str]]:
    """Parse a .meas-style script into (expression, label) tuples.

    Args:
        text: Full script content as a string.

    Returns:
        List of (expression, label_or_empty) tuples. The label is the
        measurement name from "meas ac VARNAME ..." lines, or "" for
        direct function calls.
    """
    # Preprocess: join + continuation lines before parsing
    text = _join_continuations(text)

    results: list[tuple[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('*'):
            continue

        label = ""
        expr = line

        m = _MEAS_PREFIX.match(line)
        if m and m.group(2).lower() not in _SPICE_KEYWORDS:
            label = m.group(2).lower()
            rest = m.group(3)
            expr = _apply_aliases(rest)
        else:
            # Try .meas without VARNAME (e.g. ".meas tran when v(r1)=96")
            mn = _MEAS_NO_NAME.match(line)
            if mn:
                rest = mn.group(2)
                expr = _apply_aliases(rest)
            else:
                expr = _apply_aliases(line)

        results.append((expr, label))

    return results


def _apply_aliases(line: str) -> str:
    """Map SPICE-style syntax to internal pqwave function syntax."""
    # Normalize long-form keywords to short-form
    line = re.sub(r'^integral\b', 'integ', line, flags=re.IGNORECASE)
    line = re.sub(r'^derivative\b', 'deriv', line, flags=re.IGNORECASE)

    # Unwrap par('expression') and par("expression") — ngspice syntax for
    # embedding algebraic expressions where a vector name is expected.
    # The inner expression flows through the ExprEvaluator fallback in get_data.
    line = re.sub(r"par\('([^']*)'\)", r'\1', line)
    line = re.sub(r'par\("([^"]*)"\)', r'\1', line)

    for pattern, replacement in _ALIASES:
        m = re.match(pattern, line, re.IGNORECASE)
        if m:
            if callable(replacement):
                result = replacement(m)
            else:
                result = m.expand(replacement)
            # Convert space-separated kwargs to comma-separated
            # e.g. "from=0 to=10m" → "from=0, to=10m"
            result = re.sub(r'(?<!,)\s+(?=\w+=)', ', ', result)
            return result.lower()
    # If no alias matched, assume it's already in pqwave syntax
    return line.lower()
