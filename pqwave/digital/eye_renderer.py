"""Eye diagram rendering.

Overlay mode slices raw analog data into windows and overdraws each
window as a translucent trace (same approach as eyediagram.mpl.eyediagram_lines).

Persistence mode computes a 2D count grid via eyediagram.core.grid_count()
and displays it as a colour heatmap via pg.ImageItem.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtGui, QtCore

from eyediagram.core import grid_count


def colorize(counts: np.ndarray, color1: tuple, color2: tuple = None):
    """Convert integer *counts* array to an RGBA image.

    Colours vary linearly from *color1* to *color2* (default white).
    Zero-count pixels are transparent.
    """
    if color2 is None:
        color2 = (255, 255, 255)
    m = max(1, int(counts.max()))
    colors = np.zeros((m + 1, 4), dtype=np.uint8)
    if m == 1:
        colors[1] = (*color2, 255)
    else:
        r = np.linspace(color1[0], color2[0], m)
        g = np.linspace(color1[1], color2[1], m)
        b = np.linspace(color1[2], color2[2], m)
        colors[1:, 0] = r.astype(np.uint8)
        colors[1:, 1] = g.astype(np.uint8)
        colors[1:, 2] = b.astype(np.uint8)
        colors[1:, 3] = 255
    colors[0, 3] = 0
    return colors[counts]


def compute_eye_metrics(counts: np.ndarray, ybounds: tuple) -> dict:
    """Compute eye height, eye width, and optimal sampling point from a
    grid_count output array.

    *counts* has shape ``(width, height)`` — time across columns,
    voltage down rows.  *ybounds* is ``(ymin, ymax)`` in volts.
    """
    width, height = counts.shape
    dy = (ybounds[1] - ybounds[0]) / height

    # For each time column find the largest gap between upper / lower clusters.
    gaps = np.full(width, np.nan, dtype=np.float64)
    mid = height // 2
    for col in range(width):
        nonzero = np.where(counts[col, :] > 0)[0]
        if len(nonzero) < 5:
            continue
        lower = nonzero[nonzero < mid]
        upper = nonzero[nonzero >= mid]
        if len(lower) == 0 or len(upper) == 0:
            continue
        gaps[col] = (upper[0] - lower[-1]) * dy

    if np.all(np.isnan(gaps)):
        return {}

    best_col = int(np.nanargmax(gaps))
    eye_height = float(gaps[best_col])

    # Optimal sampling time in UI (0..2)
    opt_time = best_col / width * 2.0

    # Eye width at 50% of max height
    half_h = eye_height * 0.5
    above = np.where(gaps >= half_h)[0]
    if len(above) > 0:
        eye_width = (above[-1] - above[0]) / width * 2.0
    else:
        eye_width = 0.0

    # Average voltage of the two rails (center of the eye)
    upper_levels = []
    lower_levels = []
    for col in range(width):
        nz = np.where(counts[col, :] > 0)[0]
        if len(nz) < 5:
            continue
        lo = nz[nz < mid]
        hi = nz[nz >= mid]
        if len(lo) and len(hi):
            lower_levels.append(lo[-1])
            upper_levels.append(hi[0])
    v_mid = ybounds[0] + dy * (
        (np.median(upper_levels) + np.median(lower_levels)) / 2.0
        if upper_levels else mid)

    return {
        'eye_height': eye_height,
        'eye_width': eye_width,
        'opt_time': opt_time,
        'v_mid': v_mid,
    }


def _add_metrics_overlay(plot_widget: pg.PlotWidget, metrics: dict) -> None:
    """Draw eye-height / eye-width markers and a label on the plot."""
    if not metrics:
        return
    opt_t = metrics['opt_time']
    v_mid = metrics['v_mid']
    half_h = metrics['eye_height'] / 2.0

    pen = pg.mkPen('cyan', width=1, style=QtCore.Qt.PenStyle.DashLine)
    for y in (v_mid + half_h, v_mid - half_h):
        line = pg.InfiniteLine(pos=y, angle=0, pen=pen)
        plot_widget.addItem(line)

    opt_pen = pg.mkPen('red', width=1, style=QtCore.Qt.PenStyle.DotLine)
    opt_line = pg.InfiniteLine(pos=opt_t, angle=90, pen=opt_pen)
    plot_widget.addItem(opt_line)

    label = pg.TextItem(
        f"H={metrics['eye_height']:.3f}V  W={metrics['eye_width']:.3f}UI",
        color='white', anchor=(0, 1))
    label.setPos(opt_t, v_mid + half_h)
    plot_widget.addItem(label)


def render_overlay(plot_widget: pg.PlotWidget, y_data: np.ndarray,
                   window_size: int, offset: int):
    """Render eye diagram as overlaid waveform windows (raw analog)."""
    plot_widget.clear()
    plot_widget.setBackground('k')
    plot_widget.setLabel('bottom', 'Sample')
    plot_widget.setLabel('left', 'Amplitude')
    plot_widget.showGrid(x=True, y=True, alpha=0.3)

    n = len(y_data)
    if n < window_size:
        return

    pen = pg.mkPen(color=(0, 220, 0, 100), width=1)
    start = offset
    while start + window_size < n:
        end = start + window_size
        yy = y_data[start:end + 1]
        xx = np.arange(len(yy), dtype=np.float64)
        plot_widget.addItem(pg.PlotDataItem(
            xx, yy, pen=pen, symbol=None, skipFiniteCheck=True,
        ))
        start = end

    # Compute metrics from a lightweight grid_count pass
    y_clean = y_data[np.isfinite(y_data)]
    yb = (y_clean.min(), y_clean.max())
    yb = (yb[0] - 0.05*(yb[1]-yb[0]), yb[1] + 0.05*(yb[1]-yb[0]))
    counts = grid_count(y_data, window_size, offset=offset, size=(240, 240),
                        fuzz=False, bounds=yb)
    metrics = compute_eye_metrics(counts, yb)
    _add_metrics_overlay(plot_widget, metrics)

    plot_widget.autoRange()


def render_persistence(plot_widget: pg.PlotWidget, y_data: np.ndarray,
                       window_size: int, offset: int, fuzz: bool,
                       ybounds: tuple):
    """Render eye diagram as a 2D colour-persistence heatmap."""
    plot_widget.clear()
    plot_widget.setBackground('k')
    plot_widget.setLabel('bottom', 'UI')
    plot_widget.setLabel('left', 'Amplitude')

    size = (480, 480)
    counts = grid_count(y_data, window_size, offset=offset, size=size,
                        fuzz=fuzz, bounds=ybounds)

    img_data = colorize(counts, (224, 192, 48))

    img = pg.ImageItem()
    img.setImage(img_data)
    img.setBorder(10)
    plot_widget.addItem(img)

    dy = ybounds[1] - ybounds[0]
    tr = QtGui.QTransform()
    tr.scale(2.0 / counts.shape[0], dy / counts.shape[1])
    tr.translate(0, counts.shape[1] * ybounds[0] / dy)
    img.setTransform(tr)

    plot_widget.getAxis('left').setGrid(192)
    plot_widget.getAxis('bottom').setGrid(192)

    metrics = compute_eye_metrics(counts, ybounds)
    _add_metrics_overlay(plot_widget, metrics)

    plot_widget.autoRange()
