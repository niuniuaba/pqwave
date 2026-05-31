import os
import socket
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from pqwave.bridge.xschem.cross_probe import (
    XschemCrossProbeClient,
    check_tcl_server,
    deploy_tcl_server,
    _get_tcl_target_path,
    _get_xschem_config_dir,
    _get_xschemrc_path,
)


class TestDeployment:
    def test_get_config_dir(self):
        with patch.dict(os.environ, {"HOME": "/home/testuser"}):
            assert _get_xschem_config_dir() == "/home/testuser/.config/xschem"

    def test_get_xschemrc_path(self):
        with patch.dict(os.environ, {"HOME": "/home/testuser"}):
            assert _get_xschemrc_path() == "/home/testuser/.xschem/xschemrc"

    def test_check_tcl_server_not_installed(self):
        with patch("os.path.exists", return_value=False):
            result = check_tcl_server()
            assert result["installed"] is False
            assert result["needs_deploy"] is True

    def test_check_tcl_server_installed_no_xschemrc_line(self):
        with patch("os.path.exists") as mock_exists, \
             patch("builtins.open", MagicMock()) as mock_open:
            mock_exists.return_value = True
            mock_file = MagicMock()
            mock_file.read.return_value = "# just comments\n"
            mock_open.return_value.__enter__.return_value = mock_file

            result = check_tcl_server()
            assert result["installed"] is False
            assert result["server_script_ok"] is True
            assert result["xschemrc_configured"] is False

    def test_check_tcl_server_fully_installed(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", MagicMock()) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = "lappend tcl_files ~/.config/xschem/pqwave-server.tcl\n"
            mock_open.return_value.__enter__.return_value = mock_file

            result = check_tcl_server()
            assert result["installed"] is True


class TestCrossProbeClient:
    def test_probe_net_sends_command(self):
        client = XschemCrossProbeClient(port=9999)
        mock_sock = MagicMock()
        client._sock = mock_sock
        result = client.probe_net("Vout")
        assert result is True
        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        assert b'$NET: "Vout"' in sent_data

    def test_probe_part_sends_command(self):
        client = XschemCrossProbeClient(port=9999)
        mock_sock = MagicMock()
        client._sock = mock_sock
        result = client.probe_part("Q1")
        assert result is True
        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        assert b'$PART: "Q1"' in sent_data

    def test_clear_sends_command(self):
        client = XschemCrossProbeClient(port=9999)
        mock_sock = MagicMock()
        client._sock = mock_sock
        result = client.clear()
        assert result is True
        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        assert b"$CLEAR" in sent_data

    def test_send_when_not_connected_emits_error(self, qtbot):
        client = XschemCrossProbeClient(port=9999)
        with qtbot.waitSignal(client.error_occurred, timeout=1000) as blocker:
            result = client.probe_net("Vout")
        assert result is False

    def test_connect_refused_emits_error(self, qtbot):
        client = XschemCrossProbeClient(port=1, timeout=0.5)
        with qtbot.waitSignal(client.error_occurred, timeout=2000):
            client.connect_to_server()
