#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Color utilities for trace plotting.

Provides color palette management and color generation functions.
"""

from typing import List, Tuple
import numpy as np


# Predefined color palette (RGB tuples with values 0-255)
DEFAULT_COLOR_PALETTE: List[Tuple[int, int, int]] = [
    (255, 0, 0),      # Red
    (0, 255, 0),      # Green
    (0, 0, 255),      # Blue
    (255, 255, 0),    # Yellow
    (255, 0, 255),    # Magenta
    (0, 255, 255),    # Cyan
    (128, 0, 0),      # Maroon
    (0, 128, 0),      # Dark Green
    (0, 0, 128),      # Navy
    (128, 128, 0),    # Olive
    (128, 0, 128),    # Purple
    (0, 128, 128),    # Teal
    (192, 192, 192),  # Silver
    (128, 128, 128),  # Gray
    (255, 165, 0),    # Orange
    (147, 112, 219),  # Medium Purple
    (64, 224, 208),   # Turquoise
    (255, 192, 203),  # Pink
    (173, 216, 230),  # Light Blue
    (240, 230, 140)   # Khaki
]


class ColorManager:
    """Manages color assignment for traces with no repeats."""

    def __init__(self, palette: List[Tuple[int, int, int]] = None):
        """
        Initialize color manager.

        Args:
            palette: List of RGB tuples (0-255). If None, uses DEFAULT_COLOR_PALETTE.
        """
        self.palette = palette if palette is not None else DEFAULT_COLOR_PALETTE.copy()
        self.used_colors: List[Tuple[int, int, int]] = []
        self.color_index = 0

    def get_next_color(self) -> Tuple[int, int, int]:
        """Get the next color from the palette, ensuring no repeats.

        Returns:
            RGB tuple with values 0-255.
        """
        if self.color_index < len(self.palette):
            # Use predefined color
            color = self.palette[self.color_index]
            self.color_index += 1
        else:
            # Generate random color if palette is exhausted
            while True:
                color = (np.random.randint(0, 255),
                         np.random.randint(0, 255),
                         np.random.randint(0, 255))
                if color not in self.used_colors:
                    break
        self.used_colors.append(color)
        return color

    def reset(self) -> None:
        """Reset color management state."""
        self.used_colors.clear()
        self.color_index = 0

    def mark_color_used(self, color: Tuple[int, int, int]) -> None:
        """Mark a color as used to prevent reuse."""
        if color not in self.used_colors:
            self.used_colors.append(color)

    def is_color_used(self, color: Tuple[int, int, int]) -> bool:
        """Check if a color is already used."""
        return color in self.used_colors