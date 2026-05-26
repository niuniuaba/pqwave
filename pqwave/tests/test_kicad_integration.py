"""End-to-end integration tests for KiCad bridge pipeline.

Requires kicad-cli and ngspice in PATH.
Run with: pytest pqwave/tests/test_kicad_integration.py -v -m kicad
"""

import os
import tempfile

import pytest

pytestmark = pytest.mark.kicad

BRIDGE_SCH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "kicad", "examples", "bridge.kicad_sch"
)


@pytest.fixture
def bridge():
    from pqwave.bridge.kicad.bridge import KiCadBridge
    return KiCadBridge()


def test_export_netlist(bridge):
    """Export a netlist from the bridge rectifier example."""
    if not os.path.exists(BRIDGE_SCH):
        pytest.skip(f"Example file not found: {BRIDGE_SCH}")
    netlist = bridge.export_netlist(BRIDGE_SCH)
    assert ".end" in netlist
    assert "D1" in netlist or "D3" in netlist


def test_netlist_postprocessor_applies_fixes(bridge):
    """Verify post-processor fixes are applied to real netlist."""
    if not os.path.exists(BRIDGE_SCH):
        pytest.skip(f"Example file not found: {BRIDGE_SCH}")
    from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor

    netlist = bridge.export_netlist(BRIDGE_SCH)
    fixes = bridge.get_netlist_fixes()
    processor = NetlistPostProcessor(fixes)

    dry_results = processor.dry_run(netlist)
    assert len(dry_results) > 0, "Should report at least diode fix"

    fixed = processor.process(netlist)
    assert len(fixed) > 0
    assert ".end" in fixed


def test_full_simulate_pipeline(bridge):
    """Run the full pipeline and verify .raw loads."""
    if not os.path.exists(BRIDGE_SCH):
        pytest.skip(f"Example file not found: {BRIDGE_SCH}")

    _, raw_path = tempfile.mkstemp(suffix=".raw", prefix="pqwave_test_")
    os.close(_)

    try:
        result = bridge.simulate(BRIDGE_SCH, raw_output=raw_path)
        assert result["returncode"] == 0, f"ngspice failed: {result['stderr'][:500]}"
        assert result["raw_file"] is not None

        from pqwave.session.api import SessionAPI
        from pqwave.models.state import ApplicationState
        api = SessionAPI(state=ApplicationState())
        info = api.load(raw_path)
        assert info["n_variables"] >= 4, f"Expected >= 4 signals, got {info}"
    finally:
        try:
            os.unlink(raw_path)
        except OSError:
            pass
