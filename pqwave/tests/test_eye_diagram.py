"""Unit tests for the eye diagram feature.

Covers:
  - EyeDiagramConfig serialization round-trip
  - colorize() function edge cases
"""

import numpy as np
import pytest
from pqwave.models.state import EyeDiagramConfig
from pqwave.digital.eye_renderer import colorize


class TestEyeDiagramConfig:
    """Serialisation round-trip tests."""

    def test_defaults(self):
        cfg = EyeDiagramConfig()
        assert cfg.window_size == 48
        assert cfg.offset == 16
        assert cfg.fuzz is True
        assert cfg.mode == "persistence"

    def test_to_dict_round_trip(self):
        cfg = EyeDiagramConfig(
            window_size=64, offset=32, fuzz=False, mode="overlay")
        data = cfg.to_dict()
        restored = EyeDiagramConfig.from_dict(data)
        assert restored.window_size == 64
        assert restored.offset == 32
        assert restored.fuzz is False
        assert restored.mode == "overlay"

    def test_from_dict_missing_keys(self):
        restored = EyeDiagramConfig.from_dict({})
        assert restored.window_size == 48
        assert restored.offset == 16
        assert restored.fuzz is True
        assert restored.mode == "persistence"

    def test_from_dict_partial(self):
        restored = EyeDiagramConfig.from_dict({"window_size": 100})
        assert restored.window_size == 100
        assert restored.offset == 16
        assert restored.fuzz is True
        assert restored.mode == "persistence"


class TestColorize:
    """Unit tests for the colorize() helper."""

    def test_empty_grid(self):
        counts = np.zeros((10, 10), dtype=np.int32)
        img = colorize(counts, (100, 150, 200))
        assert img.shape == (10, 10, 4)
        assert img.dtype == np.uint8
        np.testing.assert_array_equal(img[..., 3], 0)

    def test_uniform_counts(self):
        counts = np.ones((5, 5), dtype=np.int32)
        img = colorize(counts, (0, 128, 255))
        assert img.shape == (5, 5, 4)
        assert (img[..., 3] == 255).all()

    def test_single_pixel_count(self):
        counts = np.array([[3]], dtype=np.int32)
        img = colorize(counts, (0, 0, 0))
        assert img.shape == (1, 1, 4)
        assert img[0, 0, 3] == 255

    def test_color_gradient(self):
        """count=1 maps to color1; count=max maps to color2."""
        counts = np.array([[1, 5]], dtype=np.int32)
        color1 = (50, 100, 150)
        color2 = (200, 210, 220)
        img = colorize(counts, color1, color2)
        np.testing.assert_array_equal(img[0, 1, :3], color2)
        assert img[0, 0, 3] == 255

    def test_default_color2_is_white(self):
        counts = np.array([[0, 1]], dtype=np.int32)
        img = colorize(counts, (0, 0, 0))
        assert img[0, 1, 3] == 255
        np.testing.assert_array_equal(img[0, 1, :3], [255, 255, 255])
