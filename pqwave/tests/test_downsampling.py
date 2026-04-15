#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test that PlotDataItem autoDownsample actually reduces rendered points
and adapts to zoom level.

Usage:
    python test_downsampling.py                          # synthetic sine wave (100k points)
    python test_downsampling.py --datafile FILE --trace_name VAR  # real data file

This test verifies the fix for issues.md No.6 (performance improvement).
"""

import sys
sys.path.insert(0, '.')

import argparse
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

THRESHOLD_RATIO = 0.10  # full view should render <10% of original points


def _make_item(x, y):
    """Create a PlotDataItem with autoDownsample enabled."""
    item = pg.PlotDataItem(
        x, y,
        symbol=None,
        skipFiniteCheck=True,
        autoDownsample=True,
        downsampleMethod='peak',
    )
    pw = pg.PlotWidget()
    pw.plotItem.vb.addItem(item)
    pw.resize(800, 600)
    QApplication.instance().processEvents()
    return item, pw


def _get_displayed_count(item):
    ds = item._getDisplayDataset()
    return len(ds.x) if ds else 0


def test_autodownsample_reduces_points(x, y, label):
    """Verify autoDownsample reduces the number of rendered points."""
    N = len(x)
    item, pw = _make_item(x, y)

    dataset = item._getDisplayDataset()
    assert dataset is not None, "_getDisplayDataset should not return None"

    displayed = len(dataset.x)
    ratio = displayed / N

    assert ratio < THRESHOLD_RATIO, \
        f"Expected <{THRESHOLD_RATIO*100:.0f}% points displayed at full view, got {ratio*100:.1f}%"
    assert item._adsLastValue > 1, \
        f"Expected downsample factor > 1, got {item._adsLastValue}"

    print(f"PASS: {label} full view — {displayed:,} / {N:,} points ({ratio*100:.1f}%), factor={item._adsLastValue}")


def test_autodownsample_adapts_to_zoom(x, y, label):
    """Verify autoDownsample adjusts factor based on visible X range."""
    N = len(x)
    item, pw = _make_item(x, y)

    # Full view
    full = _get_displayed_count(item)

    # Zoom into middle 10% of X range
    x_min, x_max = x[0], x[-1]
    mid = (x_min + x_max) / 2
    span = (x_max - x_min) * 0.05
    pw.plotItem.vb.setXRange(mid - span, mid + span, padding=0)
    QApplication.instance().processEvents()
    zoomed = _get_displayed_count(item)

    assert zoomed > full, \
        f"Expected more points at 10x zoom ({zoomed:,}) than full view ({full:,})"

    print(f"PASS: {label} zoom adapts — full={full:,}, 10x zoom={zoomed:,}")


def load_synthetics():
    """Return synthetic 100k-point sine wave data."""
    N = 100_000
    x = np.linspace(0, 1, N)
    y = np.sin(x * 100)
    return x, y, f"synthetic ({N:,} points)"


def load_real_data(filepath, trace_name):
    """Return data from a real raw file."""
    from pqwave.models.rawfile import RawFile

    rf = RawFile(filepath)
    N = rf.get_num_points(0)
    x_data = rf.get_variable_data('Time', 0)
    y_data = rf.get_variable_data(trace_name, 0)

    if x_data is None:
        print(f"ERROR: Could not load 'Time' variable from {filepath}")
        sys.exit(1)
    if y_data is None:
        print(f"ERROR: Could not load '{trace_name}' variable from {filepath}")
        available = rf.get_variable_names(0)
        print(f"Available variables: {', '.join(available[:10])}..." if len(available) > 10 else f"Available variables: {', '.join(available)}")
        sys.exit(1)

    return x_data, y_data, f"{filepath} ({N:,} points, {trace_name})"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Test pyqtgraph autoDownsample on waveform data.'
    )
    parser.add_argument('--datafile', type=str, help='Path to a .raw/.qraw data file')
    parser.add_argument('--trace_name', type=str, help='Variable name to plot (e.g. I(R1))')
    args = parser.parse_args()

    if (args.datafile and not args.trace_name) or (args.trace_name and not args.datafile):
        print("ERROR: --datafile and --trace_name must be used together.")
        print("Usage:")
        print("  python test_downsampling.py                                    (synthetic data)")
        print("  python test_downsampling.py --datafile FILE --trace_name VAR   (real data)")
        sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)

    if args.datafile and args.trace_name:
        x, y, label = load_real_data(args.datafile, args.trace_name)
    else:
        x, y, label = load_synthetics()
        print("Tip: use --datafile and --trace_name to test with real waveform data.")
        print("  Example: python test_downsampling.py --datafile tests/SMPS.qraw --trace_name 'I(R1)'")
        print()

    test_autodownsample_reduces_points(x, y, label)
    test_autodownsample_adapts_to_zoom(x, y, label)
    print("All downsampling tests passed.")
