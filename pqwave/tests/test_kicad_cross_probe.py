"""Tests for KiCad CrossProbeClient."""

import socket
from unittest.mock import MagicMock, patch

from pqwave.bridge.kicad.cross_probe import CrossProbeClient


class TestCrossProbeClient:
    def test_initial_state_not_connected(self):
        client = CrossProbeClient()
        assert not client.is_connected()

    def test_connect_to_kicad_success(self):
        client = CrossProbeClient(port=4243)
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_connect.return_value = mock_sock
            result = client.connect_to_kicad()
            assert result is True
            mock_connect.assert_called_once_with(("localhost", 4243), timeout=2.0)
            assert client.is_connected()

    def test_connect_to_kicad_refused(self):
        client = CrossProbeClient(port=9999)
        with patch("socket.create_connection") as mock_connect:
            mock_connect.side_effect = ConnectionRefusedError("refused")
            result = client.connect_to_kicad()
            assert result is False
            assert not client.is_connected()

    def test_connect_timeout(self):
        client = CrossProbeClient(port=4243)
        with patch("socket.create_connection") as mock_connect:
            mock_connect.side_effect = socket.timeout("timeout")
            result = client.connect_to_kicad()
            assert result is False

    def test_probe_net_when_not_connected(self):
        client = CrossProbeClient()
        result = client.probe_net("R1")
        assert result is False

    def test_probe_net_when_connected(self):
        client = CrossProbeClient()
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_connect.return_value = mock_sock
            client.connect_to_kicad()
            result = client.probe_net("R1")
            assert result is True
            mock_sock.sendall.assert_called_once()
            sent = mock_sock.sendall.call_args[0][0]
            assert b'$NET: "R1"' in sent

    def test_probe_part_with_pin(self):
        client = CrossProbeClient()
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_connect.return_value = mock_sock
            client.connect_to_kicad()
            client.probe_part("U1", pin="3")
            sent = mock_sock.sendall.call_args[0][0]
            assert b'$PART: "U1" $PAD: "3"' in sent

    def test_probe_part_without_pin(self):
        client = CrossProbeClient()
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_connect.return_value = mock_sock
            client.connect_to_kicad()
            client.probe_part("Q1")
            sent = mock_sock.sendall.call_args[0][0]
            assert b'$PART: "Q1"' in sent

    def test_clear_command(self):
        client = CrossProbeClient()
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_connect.return_value = mock_sock
            client.connect_to_kicad()
            client.clear()
            sent = mock_sock.sendall.call_args[0][0]
            assert b"$CLEAR" in sent

    def test_disconnect_cleans_up(self):
        client = CrossProbeClient()
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_connect.return_value = mock_sock
            client.connect_to_kicad()
            client.disconnect()
            assert not client.is_connected()
            mock_sock.close.assert_called_once()

    def test_send_failure_disconnects(self):
        client = CrossProbeClient()
        with patch("socket.create_connection") as mock_connect:
            mock_sock = MagicMock()
            mock_sock.sendall.side_effect = OSError("broken pipe")
            mock_connect.return_value = mock_sock
            client.connect_to_kicad()
            result = client.send_command("test")
            assert result is False
            assert not client.is_connected()
