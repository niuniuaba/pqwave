"""Tests for Lepton-EDA bridge."""

import pytest
from pqwave.bridge.lepton.bridge import LeptonBridge


class TestLeptonBridge:
    def test_get_netlist_fixes_returns_empty(self):
        bridge = LeptonBridge()
        assert bridge.get_netlist_fixes() == []

    def test_get_watch_extensions_returns_sch(self):
        bridge = LeptonBridge()
        assert bridge.get_watch_extensions() == [".sch"]

    def test_detect_tool_returns_path_when_installed(self):
        bridge = LeptonBridge()
        path = bridge.detect_tool()
        assert path is not None
        assert "lepton-netlist" in path

    def test_is_tool_running_returns_bool(self):
        bridge = LeptonBridge()
        assert isinstance(bridge.is_tool_running(), bool)

    def test_simulate_with_invalid_sch_raises(self):
        bridge = LeptonBridge()
        with pytest.raises(Exception):
            bridge.simulate("/nonexistent/file.sch")


class TestLeptonBridgeNetlistExport:
    def test_export_two_stage_amp(self):
        import os
        bridge = LeptonBridge()
        sch = "/home/wing/Apps/lepton-eda.git/examples/TwoStageAmp/TwoStageAmp.sch"
        if not os.path.exists(sch):
            pytest.skip("TwoStageAmp example not available")
        netlist = bridge.export_netlist(sch)
        assert ".end" in netlist
        assert "/Vbase1" not in netlist
        assert "Q1" in netlist or "Q2" in netlist

    @pytest.mark.skip(reason="requires full filesystem access")
    def test_simulate_two_stage_amp(self):
        bridge = LeptonBridge()
        sch = "/home/wing/Apps/lepton-eda.git/examples/TwoStageAmp/TwoStageAmp.sch"
        result = bridge.simulate(sch)
        assert result["returncode"] == 0
        assert result["raw_file"] is not None
        assert ".end" in result["netlist"]


class TestSchemeServerDeployment:
    def test_check_scheme_server_returns_status(self):
        from pqwave.bridge.lepton.cross_probe import check_scheme_server
        status = check_scheme_server()
        assert "installed" in status
        assert "scm_target" in status
        assert "gafrc_path" in status
        assert "bundled_version_mtime" in status
        assert "needs_update" in status

    def test_bundled_scm_exists(self):
        from pqwave.bridge.lepton.cross_probe import _get_package_scm_path
        import os
        assert os.path.exists(_get_package_scm_path())
