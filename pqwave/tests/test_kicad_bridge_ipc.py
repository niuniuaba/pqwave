"""Tests for KiCadBridge IPC API connection layer."""

import pytest
from unittest.mock import MagicMock, patch

from pqwave.bridge.kicad.bridge import KiCadBridge


class TestEnsureIpc:
    """Tests for _ensure_ipc() lazy connection."""

    def test_returns_false_when_kipy_not_installed(self):
        bridge = KiCadBridge()
        with patch("pqwave.bridge.kicad.bridge._KIPY_AVAILABLE", False):
            result = bridge._ensure_ipc()
        assert result is False
        assert bridge._ipc_available is False

    def test_returns_false_when_get_schematic_missing(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kicad = MagicMock()
        # get_schematic not present
        del mock_kicad.get_schematic
        mock_kipy.KiCad.return_value = mock_kicad

        with patch("pqwave.bridge.kicad.bridge._KIPY_AVAILABLE", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                result = bridge._ensure_ipc()
        assert result is False

    def test_connects_and_caches_on_success(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kicad = MagicMock()
        mock_kicad.get_schematic = MagicMock()  # hasattr passes
        mock_kipy.KiCad.return_value = mock_kicad

        with patch("pqwave.bridge.kicad.bridge._KIPY_AVAILABLE", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                result = bridge._ensure_ipc()

        assert result is True
        assert bridge._ipc_available is True
        assert bridge._kipy_kicad is mock_kicad
        mock_kipy.KiCad.assert_called_once()

    def test_reuses_cached_connection(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kicad = MagicMock()
        mock_kicad.get_schematic = MagicMock()
        mock_kipy.KiCad.return_value = mock_kicad

        with patch("pqwave.bridge.kicad.bridge._KIPY_AVAILABLE", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                bridge._ensure_ipc()
                bridge._ensure_ipc()

        # KiCad constructor called only once
        assert mock_kipy.KiCad.call_count == 1

    def test_reconnects_after_connection_lost(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kicad1 = MagicMock()
        mock_kicad1.get_schematic = MagicMock()
        mock_kicad2 = MagicMock()
        mock_kicad2.get_schematic = MagicMock()
        mock_kipy.KiCad.side_effect = [mock_kicad1, mock_kicad2]

        with patch("pqwave.bridge.kicad.bridge._KIPY_AVAILABLE", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                bridge._ensure_ipc()
                # Simulate connection check failure
                bridge._kipy_kicad = None
                bridge._ipc_available = None
                result = bridge._ensure_ipc()

        assert result is True
        assert mock_kipy.KiCad.call_count == 2

    def test_connection_error_sets_ipc_failed(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kipy.KiCad.side_effect = Exception("Connection refused")

        with patch("pqwave.bridge.kicad.bridge._KIPY_AVAILABLE", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                result = bridge._ensure_ipc()

        assert result is False
        assert bridge._ipc_available is False

    def test_ipc_available_property_when_connected(self):
        bridge = KiCadBridge()
        bridge._ipc_available = True
        assert bridge._ipc_available is True

    def test_ipc_available_property_when_unchecked(self):
        bridge = KiCadBridge()
        bridge._ipc_available = None
        assert bridge._ipc_available is None
