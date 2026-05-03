#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analysis package — computation engines for waveform analysis.

Pure-numpy modules with no Qt dependencies, callable from both UI and CLI.
"""

from pqwave.analysis.power_analyzer import power_analysis

__all__ = ["power_analysis"]
