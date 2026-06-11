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

        fake_tmpdir = "/tmp/pqwave_xschem_nl_test123"

        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("tempfile.mkdtemp", return_value=fake_tmpdir), \
             patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True), \
             patch("os.unlink"), \
             patch("os.rmdir"), \
             patch("os.listdir", return_value=[]), \
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
            # Verify --tcl flag with netlist_dir override
            assert "--tcl" in call_args
            tcl_idx = list(call_args).index("--tcl")
            tcl_cmd = call_args[tcl_idx + 1]
            assert "set netlist_dir" in tcl_cmd
            assert fake_tmpdir in tcl_cmd
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


class TestXschemBridgeSimulate:
    def test_simulate_pipeline_success(self):
        """Verify the full export -> post-process -> ngspice pipeline."""
        bridge = XschemBridge()
        fake_netlist = "* test netlist\nR1 n1 n2 1k\n.end\n"
        fake_raw = "/tmp/pqwave_test.raw"

        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("tempfile.mkdtemp", return_value="/tmp/pqwave_nl_test"), \
             patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True), \
             patch("os.unlink"), \
             patch("os.rmdir"), \
             patch("os.listdir", return_value=[]), \
             patch("os.close"), \
             patch("tempfile.mkstemp", return_value=(3, "/tmp/circuit.cir")), \
             patch("builtins.open", MagicMock()) as mock_open:

            mock_file = MagicMock()
            mock_file.read.return_value = fake_netlist
            mock_open.return_value.__enter__.return_value = mock_file
            mock_open.return_value.__exit__ = MagicMock()

            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="Simulation OK\n", stderr=""),
            ]

            result = bridge.simulate("/path/to/circuit.sch", raw_output=fake_raw)

            assert result["returncode"] == 0
            assert result["raw_file"] == fake_raw
            assert "Simulation OK" in result["stdout"]
            assert result["netlist"] == fake_netlist
            assert result["fix_info"] == []
            assert mock_run.call_count == 2

    def test_simulate_ngspice_error(self):
        """Verify ngspice failure is reported, not thrown."""
        bridge = XschemBridge()
        fake_netlist = "* bad circuit\n.end\n"

        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("tempfile.mkdtemp", return_value="/tmp/pqwave_nl_test"), \
             patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True), \
             patch("os.unlink"), \
             patch("os.rmdir"), \
             patch("os.listdir", return_value=[]), \
             patch("os.close"), \
             patch("tempfile.mkstemp", return_value=(3, "/tmp/circuit.cir")), \
             patch("builtins.open", MagicMock()) as mock_open:

            mock_file = MagicMock()
            mock_file.read.return_value = fake_netlist
            mock_open.return_value.__enter__.return_value = mock_file
            mock_open.return_value.__exit__ = MagicMock()

            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=1, stdout="", stderr="convergence failure"),
            ]

            result = bridge.simulate("/path/to/bad.sch")

            assert result["returncode"] == 1
            assert result["raw_file"] is None
            assert "convergence failure" in result["stderr"]
            assert result["netlist"] == fake_netlist


import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QSignalSpy
from pqwave.bridge.xschem.control_bar import XschemControlBar

# QApplication required for Qt widget/signal infrastructure
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestXschemControlBar:
    def test_initial_state_hidden(self):
        bar = XschemControlBar()
        assert bar.isHidden()

    def test_set_status_updates_label(self):
        bar = XschemControlBar()
        bar.set_status("watching circuit.sch")
        assert "circuit.sch" in bar._status_label.text()

    def test_set_simulating_disables_button(self):
        bar = XschemControlBar()
        bar.set_simulating(True)
        assert not bar._simulate_btn.isEnabled()
        assert "simulating" in bar._status_label.text().lower()

    def test_simulate_clicked_emits_signal(self):
        bar = XschemControlBar()
        spy = QSignalSpy(bar.simulate_clicked)
        bar._simulate_btn.click()
        assert len(spy) == 1

    def test_disconnect_clicked_emits_signal(self):
        bar = XschemControlBar()
        spy = QSignalSpy(bar.disconnect_clicked)
        bar._disconnect_btn.click()
        assert len(spy) == 1
