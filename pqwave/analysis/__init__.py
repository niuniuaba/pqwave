#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analysis package — computation engines for waveform analysis.

Pure-numpy modules with no Qt dependencies, callable from both UI and CLI.
"""

from pqwave.analysis.histogram import compute_histogram
from pqwave.analysis.power_analyzer import power_analysis

__all__ = ["compute_histogram", "power_analysis"]
