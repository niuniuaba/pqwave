"""Tests for XschemCrossProbeClient — stateless, pure-Tcl TCP client."""

import socket
from unittest.mock import patch, MagicMock

from pqwave.bridge.xschem.cross_probe import XschemCrossProbeClient


def test_send_command_sends_tcl_and_reads_response():
    client = XschemCrossProbeClient(port=9999, timeout=1.0)
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [b"some_result\n", b""]

    with patch("socket.create_connection", return_value=mock_sock):
        ok, result = client.send_command("probe_net VOUT 1")

    assert ok is True
    assert result == "some_result"
    mock_sock.sendall.assert_called_once_with(b"probe_net VOUT 1\n")


def test_send_command_connection_refused():
    client = XschemCrossProbeClient(port=9999, timeout=0.1)

    with patch(
        "socket.create_connection", side_effect=ConnectionRefusedError("refused")
    ):
        ok, result = client.send_command("probe_net VOUT 1")

    assert ok is False
    assert "refused" in result


def test_probe_net_sends_correct_tcl():
    client = XschemCrossProbeClient(port=9999, timeout=1.0)

    with patch.object(client, "send_command", return_value=(True, "")) as mock_send:
        ok = client.probe_net("VOUT")

    assert ok is True
    mock_send.assert_called_once_with("probe_net VOUT 1")


def test_probe_part_with_pin():
    client = XschemCrossProbeClient(port=9999, timeout=1.0)

    with patch.object(client, "send_command", return_value=(True, "")) as mock_send:
        ok = client.probe_part("R1", pin="1")

    assert ok is True
    mock_send.assert_called_once_with("select_inst R1 1")


def test_probe_part_without_pin():
    client = XschemCrossProbeClient(port=9999, timeout=1.0)

    with patch.object(client, "send_command", return_value=(True, "")) as mock_send:
        ok = client.probe_part("R1")

    assert ok is True
    mock_send.assert_called_once_with("select_inst R1 1")


def test_clear_sends_unhilight_tcl():
    client = XschemCrossProbeClient(port=9999, timeout=1.0)

    with patch.object(client, "send_command", return_value=(True, "")) as mock_send:
        ok = client.clear()

    assert ok is True
    mock_send.assert_called_once_with("xschem unhilight_all; xschem redraw")


def test_is_connected_always_true():
    client = XschemCrossProbeClient()
    assert client.is_connected() is True


def test_connect_to_server_is_noop():
    client = XschemCrossProbeClient()
    assert client.connect_to_server() is True

