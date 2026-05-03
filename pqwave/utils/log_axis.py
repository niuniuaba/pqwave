#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LogAxisItem - Custom AxisItem for log scale that shows actual values instead of exponents.

This module provides a custom AxisItem subclass that improves the display of
logarithmic axis ticks by showing values as 10^exponent with superscript formatting.
It also overrides grid-line rendering to use a dashed pen style, reducing
visual interference with traces.
"""

from pyqtgraph import AxisItem
from PyQt6.QtGui import QPen
from PyQt6.QtCore import Qt


class LogAxisItem(AxisItem):
    """Custom AxisItem for log scale that shows actual values instead of exponents"""

    def __init__(self, orientation='left', log_mode_changed_callback=None, **kwargs):
        super().__init__(orientation, **kwargs)
        self.log_mode = False
        self._db_mode = False
        self.log_mode_changed_callback = log_mode_changed_callback
        # Initially enable auto SI prefix (for linear mode)
        # It will be disabled when log mode is enabled
        self.enableAutoSIPrefix(True)

    def setDbMode(self, enabled: bool) -> None:
        """Enable/disable dB suffix on tick labels."""
        self._db_mode = enabled

    def isDbMode(self) -> bool:
        """Return whether dB suffix is enabled."""
        return self._db_mode

    def generateDrawSpecs(self, p):
        """Override to render grid lines with dash-line style."""
        specs = super().generateDrawSpecs(p)
        if specs is None:
            return None
        axisSpec, tickSpecs, textSpecs = specs
        # When grid is active, all ticks are full-width grid lines.
        # Replace their pen style with DashLine to reduce visual interference.
        if self.grid is not False and tickSpecs:
            new_specs = []
            for pen, p1, p2 in tickSpecs:
                dash_pen = QPen(pen)
                dash_pen.setStyle(Qt.PenStyle.DashLine)
                new_specs.append((dash_pen, p1, p2))
            tickSpecs = new_specs
        return (axisSpec, tickSpecs, textSpecs)

    def _safe_enable_auto_si_prefix(self, enable: bool) -> None:
        """Wrap enableAutoSIPrefix to avoid crash when label C++ object is deleted."""
        try:
            self.enableAutoSIPrefix(enable)
        except RuntimeError:
            pass

    def setLogMode(self, x=None, y=None):
        """Set log mode for this axis"""
        old_log_mode = self.log_mode

        if self.orientation in ['left', 'right'] and y is not None:
            self.log_mode = y
        elif self.orientation == 'bottom' and x is not None:
            self.log_mode = x

        new_mode = y if self.orientation in ['left', 'right'] else x
        if new_mode is not None:
            if new_mode:
                self._safe_enable_auto_si_prefix(False)
            else:
                self._safe_enable_auto_si_prefix(True)

        # Prevent super().setLogMode() from setting the linked ViewBox to
        # log mode. Data is pre-transformed to log10 space by TraceManager,
        # so the ViewBox must stay in linear mode — otherwise the ViewBox
        # applies its own log transform on top, causing double-log corruption
        # and range oscillation.
        linked_view_backup = self._linkedView
        self._linkedView = None
        try:
            super().setLogMode(x=x, y=y)
        except Exception:
            pass
        finally:
            self._linkedView = linked_view_backup

        if new_mode is not None and new_mode != old_log_mode:
            if self.log_mode_changed_callback:
                try:
                    self.log_mode_changed_callback(self.orientation, new_mode)
                except Exception:
                    pass

    # Reasonable bounds for log10-exponent ticks. In pqwave, the ViewBox
    # coordinate space holds log10-transformed values (e.g. 3.0 for 1000).
    # Real-world SPICE data rarely exceeds 10^-20 to 10^+20.  Clamping
    # prevents unbounded tick generation when linear-range data (0 to
    # millions) temporarily reaches this method before log10 transform.
    _MIN_EXPONENT = -20
    _MAX_EXPONENT = 20

    def logTickValues(self, minVal, maxVal, size, stdTicks):
        """Return decade ticks at integer exponent positions.

        Skips decades when the range is very wide or the axis is too narrow
        to fit all labels without overlap.  Targets roughly 60 px minimum
        between adjacent labels.
        """
        from math import floor, ceil, isfinite
        v1 = int(floor(minVal)) if isfinite(minVal) else self._MIN_EXPONENT
        v2 = int(ceil(maxVal)) if isfinite(maxVal) else self._MAX_EXPONENT
        v1 = max(v1, self._MIN_EXPONENT)
        v2 = min(v2, self._MAX_EXPONENT)
        v1 = min(v1, v2)
        n_decades = v2 - v1
        # Keep at most ~12 labeled decades to avoid clustering
        step = max(1, (n_decades + 11) // 12) if n_decades > 0 else 1
        # Pixel-aware: increase step if axis is too narrow for all labels.
        # Target at least 60 px between adjacent decade labels.
        if n_decades > 1 and size > 0:
            px_per_label = float(size) / float(n_decades)
            while px_per_label * step < 60.0 and step * 2 <= n_decades:
                step += 1
        major = [float(v) for v in range(v1, v2 + 1, step)]
        # Ensure the last decade is always present when step skips it
        if major and float(v2) not in major:
            major.append(float(v2))
        return [(float(step), major)]

    def tickStrings(self, values, scale, spacing):
        """Convert tick values to strings"""
        strings = []
        for v in values:
            if self.log_mode:
                formatted = self._format_exponent_with_superscript(v)
                strings.append(formatted)
            else:
                default_str = super().tickStrings([v], scale, spacing)[0]
                strings.append(default_str)
        if self._db_mode:
            strings = [s + " dB" for s in strings]
        return strings

    def _format_exponent_with_superscript(self, exponent):
        """Format exponent with superscript characters

        Examples:
        1.0 -> "10¹"
        2.0 -> "10²"
        -1.0 -> "10⁻¹"
        1.5 -> "10¹·⁵"
        -2.3 -> "10⁻²·³"
        """
        # Round to reasonable precision
        if abs(exponent) < 0.001:
            exponent_str = "0"
        elif abs(exponent - round(exponent)) < 0.001:
            # Integer exponent
            exponent_str = str(int(round(exponent)))
        else:
            # Decimal exponent, round to 1 decimal place
            exponent_str = f"{exponent:.1f}"

        # Convert to superscript
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
            '-': '⁻', '.': '·'
        }

        superscript_str = ''.join(superscript_map.get(ch, ch) for ch in exponent_str)

        return f"10{superscript_str}"
