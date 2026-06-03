"""Tests for IPC-based IpcProbeClient."""

from unittest.mock import MagicMock
from pqwave.bridge.kicad.cross_probe import IpcProbeClient


class TestIpcProbeClient:
    """Tests for IPC-based probe client."""

    def test_initial_state_not_connected(self):
        client = IpcProbeClient()
        assert not client.is_connected()

    def test_set_kicad_instance(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        client.set_kicad(mock_kicad)
        assert client.is_connected()

    def test_probe_net_calls_run_action(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        mock_kicad.run_action.return_value = MagicMock(status=1)
        client.set_kicad(mock_kicad)

        result = client.probe_net("R1")

        assert result is True
        mock_kicad.run_action.assert_called_once()

    def test_probe_net_when_not_connected(self):
        client = IpcProbeClient()
        result = client.probe_net("R1")
        assert result is False

    def test_probe_part_calls_run_action(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        mock_kicad.run_action.return_value = MagicMock(status=1)
        client.set_kicad(mock_kicad)

        result = client.probe_part("Q1")

        assert result is True

    def test_clear_probe(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        mock_kicad.run_action.return_value = MagicMock(status=1)
        client.set_kicad(mock_kicad)

        result = client.clear()

        assert result is True
        mock_kicad.run_action.assert_called_once()

    def test_disconnect_clears_kicad_ref(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        client.set_kicad(mock_kicad)
        client.disconnect()

        assert not client.is_connected()
        assert client._kicad is None

    def test_connected_signal_emitted(self):
        client = IpcProbeClient()
        signal_received = []
        client.connected.connect(lambda: signal_received.append(True))

        client.set_kicad(MagicMock())

        assert len(signal_received) == 1

    def test_disconnected_signal_emitted(self):
        client = IpcProbeClient()
        signal_received = []
        client.disconnected.connect(lambda: signal_received.append(True))
        client.set_kicad(MagicMock())
        client.disconnect()

        assert len(signal_received) == 1

    def test_error_signal_on_failed_probe(self):
        client = IpcProbeClient()
        errors = []
        client.error_occurred.connect(errors.append)
        # No set_kicad — simulate a missing/unset IPC connection

        result = client.probe_net("R1")

        assert result is False
        assert len(errors) == 1
        assert "Not connected" in errors[0]
