#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Nyquist analysis module."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_nyquist_computation():
    from pqwave.analysis.nyquist import compute_nyquist_trace
    t = np.linspace(0, 1, 100)
    real = np.cos(2 * np.pi * t)
    imag = np.sin(2 * np.pi * t)
    result = compute_nyquist_trace(real=real, imag=imag, freq=t)
    assert "x" in result
    assert "y" in result
    assert len(result["x"]) == 100
    assert len(result["y"]) == 100


def test_nyquist_vector_detection_complex():
    from pqwave.analysis.nyquist import detect_nyquist_vectors
    var_names = ["v(out)_real", "v(out)_imag", "frequency", "v(in)"]
    result = detect_nyquist_vectors(var_names)
    assert result is not None
    real_var, imag_var = result
    assert real_var == "v(out)_real"
    assert imag_var == "v(out)_imag"


def test_nyquist_no_detectable_pair():
    from pqwave.analysis.nyquist import detect_nyquist_vectors
    var_names = ["time", "v(out)", "i(r1)"]
    result = detect_nyquist_vectors(var_names)
    assert result is None


def test_equal_aspect_enabled(qapp):
    from pqwave.ui.plot_widget import PlotWidget
    pw = PlotWidget(equal_aspect=True)
    vb = pw.getViewBox()
    assert vb.state["aspectLocked"] == 1.0
    pw.close()
