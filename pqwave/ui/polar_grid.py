"""Polar grid renderer: concentric rings and radial lines for polar plots."""

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsPathItem


def render_polar_grid(
    plot_widget: pg.PlotWidget,
    n_rings: int = 5,
    n_radials: int = 12,
    max_radius: float = 1.0,
    log_scale: bool = False,
) -> list[QGraphicsPathItem]:
    """Add a polar reference grid to a PlotWidget.

    Renders *n_rings* concentric circles and *n_radials* radial lines.
    The grid is static (rendered once) and uses QPainterPath.

    Parameters
    ----------
    plot_widget:
        The PlotWidget to add grid items to.
    n_rings:
        Number of concentric magnitude rings (default 5).
    n_radials:
        Number of radial phase lines (default 12, every 30 degrees).
    max_radius:
        Outer ring radius (default 1.0).
    log_scale:
        If True, rings are log-spaced.

    Returns:
        List of added QGraphicsPathItems (for later removal on re-invocation).
    """
    grid_pen = QPen(QColor(60, 60, 60), 1)
    radial_pen = QPen(QColor(50, 50, 50), 1, pg.QtCore.Qt.PenStyle.DashLine)
    items: list[QGraphicsPathItem] = []

    # Concentric rings
    if log_scale and max_radius > 0:
        ring_radii = np.logspace(-1, math.log10(max_radius), n_rings)
    else:
        ring_radii = np.linspace(max_radius / n_rings, max_radius, n_rings)

    for r in ring_radii:
        path = QPainterPath()
        path.addEllipse(-r, -r, 2 * r, 2 * r)
        item = QGraphicsPathItem(path)
        item.setPen(grid_pen)
        plot_widget.addItem(item)
        items.append(item)

    # Radial lines
    for i in range(n_radials):
        angle = 2 * math.pi * i / n_radials
        x = max_radius * math.cos(angle)
        y = max_radius * math.sin(angle)
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(x, y)
        item = QGraphicsPathItem(path)
        item.setPen(radial_pen)
        plot_widget.addItem(item)
        items.append(item)

    # Outer boundary circle (slightly bolder)
    outer_pen = QPen(QColor(80, 80, 80), 1.5)
    path = QPainterPath()
    path.addEllipse(-max_radius, -max_radius, 2 * max_radius, 2 * max_radius)
    item = QGraphicsPathItem(path)
    item.setPen(outer_pen)
    plot_widget.addItem(item)
    items.append(item)

    return items
