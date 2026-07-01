#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analysis package — computation engines for waveform analysis.

Pure-numpy modules with no Qt dependencies, callable from both UI and CLI.
"""

from pqwave.analysis.bode import compute_bode, detect_bode_vectors
from pqwave.analysis.histogram import compute_histogram
from pqwave.analysis.nyquist import (
    compute_nyquist_trace,
    detect_nyquist_vectors,
)
from pqwave.analysis.polar import (
    compute_polar_trace,
    detect_polar_vectors,
)
from pqwave.analysis.power_analyzer import power_analysis
from pqwave.analysis.smith import (
    clamp_gamma,
    compute_reflection_coefficient,
    normalize_impedance,
    smith_grid_circles,
)
from pqwave.analysis.worst_case import (
    enumerate_corners,
    apply_tempco,
    rank_by_sensitivity,
    modify_netlist,
)

__all__ = [
    "clamp_gamma",
    "compute_bode",
    "compute_histogram",
    "compute_nyquist_trace",
    "compute_polar_trace",
    "compute_reflection_coefficient",
    "detect_bode_vectors",
    "detect_nyquist_vectors",
    "detect_polar_vectors",
    "normalize_impedance",
    "power_analysis",
    "smith_grid_circles",
    "enumerate_corners",
    "apply_tempco",
    "rank_by_sensitivity",
    "modify_netlist",
]
