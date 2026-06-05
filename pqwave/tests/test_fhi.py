"""Frequently-Happened Issues (FHI) — regression tests for recurring bugs.

Each test guards against a bug that has actually recurred or has a
subtle failure mode not obvious from the spec.  The docstring names
the gotcha and references the relevant entry in
``docs/integration-platform-capability-assessment.md`` (Appendix:
Integration Gotchas) when applicable.

Tests here MUST be deterministic (no running editors required).
Use mocks for external dependencies.
"""

from unittest.mock import patch

from pqwave.utils.colors import ColorManager
from pqwave.bridge.xschem.cross_probe import XschemCrossProbeClient


# ---------------------------------------------------------------------------
# ColorManager: mark_color_used vs. color_index
# ---------------------------------------------------------------------------

def test_colormanager_get_next_color_skips_mark_color_used():
    """FHI: mark_color_used() adds to used_colors but does not advance
    color_index.  get_next_color() must skip palette entries already
    reserved via mark_color_used() to avoid returning a duplicate.

    Triggered by: xschem Alt+G copyvar sends a custom color (red);
    next auto-assigned trace from pqwave also got red instead of green.
    """
    cm = ColorManager()

    # Simulate xschem Alt+G reserving palette[0] = red.
    red = (255, 0, 0)
    cm.mark_color_used(red)

    # Next auto-assigned color must NOT be red.
    c1 = cm.get_next_color()
    assert c1 != red, f"got duplicate red; color_index was not advanced past used"

    # Second auto-assigned should be different from the first.
    c2 = cm.get_next_color()
    assert c2 != c1, f"got same color twice: {c1}"
    assert c2 != red, f"red leaked into second auto-assignment"

    # Marking mid-palette must also work.
    cm2 = ColorManager()
    green = cm2.palette[1]  # skip red (palette[0]) + green (palette[1])
    cm2.mark_color_used(green)
    c = cm2.get_next_color()
    assert c == cm2.palette[0], f"expected palette[0] (red), got {c}"
    c = cm2.get_next_color()
    assert c not in (cm2.palette[1],), f"got marked green as auto-color"


def test_colormanager_mark_used_multiple_then_auto_assign():
    """FHI: marking several palette colors then auto-assigning must skip
    all of them."""
    cm = ColorManager()
    # Reserve first three palette entries.
    for i in range(3):
        cm.mark_color_used(cm.palette[i])

    for _ in range(3):
        c = cm.get_next_color()
        assert c not in cm.palette[:3], f"returned a marked-as-used color: {c}"


def test_colormanager_auto_assign_after_mark_used_does_not_repeat():
    """FHI: after a full auto-assign cycle, mark_color_used + get_next_color
    must still be consistent."""
    cm = ColorManager()
    # Exhaust some of the palette.
    for _ in range(3):
        cm.get_next_color()

    # Mark a later palette entry.
    cm.mark_color_used(cm.palette[4])
    c = cm.get_next_color()
    assert c == cm.palette[3], f"expected palette[3], got {c}"
    c = cm.get_next_color()
    assert c != cm.palette[4], f"returned marked-as-used palette[4]"


# ---------------------------------------------------------------------------
# Xschem: case-sensitive probe_net
# ---------------------------------------------------------------------------

def test_xschem_probe_net_falls_back_to_uppercase():
    """FHI: SPICE/ngspice is case-insensitive but xschem Tcl commands
    (hilight_netname, probe_net) do case-sensitive lookups.  pqwave
    extracts lowercase net names from v(r1), but xschem stores R1.

    probe_net must try verbatim first, then uppercase as fallback.
    """
    client = XschemCrossProbeClient(port=9999, timeout=0.1)

    # Simulate: verbatim lowercase returns empty (net not found),
    # uppercase returns the net path (found).
    responses = iter([(True, ""), (True, "R2")])

    def fake_send(tcl):
        ok, result = next(responses)
        return ok, result

    with patch.object(client, "send_command", side_effect=fake_send) as mock:
        ok = client.probe_net("r2")

    assert ok is True
    assert mock.call_count == 2
    assert mock.call_args_list[0][0][0] == "probe_net r2 1"
    assert mock.call_args_list[1][0][0] == "probe_net R2 1"


def test_xschem_probe_net_verbatim_succeeds_no_fallback():
    """FHI: when verbatim case succeeds, uppercase fallback must NOT
    be attempted (avoid unnecessary TCP round-trip)."""
    client = XschemCrossProbeClient(port=9999, timeout=0.1)

    with patch.object(client, "send_command", return_value=(True, "r2")) as mock:
        ok = client.probe_net("r2")

    assert ok is True
    mock.assert_called_once_with("probe_net r2 1")


def test_xschem_probe_net_both_cases_fail():
    """FHI: when neither verbatim nor uppercase finds the net, probe_net
    must return False (not crash or hang)."""
    client = XschemCrossProbeClient(port=9999, timeout=0.1)

    with patch.object(client, "send_command", return_value=(True, "")) as mock:
        ok = client.probe_net("nonexistent")

    assert ok is False
    assert mock.call_count == 2
