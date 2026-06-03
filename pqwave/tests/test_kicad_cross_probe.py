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

    def _make_kiid(self, value="12345678-1234-1234-1234-123456789abc"):
        """Create a real KIID protobuf object."""
        from kipy.proto.common.types import KIID
        kiid = KIID()
        kiid.value = value
        return kiid

    def test_probe_net_resolves_name_to_kiids(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()

        mock_net = MagicMock()
        mock_net.name = "R1"
        mock_net_sheet = MagicMock()
        mock_net_sheet.items = [self._make_kiid()]
        mock_net.sheets = [mock_net_sheet]
        mock_sch = MagicMock()
        mock_sch.get_netlist.return_value = [mock_net]
        mock_kicad.get_schematic.return_value = mock_sch
        mock_kicad._client = MagicMock()

        client.set_kicad(mock_kicad)
        result = client.probe_net("R1")

        assert result is True
        assert mock_kicad._client.send.call_count == 2

    def test_probe_net_not_found(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        mock_sch = MagicMock()
        mock_sch.get_netlist.return_value = [MagicMock(name="OTHER")]
        mock_kicad.get_schematic.return_value = mock_sch
        mock_kicad._client = MagicMock()

        client.set_kicad(mock_kicad)
        result = client.probe_net("R1")

        assert result is False

    def test_probe_net_when_not_connected(self):
        client = IpcProbeClient()
        result = client.probe_net("R1")
        assert result is False

    def test_probe_part_resolves_refdes_to_kiid(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()

        mock_sym = MagicMock()
        mock_sym.reference_field.text = "Q1"
        mock_sym.id = self._make_kiid()
        mock_sch = MagicMock()
        mock_sch.get_symbols.return_value = [mock_sym]
        mock_kicad.get_schematic.return_value = mock_sch
        mock_kicad._client = MagicMock()

        client.set_kicad(mock_kicad)
        result = client.probe_part("Q1")

        assert result is True
        assert mock_kicad._client.send.call_count == 2

    def test_clear_probe_sends_clear_selection(self):
        client = IpcProbeClient()
        mock_kicad = MagicMock()
        mock_kicad._client = MagicMock()
        client.set_kicad(mock_kicad)

        result = client.clear()

        assert result is True
        mock_kicad._client.send.assert_called_once()

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
