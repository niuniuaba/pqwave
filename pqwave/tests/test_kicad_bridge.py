"""Tests for KiCadBridge core (export + simulate pipeline)."""

from unittest.mock import MagicMock, mock_open, patch

from pqwave.bridge.kicad.bridge import KiCadBridge


class TestKiCadBridgeToolDetection:
    def test_detect_tool_finds_kicad_cli(self):
        bridge = KiCadBridge()
        with patch("shutil.which", return_value="/usr/bin/kicad-cli"):
            path = bridge.detect_tool()
            assert path == "/usr/bin/kicad-cli"

    def test_detect_tool_uses_custom_path(self):
        bridge = KiCadBridge(kicad_cli_path="/custom/kicad-cli")
        with patch("os.path.isfile", return_value=True):
            with patch("shutil.which") as mock_which:
                path = bridge.detect_tool()
                assert path == "/custom/kicad-cli"
                mock_which.assert_not_called()

    def test_detect_tool_returns_none_when_not_found(self):
        bridge = KiCadBridge()
        with patch("shutil.which", return_value=None):
            path = bridge.detect_tool()
            assert path is None

    def test_get_watch_extensions(self):
        bridge = KiCadBridge()
        exts = bridge.get_watch_extensions()
        assert ".kicad_sch" in exts

    def test_is_tool_running_true(self):
        bridge = KiCadBridge()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert bridge.is_tool_running() is True

    def test_is_tool_running_false(self):
        bridge = KiCadBridge()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert bridge.is_tool_running() is False


class TestKiCadBridgeExport:
    def test_export_netlist_success(self):
        bridge = KiCadBridge(kicad_cli_path="/usr/bin/kicad-cli")
        expected_netlist = ".title test\nR1 1 0 1k\n.end\n"
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                with patch("builtins.open", mock_open(read_data=expected_netlist)):
                    result = bridge.export_netlist("/path/to/circuit.kicad_sch")
                    assert result == expected_netlist

    def test_export_netlist_kicad_cli_error(self):
        bridge = KiCadBridge(kicad_cli_path="/usr/bin/kicad-cli")
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stderr="schematic parse error"
                )
                import pytest
                with pytest.raises(RuntimeError, match="kicad-cli failed"):
                    bridge.export_netlist("/path/to/bad.kicad_sch")

    def test_export_kicad_cli_not_found(self):
        bridge = KiCadBridge()
        with patch("shutil.which", return_value=None):
            import pytest
            with pytest.raises(FileNotFoundError, match="kicad-cli not found"):
                bridge.export_netlist("/path/to/circuit.kicad_sch")


class TestKiCadBridgeSimulate:
    def test_simulate_runs_full_pipeline(self):
        bridge = KiCadBridge(
            kicad_cli_path="/usr/bin/kicad-cli",
            ngspice_path="/usr/bin/ngspice",
        )
        netlist = ".title test\nR1 1 0 1k\nV1 1 0 DC 1\n.end\n"
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stderr=""),
                    MagicMock(returncode=0, stdout="sim ok", stderr=""),
                ]
                with patch("builtins.open", mock_open(read_data=netlist)):
                    result = bridge.simulate(
                        "/path/to/circuit.kicad_sch",
                        raw_output="/tmp/out.raw",
                    )
                    assert result["returncode"] == 0
                    assert result["raw_file"] == "/tmp/out.raw"
                    assert result["netlist"] == netlist
                    assert mock_run.call_count == 2

    def test_simulate_ngspice_error(self):
        bridge = KiCadBridge(
            kicad_cli_path="/usr/bin/kicad-cli",
            ngspice_path="/usr/bin/ngspice",
        )
        netlist = ".title test\nR1 1 0 1k\n.end\n"
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stderr=""),
                    MagicMock(returncode=1, stdout="", stderr="convergence failure"),
                ]
                with patch("builtins.open", mock_open(read_data=netlist)):
                    result = bridge.simulate(
                        "/path/to/circuit.kicad_sch",
                        raw_output="/tmp/out.raw",
                    )
                    assert result["returncode"] == 1
                    assert result["raw_file"] is None


class TestSimPinsExtraction:
    def test_extract_sim_pins_bjt(self):
        bridge = KiCadBridge()
        sch_content = """(kicad_sch
  (symbol
    (property "Reference" "Q1"
    (property "Sim.Pins" "1=E 2=B 3=C"
    (pin "1"
"""
        with patch("builtins.open", mock_open(read_data=sch_content)):
            result = bridge.extract_sim_pins("/fake/path.kicad_sch")
            assert "Q1" in result
            assert result["Q1"] == {"1": "E", "2": "B", "3": "C"}

    def test_extract_sim_pins_diode(self):
        bridge = KiCadBridge()
        sch_content = """(kicad_sch
  (symbol
    (property "Reference" "D1"
    (property "Sim.Pins" "1=K 2=A"
    (pin
"""
        with patch("builtins.open", mock_open(read_data=sch_content)):
            result = bridge.extract_sim_pins("/fake/path.kicad_sch")
            assert "D1" in result
            assert result["D1"] == {"1": "K", "2": "A"}

    def test_extract_sim_pins_file_not_found(self):
        bridge = KiCadBridge()
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = bridge.extract_sim_pins("/nonexistent.kicad_sch")
            assert result == {}
