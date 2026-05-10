"""DigitalStepCurveItem — pyqtgraph GraphicsObject for digital timing diagrams.

Renders logic signals as step functions with separate colors for high, low,
and unknown states.  Designed for the pqwave parallel rendering path:
analog traces use _StaticCurveItem, digital traces use this class.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui
from typing import Optional, Tuple

from pqwave.digital.threshold_config import (
    DIGITAL_HIGH_COLOR,
    DIGITAL_LOW_COLOR,
    DIGITAL_UNKNOWN_COLOR,
)

BUS_COLOR = (0, 180, 255)  # bright blue for bus indicator line


def _to_qt_color(rgb: Tuple[int, int, int]) -> QtGui.QColor:
    return QtGui.QColor(rgb[0], rgb[1], rgb[2])


HIGH_PEN = QtGui.QPen(_to_qt_color(DIGITAL_HIGH_COLOR), 1.5)
LOW_PEN = QtGui.QPen(_to_qt_color(DIGITAL_LOW_COLOR), 1.5)
UNKNOWN_PEN = QtGui.QPen(_to_qt_color(DIGITAL_UNKNOWN_COLOR), 1.0, QtCore.Qt.PenStyle.DashLine)
BUS_PEN = QtGui.QPen(_to_qt_color(BUS_COLOR), 1.5)


class DigitalStepCurveItem(pg.GraphicsObject):
    """Renders a single digital logic signal as a step-function timing diagram.

    Stores pre-computed step vertices (time, level) produced by
    digital_renderer.threshold_and_step().  On paint, builds separate
    QPainterPath segments for high (1), low (0), and unknown (Z/X) states.

    The boundingRect is cached and only recomputed on setData(), matching
    the _StaticCurveItem pattern.
    """

    def __init__(self, times: Optional[np.ndarray] = None,
                 levels: Optional[np.ndarray] = None, y_offset: float = 0.0,
                 is_bus: bool = False):
        super().__init__()
        self._times = np.array([]) if times is None else times
        self._levels = np.array([]) if levels is None else levels
        self.y_offset = y_offset
        self.is_bus = is_bus
        self.opts = {'pen': BUS_PEN if is_bus else HIGH_PEN}
        self._cached_paths: Optional[tuple] = None

    def setData(self, times: np.ndarray, levels: np.ndarray) -> None:
        """Update the step waveform data.  Mirrors PlotCurveItem.setData()."""
        self._times = np.asarray(times, dtype=np.float64)
        self._levels = np.asarray(levels, dtype=np.float64)
        self._cached_paths = None
        self.prepareGeometryChange()
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtGui.QStyleOptionGraphicsItem,
              widget: Optional[QtGui.QWidget] = None) -> None:
        """Draw the step waveform using separate paths per logic level."""
        if len(self._times) < 2:
            return

        painter.save()
        painter.translate(0.0, self.y_offset)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        if self._cached_paths is None:
            self._cached_paths = self._build_paths()
        high_path, low_path, unk_path, bus_path = self._cached_paths

        if not high_path.isEmpty():
            painter.setPen(HIGH_PEN)
            painter.drawPath(high_path)
        if not low_path.isEmpty():
            painter.setPen(LOW_PEN)
            painter.drawPath(low_path)
        if not unk_path.isEmpty():
            painter.setPen(UNKNOWN_PEN)
            painter.drawPath(unk_path)
        if not bus_path.isEmpty():
            painter.setPen(BUS_PEN)
            painter.drawPath(bus_path)
        painter.restore()

    def dataBounds(self, axis: int = 0, **kwargs):
        """Return data bounds for auto-range.

        axis=0 → (x_min, x_max), axis=1 → (y_min, y_max).
        """
        if len(self._times) == 0 or len(self._levels) == 0:
            return None
        if np.all(np.isnan(self._levels)):
            return None
        x_min, x_max = float(self._times[0]), float(self._times[-1])
        l_min = float(np.nanmin(self._levels)) + self.y_offset
        l_max = float(np.nanmax(self._levels)) + self.y_offset
        if l_min == l_max:
            l_min -= 0.5
            l_max += 0.5
        if axis == 0:
            return (x_min, x_max)
        return (l_min, l_max)

    def boundingRect(self) -> QtCore.QRectF:
        n = len(self._times)
        if n == 0 or len(self._levels) == 0:
            return QtCore.QRectF()
        if np.all(np.isnan(self._levels)):
            return QtCore.QRectF()
        t_min, t_max = self._times[0], self._times[-1]
        l_min = float(np.nanmin(self._levels)) + self.y_offset
        l_max = float(np.nanmax(self._levels)) + self.y_offset
        if l_min == l_max:
            l_max = l_min + 1.0
        return QtCore.QRectF(
            t_min, l_min - 0.1, max(t_max - t_min, 1e-12), l_max - l_min + 0.2
        )

    def _build_paths(self):
        """Build QPainterPath objects for high, low, unknown, and bus segments."""
        times = self._times
        levels = self._levels
        n = len(times)

        high_path = QtGui.QPainterPath()
        low_path = QtGui.QPainterPath()
        unk_path = QtGui.QPainterPath()
        bus_path = QtGui.QPainterPath()

        for i in range(n - 1):
            t_i, t_next = times[i], times[i + 1]
            lvl, lvl_next = levels[i], levels[i + 1]

            if self.is_bus:
                path = bus_path
            elif lvl >= 1.0:
                path = high_path
            elif lvl <= 0.0:
                path = low_path
            else:
                path = unk_path

            path.moveTo(t_i, lvl)
            path.lineTo(t_next, lvl)

            if abs(lvl_next - lvl) > 0.1:
                path.moveTo(t_next, lvl)
                path.lineTo(t_next, lvl_next)

        return high_path, low_path, unk_path, bus_path
