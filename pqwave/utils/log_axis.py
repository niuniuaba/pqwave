#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LogAxisItem - Custom AxisItem for log scale that shows actual values instead of exponents.

This module provides a custom AxisItem subclass that improves the display of
logarithmic axis ticks by showing values as 10^exponent with superscript formatting.
"""

from pyqtgraph import AxisItem


class LogAxisItem(AxisItem):
    """Custom AxisItem for log scale that shows actual values instead of exponents"""
    def __init__(self, orientation='left', log_mode_changed_callback=None, **kwargs):
        super().__init__(orientation, **kwargs)
        self.log_mode = False
        self.log_mode_changed_callback = log_mode_changed_callback
        # Initially enable auto SI prefix (for linear mode)
        # It will be disabled when log mode is enabled
        self.enableAutoSIPrefix(True)



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
                self.enableAutoSIPrefix(False)
            else:
                self.enableAutoSIPrefix(True)

        try:
            super().setLogMode(x=x, y=y)
        except Exception:
            pass

        if new_mode is not None and new_mode != old_log_mode:
            if self.log_mode_changed_callback:
                try:
                    self.log_mode_changed_callback(self.orientation, new_mode)
                except Exception:
                    pass

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