#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LogAxisItem - Custom AxisItem for log scale that shows actual values instead of exponents.

This module provides a custom AxisItem subclass that improves the display of
logarithmic axis ticks by showing values as 10^exponent with superscript formatting.
"""

from pyqtgraph import AxisItem
from pqwave.logging_config import get_logger

logger = get_logger(__name__)


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
        """Set log mode for this axis

        Args:
            x: Whether X-axis is in log mode (for bottom axis)
            y: Whether Y-axis is in log mode (for left/right axis)
        """
        logger.debug(f"\n=== LogAxisItem.setLogMode called: orientation={self.orientation}, x={x}, y={y} ===")

        # Store old log mode for comparison
        old_log_mode = self.log_mode

        # Update log_mode based on orientation
        if self.orientation in ['left', 'right'] and y is not None:
            self.log_mode = y
            logger.debug(f"  Updated log_mode from {old_log_mode} to: {y} (Y-axis)")
        elif self.orientation == 'bottom' and x is not None:
            self.log_mode = x
            logger.debug(f"  Updated log_mode from {old_log_mode} to: {x} (X-axis)")

        # Enable/disable auto SI prefix based on log mode
        # For log mode, disable auto SI prefix (we show exponents directly)
        # For linear mode, enable auto SI prefix for large/small numbers
        new_mode = y if self.orientation in ['left', 'right'] else x
        if new_mode is not None:
            if new_mode:  # Log mode
                self.enableAutoSIPrefix(False)
                logger.debug(f"  Disabled auto SI prefix for log mode")
            else:  # Linear mode
                self.enableAutoSIPrefix(True)
                logger.debug(f"  Enabled auto SI prefix for linear mode")

        # Also call parent's setLogMode to ensure pyqtgraph internal state is updated
        try:
            super().setLogMode(x=x, y=y)
            logger.debug(f"  Called parent setLogMode")
        except Exception as e:
            logger.debug(f"  Parent setLogMode failed: {e}")

        # If log mode changed, call callback if provided
        if new_mode is not None and new_mode != old_log_mode:
            logger.debug(f"  Log mode changed from {old_log_mode} to {new_mode}")
            if self.log_mode_changed_callback:
                logger.debug(f"  Calling log_mode_changed_callback with orientation={self.orientation}, log_mode={new_mode}")
                try:
                    self.log_mode_changed_callback(self.orientation, new_mode)
                except Exception as e:
                    logger.debug(f"  Callback failed: {e}")

    def tickStrings(self, values, scale, spacing):
        """Convert tick values to strings"""
        logger.debug(f"\n=== LogAxisItem.tickStrings ===")
        logger.debug(f"  orientation: {self.orientation}")
        logger.debug(f"  log_mode: {self.log_mode}")
        logger.debug(f"  values: {values}")

        strings = []
        for v in values:
            if self.log_mode:
                # For log scale, show 10^v with superscript exponent
                logger.debug(f"  Processing value v={v}")

                # Format exponent with superscript
                formatted = self._format_exponent_with_superscript(v)
                strings.append(formatted)
                logger.debug(f"    Formatted as: '{formatted}'")
            else:
                # For linear scale, use default formatting
                default_str = super().tickStrings([v], scale, spacing)[0]
                strings.append(default_str)
                logger.debug(f"  Linear mode: v={v} -> '{default_str}'")

        logger.debug(f"  Returning strings: {strings}")
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