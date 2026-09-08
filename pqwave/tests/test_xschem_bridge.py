import os
import tempfile
import subprocess
from unittest.mock import patch, MagicMock
import pytest
from pqwave.bridge.xschem.bridge import XschemBridge


NETLIST = "* SPICE netlist\nR1 n1 n2 1k\n.end\n"


@pytest.fixture()
def xschem_env(tmp_path, monkeypatch):
    """A real project dir plus an isolated HOME.

    The previous tests passed fake paths like `/path/to/circuit.sch` and patched
    `os.path.exists` to True globally. export_netlist() really does
    `os.makedirs(netlist_dir)` and simulate() really does `os.path.getmtime()`
    on the expected .raw, so the fake paths escaped into the real filesystem
    (`Read-only file system: '/path'`) and the blanket exists-patch made
    nonexistent files look present. Everything here is real, under tmp_path.
    """
    home = tmp_path / "home"
    (home / ".xschem").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    # local_netlist_dir 1 -> netlist lands in <sch_dir>/simulation/
    (home / ".xschem" / "xschemrc").write_text("set local_netlist_dir 1\n")

    sch_dir = tmp_path / "proj"
    sch_dir.mkdir()
    sch = sch_dir / "circuit.sch"
    sch.write_text("** schematic\n")
    netlist_dir = sch_dir / "simulation"
    return {
        "sch": str(sch),
        "sch_dir": str(sch_dir),
        "netlist_dir": str(netlist_dir),
        "spice": str(netlist_dir / "circuit.spice"),
        "raw": str(netlist_dir / "circuit.raw"),
    }


class TestXschemBridgeExport:
    def test_export_netlist_success(self, xschem_env):
        """xschem is driven headless and the resulting .spice is returned."""
        bridge = XschemBridge()

        def fake_run(cmd, **kwargs):
            # xschem writes the netlist itself; emulate that side effect.
            os.makedirs(os.path.dirname(xschem_env["spice"]), exist_ok=True)
            with open(xschem_env["spice"], "w") as fh:
                fh.write(NETLIST)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("subprocess.run", side_effect=fake_run) as mock_run:
            result = bridge.export_netlist(xschem_env["sch"])

        assert result == NETLIST
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        # -n netlist, -s spice, -x no GUI, -q quit after. The bridge deliberately
        # does NOT pass `--tcl set netlist_dir ...` any more: overriding the
        # user's configured netlist_dir was the behaviour removed in the
        # streamline-eda-integrations change, and these older assertions were
        # still demanding the deleted flags.
        assert cmd == ["/usr/bin/xschem", "-n", "-s", "-x", "-q",
                       xschem_env["sch"]], f"unexpected invocation: {cmd}"
        assert "--tcl" not in cmd, "netlist_dir must not be overridden"
        assert mock_run.call_args[1]["cwd"] == xschem_env["sch_dir"]
        assert mock_run.call_args[1]["timeout"] == 30

    def test_export_netlist_raises_when_xschem_produces_nothing(self, xschem_env):
        """returncode 0 with no .spice on disk must not silently return ''."""
        bridge = XschemBridge()
        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")):
            with pytest.raises(RuntimeError, match="no .spice file found"):
                bridge.export_netlist(xschem_env["sch"])

    def test_export_netlist_xschem_not_found(self, xschem_env):
        bridge = XschemBridge()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="xschem"):
                bridge.export_netlist(xschem_env["sch"])

    def test_export_netlist_subprocess_error(self, xschem_env):
        """A non-zero xschem exit becomes a RuntimeError carrying stderr."""
        bridge = XschemBridge()
        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="schematic not found"
            )
            with pytest.raises(RuntimeError, match="xschem failed"):
                bridge.export_netlist(xschem_env["sch"])

    def test_get_netlist_fixes_returns_empty(self):
        bridge = XschemBridge()
        assert bridge.get_netlist_fixes() == []

    def test_get_watch_extensions_returns_sch(self):
        bridge = XschemBridge()
        assert bridge.get_watch_extensions() == [".sch"]


class TestXschemBridgeSimulate:
    def _two_stage_runner(self, xschem_env, sim_rc, sim_stdout, sim_stderr):
        """Mock xschem export (writes .spice) then the simulator invocation."""
        state = {"calls": 0}

        def fake_run(cmd, **kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                os.makedirs(os.path.dirname(xschem_env["spice"]), exist_ok=True)
                with open(xschem_env["spice"], "w") as fh:
                    fh.write(NETLIST)
                return MagicMock(returncode=0, stdout="", stderr="")
            with open(xschem_env["raw"], "w") as fh:
                fh.write("raw written\n")
            return MagicMock(returncode=sim_rc, stdout=sim_stdout,
                             stderr=sim_stderr)

        return fake_run, state

    def test_simulate_pipeline_success(self, xschem_env):
        """Full export -> post-process -> ngspice pipeline."""
        bridge = XschemBridge()
        fake_run, state = self._two_stage_runner(
            xschem_env, sim_rc=0, sim_stdout="Simulation OK\n", sim_stderr="")

        with patch("shutil.which", return_value="/usr/bin/xschem"), \
             patch("subprocess.run", side_effect=fake_run):
            result = bridge.simulate(xschem_env["sch"])

        assert state["calls"] == 2, "expected one export and one simulation call"
        assert result["returncode"] == 0
        assert "Simulation OK" in result["stdout"]
        assert result["raw_file"] == xschem_env["raw"], \
            "the .raw produced by the simulator was not reported"
        assert result["netlist"] == NETLIST

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
