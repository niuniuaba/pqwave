#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parser for .meas-style script files.

Maps SPICE/ngspice aliases to internal pqwave measure function names
and returns a list of (expression, label) tuples for batch execution.
"""

from __future__ import annotations

import re

# Known SPICE .meas function keywords. Used to distinguish
# ".meas tran when v(r1)=96" (when = function) from
# ".meas tran result find v(out) at=1k" (result = VARNAME).
_SPICE_KEYWORDS: frozenset[str] = frozenset({
    'find', 'when', 'deriv', 'avg', 'rms', 'integ',
    'min', 'max', 'pp', 'min_at', 'max_at',
    'rise_time', 'fall_time', 'period', 'frequency',
    'duty_cycle', 'pulse_width', 'settling_time', 'slew_rate',
    'overshoot', 'undershoot', 'thd', 'sinad', 'snr', 'sfdr',
})

# Patterns for SPICE alias mapping.
# Each is (regex, replacement_template) where template uses \1, \2, etc.
# Order matters: more-specific patterns must come before less-specific ones.
_ALIASES: list[tuple[str, str]] = [
    # find expr when cond=val  →  find_when(expr, cond, val)
    # Must precede find_at pattern because "when" contains "at=..." sequences
    (r'^find\s+(.+?)\s+when\s+(.+?)\s*=\s*(.+)$',
     r'find_when(\1, \2, \3)'),

    # find v(out) at=1k  →  find_at(v(out), 1k)
    (r'^find\s+(\S+(?:\s*\([^)]*\))?)\s+at\s*=\s*(\S+)',
     r'find_at(\1, \2)'),

    # when v(out)=2.5 rise=1  →  when_cross(v(out), 2.5, rise=1)  (with extra args)
    (r'^when\s+(\S+(?:\s*\([^)]*\))?)\s*=\s*(\S+)\s+(.+)$',
     r'when_cross(\1, \2, \3)'),

    # when v(out)=2.5  →  when_cross(v(out), 2.5)  (no extra args)
    (r'^when\s+(\S+(?:\s*\([^)]*\))?)\s*=\s*(\S+)$',
     r'when_cross(\1, \2)'),

    # deriv v(out) at=1m  →  deriv_at(v(out), 1m)
    (r'^deriv\s+(\S+(?:\s*\([^)]*\))?)\s+at\s*=\s*(\S+)',
     r'deriv_at(\1, \2)'),

    # avg v(out) from=0 to=10m  →  avg(v(out), from=0, to=10m)
    (r'^avg\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'avg(\1, \2)'),

    # rms v(out) from=0 to=10m  →  rms(v(out), from=0, to=10m)
    (r'^rms\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'rms(\1, \2)'),

    # integ v(out) from=0 to=10m  →  integ(v(out), from=0, to=10m)
    (r'^integ\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'integ(\1, \2)'),

    # Single-arg functions with extra args: min/max/pp/min_at/max_at
    (r'^(min|max|pp|min_at|max_at)\s+(\S+(?:\s*\([^)]*\))?)\s+(.+)$',
     r'\1(\2, \3)'),

    # Single-arg functions (no extra args)
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


def parse_meas_script(text: str) -> list[tuple[str, str]]:
    """Parse a .meas-style script into (expression, label) tuples.

    Args:
        text: Full script content as a string.

    Returns:
        List of (expression, label_or_empty) tuples. The label is the
        measurement name from "meas ac VARNAME ..." lines, or "" for
        direct function calls.
    """
    results: list[tuple[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('*'):
            continue

        label = ""
        expr = line

        m = _MEAS_PREFIX.match(line)
        if m and m.group(2).lower() not in _SPICE_KEYWORDS:
            label = m.group(2)
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
    for pattern, replacement in _ALIASES:
        m = re.match(pattern, line, re.IGNORECASE)
        if m:
            return m.expand(replacement)
    # If no alias matched, assume it's already in pqwave syntax
    return line
