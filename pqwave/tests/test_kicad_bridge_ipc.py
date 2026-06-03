"""Tests for KiCadBridge IPC API connection layer."""

import pytest
from unittest.mock import MagicMock, mock_open, patch, PropertyMock

from pqwave.bridge.kicad.bridge import KiCadBridge


class TestEnsureIpc:
    """Tests for _ensure_ipc() lazy connection."""

    def test_raises_runtime_error_when_kipy_not_installed(self):
        bridge = KiCadBridge()
        with patch("pqwave.bridge.kicad.bridge._kipy_available", False):
            with pytest.raises(RuntimeError, match="kicad-python"):
                bridge._ensure_ipc()

    def test_returns_false_when_get_schematic_missing(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()

        # Use spec=[] so only explicitly set attrs exist — get_schematic
        # is NOT set on the instance, so accessing it will raise AttributeError.
        mock_kicad_class = MagicMock()
        mock_kicad_instance = MagicMock(spec=[])
        mock_kicad_class.return_value = mock_kicad_instance
        mock_kipy.KiCad = mock_kicad_class

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                result = bridge._ensure_ipc()
        assert result is False

    def test_connects_and_caches_on_success(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kicad = MagicMock()
        mock_kicad.get_schematic = MagicMock()  # hasattr passes
        mock_kipy.KiCad.return_value = mock_kicad

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
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

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
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

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
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

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                result = bridge._ensure_ipc()

        assert result is False
        assert bridge._ipc_available is False

    def test_connection_error_returns_false_not_raises(self):
        """Connection failures should gracefully return False, not raise."""
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kipy.KiCad.side_effect = Exception("Connection refused")

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                result = bridge._ensure_ipc()

        assert result is False
        assert bridge._ipc_failed is True

    def test_ipc_available_property_when_connected(self):
        bridge = KiCadBridge()
        bridge._ipc_available = True
        assert bridge._ipc_available is True

    def test_ipc_available_property_when_unchecked(self):
        bridge = KiCadBridge()
        bridge._ipc_available = None
        assert bridge._ipc_available is None

    def test_uses_kicad_api_socket_env_var(self):
        bridge = KiCadBridge()
        mock_kipy = MagicMock()
        mock_kicad = MagicMock()
        mock_kicad.get_schematic = MagicMock()
        mock_kipy.KiCad.return_value = mock_kicad

        with patch("pqwave.bridge.kicad.bridge._kipy_available", True):
            with patch.dict("sys.modules", {"kipy": mock_kipy}):
                with patch.dict("os.environ", {"KICAD_API_SOCKET": "/custom/path/api.sock"}):
                    bridge._ensure_ipc()

        # Connection should have been called with the custom socket path
        call_kwargs = mock_kipy.KiCad.call_args
        socket_arg = (
            call_kwargs[1].get("socket_path", call_kwargs[0][0] if call_kwargs[0] else None)
        )
        assert "/custom/path/api.sock" in str(socket_arg)


class TestDisconnectIpc:
    """Tests for _disconnect_ipc() cleanup."""

    def test_disconnect_closes_kicad_instance(self):
        bridge = KiCadBridge()
        mock_kicad = MagicMock()
        bridge._kipy_kicad = mock_kicad
        bridge._ipc_available = True
        bridge._ipc_failed = False

        bridge._disconnect_ipc()

        assert bridge._kipy_kicad is None
        assert bridge._ipc_available is None
        assert bridge._ipc_failed is False
        mock_kicad.close.assert_called_once()

    def test_disconnect_handles_close_error_gracefully(self):
        bridge = KiCadBridge()
        mock_kicad = MagicMock()
        mock_kicad.close.side_effect = Exception("socket already closed")
        bridge._kipy_kicad = mock_kicad

        bridge._disconnect_ipc()  # should not raise

        assert bridge._kipy_kicad is None

    def test_disconnect_when_not_connected_is_noop(self):
        bridge = KiCadBridge()
        bridge._kipy_kicad = None

        bridge._disconnect_ipc()  # should not raise

        assert bridge._kipy_kicad is None


class TestIpcExportNetlist:
    """Tests for IPC-based netlist export with kicad-cli fallback."""

    def test_export_via_ipc_when_connected(self):
        bridge = KiCadBridge()
        bridge._ipc_available = True
        mock_sch = MagicMock()
        mock_result = MagicMock()
        mock_result.succeeded = True
        mock_result.output_path = ["/tmp/test.cir"]
        mock_sch.export_netlist.return_value = mock_result
        mock_kicad = MagicMock()
        mock_kicad.get_schematic.return_value = mock_sch
        bridge._kipy_kicad = mock_kicad

        with patch("builtins.open", mock_open(read_data=".title test\nR1 1 0 1k\n.end\n")):
            result = bridge._export_netlist_via_ipc()

        assert ".title test" in result
        mock_sch.export_netlist.assert_called_once()

    def test_falls_back_to_kicad_cli_when_ipc_unavailable(self):
        bridge = KiCadBridge(kicad_cli_path="/usr/bin/kicad-cli")
        bridge._ipc_available = False
        expected = ".title test\nR1 1 0 1k\n.end\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch("builtins.open", mock_open(read_data=expected)):
                with patch("os.path.isfile", return_value=True):
                    result = bridge.export_netlist("/path/to/circuit.kicad_sch")

        assert result == expected
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "kicad-cli" in call_args[0]

    def test_raises_when_both_unavailable(self):
        bridge = KiCadBridge()
        bridge._ipc_available = False
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="kicad-cli"):
                bridge.export_netlist("/path/to/circuit.kicad_sch")

    def test_ipc_export_failure_falls_back(self):
        bridge = KiCadBridge(kicad_cli_path="/usr/bin/kicad-cli")
        bridge._ipc_available = True
        mock_sch = MagicMock()
        mock_sch.export_netlist.side_effect = Exception("API error")
        mock_kicad = MagicMock()
        mock_kicad.get_schematic.return_value = mock_sch
        bridge._kipy_kicad = mock_kicad
        expected = ".title fallback\n.end\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch("builtins.open", mock_open(read_data=expected)):
                with patch("os.path.isfile", return_value=True):
                    result = bridge.export_netlist("/path/to/circuit.kicad_sch")

        assert result == expected
        mock_run.assert_called_once()


class TestIpcSimPinsExtraction:
    """Tests for IPC-based Sim.Pins extraction."""

    def _make_mock_pin(self, number, name):
        pin = MagicMock()
        pin.number = number
        pin.name = name
        return pin

    def _make_mock_symbol_child(self, pin):
        child = MagicMock()
        child.item = pin
        return child

    def test_extracts_sim_pins_from_symbols(self):
        bridge = KiCadBridge()
        bridge._ipc_available = True

        mock_sch = MagicMock()
        q1_pins = [
            self._make_mock_symbol_child(self._make_mock_pin("1", "E")),
            self._make_mock_symbol_child(self._make_mock_pin("2", "B")),
            self._make_mock_symbol_child(self._make_mock_pin("3", "C")),
        ]
        q1_sym = MagicMock()
        q1_sym.reference_field.text = "Q1"
        type(q1_sym.definition).items = PropertyMock(return_value=q1_pins)

        d1_pins = [
            self._make_mock_symbol_child(self._make_mock_pin("1", "K")),
            self._make_mock_symbol_child(self._make_mock_pin("2", "A")),
        ]
        d1_sym = MagicMock()
        d1_sym.reference_field.text = "D1"
        type(d1_sym.definition).items = PropertyMock(return_value=d1_pins)

        mock_sch.get_symbols.return_value = [q1_sym, d1_sym]
        bridge._kipy_kicad = MagicMock()
        bridge._kipy_kicad.get_schematic.return_value = mock_sch

        result = bridge._extract_sim_pins_ipc()

        assert result == {
            "Q1": {"1": "E", "2": "B", "3": "C"},
            "D1": {"1": "K", "2": "A"},
        }

    def test_skips_symbols_without_pins(self):
        bridge = KiCadBridge()
        bridge._ipc_available = True

        mock_sch = MagicMock()
        r1_sym = MagicMock()
        r1_sym.reference_field.text = "R1"
        type(r1_sym.definition).items = PropertyMock(return_value=[])

        mock_sch.get_symbols.return_value = [r1_sym]
        bridge._kipy_kicad = MagicMock()
        bridge._kipy_kicad.get_schematic.return_value = mock_sch

        result = bridge._extract_sim_pins_ipc()
        assert result == {}

    def test_falls_back_to_regex_when_ipc_unavailable(self):
        bridge = KiCadBridge()
        bridge._ipc_available = False

        sch_content = """(kicad_sch
  (symbol
    (property "Reference" "Q1"
    (property "Sim.Pins" "1=E 2=B 3=C"
    (pin "1"
"""
        with patch("builtins.open", mock_open(read_data=sch_content)):
            result = bridge.extract_sim_pins("/fake/path.kicad_sch")

        assert result == {"Q1": {"1": "E", "2": "B", "3": "C"}}
