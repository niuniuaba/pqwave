#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Bode plot computation module."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest


def test_detect_bode_vectors_db_phase():
    from pqwave.analysis.bode import detect_bode_vectors
    names = ["frequency", "v(out)_db", "v(out)_phase", "v(in)"]
    result = detect_bode_vectors(names)
    assert result is not None
    mag, phase, freq = result
    assert mag == "v(out)_db"
    assert phase == "v(out)_phase"


def test_detect_bode_vectors_no_match():
    from pqwave.analysis.bode import detect_bode_vectors
    names = ["time", "v(out)", "i(r1)"]
    result = detect_bode_vectors(names)
    assert result is None


def test_compute_bode_from_mag_phase():
    from pqwave.analysis.bode import compute_bode
    freq = np.logspace(1, 6, 1000)
    mag_db = -20 * np.log10(freq / 1000)
    phase = -np.arctan(freq / 1000) * 180 / np.pi
    result = compute_bode(mag_db=mag_db, phase_deg=phase, freq=freq)
    assert "gain_db" in result
    assert "phase_deg" in result
    assert "freq" in result
    assert len(result["gain_db"]) == 1000


def test_compute_bode_from_fft():
    from pqwave.analysis.bode import compute_bode
    t = np.linspace(0, 1, 10000, endpoint=False)
    signal = np.sin(2 * np.pi * 1000 * t)
    result = compute_bode(signal=signal, sampling_rate=10000)
    assert "gain_db" in result
    assert "phase_deg" in result
    assert "freq" in result
    assert len(result["freq"]) == len(result["gain_db"])
