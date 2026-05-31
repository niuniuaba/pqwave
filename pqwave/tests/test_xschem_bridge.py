import os
import tempfile
import subprocess
from unittest.mock import patch, MagicMock
import pytest
from pqwave.bridge.xschem.bridge import XschemBridge


class TestXschemBridgeExport:
    def test_export_netlist_success(self):
        bridge = XschemBridge()
        fake_netlist = "* SPICE netlist\nR1 n1 n2 1k\n.end\n"

        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", MagicMock()) as mock_open:

            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            mock_file = MagicMock()
            mock_file.read.return_value = fake_netlist
            mock_open.return_value.__enter__.return_value = mock_file
            mock_open.return_value.__exit__ = MagicMock()

            result = bridge.export_netlist("/path/to/circuit.sch")

            assert result == fake_netlist
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "/usr/bin/xschem"
            assert "-n" in call_args
            assert "-s" in call_args
            assert "-q" in call_args
            assert "--quit" in call_args
            assert "--netlist_type" in call_args
            assert "spice" in call_args

    def test_export_netlist_xschem_not_found(self):
        bridge = XschemBridge()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="xschem"):
                bridge.export_netlist("/path/to/circuit.sch")

    def test_export_netlist_subprocess_error(self):
        bridge = XschemBridge()
        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="schematic not found"
            )
            with pytest.raises(RuntimeError, match="xschem failed"):
                bridge.export_netlist("/path/to/bad.sch")

    def test_get_netlist_fixes_returns_empty(self):
        bridge = XschemBridge()
        assert bridge.get_netlist_fixes() == []

    def test_get_watch_extensions_returns_sch(self):
        bridge = XschemBridge()
        assert bridge.get_watch_extensions() == [".sch"]
