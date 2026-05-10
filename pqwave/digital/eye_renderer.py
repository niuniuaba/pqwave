"""Eye diagram rendering.

Overlay mode slices raw analog data into windows and overdraws each
window as a translucent trace (same approach as eyediagram.mpl.eyediagram_lines).

Persistence mode computes a 2D count grid via eyediagram.core.grid_count()
and displays it as a colour heatmap via pg.ImageItem.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtGui

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


def render_overlay(plot_widget: pg.PlotWidget, y_data: np.ndarray,
                   window_size: int, offset: int):
    """Render eye diagram as overlaid waveform windows (raw analog)."""
    plot_widget.clear()
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

    plot_widget.autoRange()


def render_persistence(plot_widget: pg.PlotWidget, y_data: np.ndarray,
                       window_size: int, offset: int, fuzz: bool,
                       ybounds: tuple):
    """Render eye diagram as a 2D colour-persistence heatmap."""
    plot_widget.clear()
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
    plot_widget.autoRange()
