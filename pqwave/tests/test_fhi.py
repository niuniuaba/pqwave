"""Frequently-Happened Issues (FHI) — regression tests for recurring bugs.

Each test guards against a bug that has actually recurred or has a
subtle failure mode not obvious from the spec.  The docstring names
the gotcha and references the relevant entry in
``docs/integration-platform-capability-assessment.md`` (Appendix:
Integration Gotchas) when applicable.

Tests here MUST be deterministic (no running editors required).
Use mocks for external dependencies.
"""

import os
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


# ---------------------------------------------------------------------------
# Tcl {} empty-element parsing
# ---------------------------------------------------------------------------

def test_get_pqwave_texts_tag_filters_tcl_empty():
    """FHI: Tcl represents empty list elements as ``{}``.  When
    ``_get_pqwave_texts_tag`` parses ``lappend``+``set`` output,
    ``{}`` must be treated as empty (no tag), NOT as a valid key.

    Without the filter, ``{}`` enters the dict as a truthy key,
    mapping to a text index that should NOT have been included.
    ``_delete_tagged_texts`` then selects and deletes ALL texts
    (tagged + untagged), destroying annotations of the other type.
    """
    client = XschemCrossProbeClient(port=9999, timeout=0.1)

    # Simulate 5 texts:
    #   text 0: pqwave_dc=ac_p
    #   text 1: pqwave_dc=ac_n
    #   text 2: pqwave_dc=r1
    #   text 3: pqwave_dc=r2
    #   text 4: no pqwave_dc tag  → Tcl lappend represents empty as {}
    globals_out = "texts=5\n"
    getprop_out = "ac_p ac_n r1 r2 {}"

    def fake_send(cmd):
        if "globals" in cmd:
            return (True, globals_out)
        if "pqwave_dc" in cmd:
            return (True, getprop_out)
        return (True, "")

    with patch.object(client, "send_command", side_effect=fake_send):
        texts = client._get_pqwave_texts_tag("pqwave_dc", "dc")

    # Must have exactly 4 entries (ac_p, ac_n, r1, r2) — NOT 5 with {}.
    assert len(texts) == 4, f"expected 4, got {len(texts)}: {texts}"
    assert "{}" not in texts, "Tcl empty braces leaked into dict: " + str(texts)
    assert texts == {"ac_p": 0, "ac_n": 1, "r1": 2, "r2": 3}


# ---------------------------------------------------------------------------
# Cache invalidation after creating new xschem text objects
# ---------------------------------------------------------------------------

def test_stamp_values_invalidates_cache_after_creating_texts():
    """FHI: when ``stamp_values`` creates new text objects (because no
    existing cursor text was found), it MUST invalidate the text cache
    so the *next* call re-queries xschem and finds the newly created
    texts.  Without invalidation the second call returns the stale
    (empty) cache and creates duplicate texts at the same position.
    """
    client = XschemCrossProbeClient(port=9999, timeout=0.1)

    # Simulate one lab at (100, 200) for net "r1".
    with patch.object(client, "_build_lab_position_map",
                      return_value={"r1": (100, 200)}):
        # First call: no existing cursor texts → creates new one.
        with patch.object(client, "_get_pqwave_texts_tag",
                          return_value={}) as mock_tag:
            with patch.object(client, "send_command",
                              return_value=(True, "")):
                client.stamp_values({"r1": "5.0"})

            # After stamp_values, the cache must be cleared.
            # Verify by checking that _get_pqwave_texts_tag was called
            # with the cursor tag (for the initial lookup).
            mock_tag.assert_called_once_with("pqwave_net", "cursor")

        # Second call: simulate that the text now exists at index 0.
        with patch.object(client, "_get_pqwave_texts_tag",
                          return_value={"r1": 0}) as mock_tag2:
            with patch.object(client, "send_command",
                              return_value=(True, "")) as mock_send:
                client.stamp_values({"r1": "5.1"})

            # Must have re-queried (not used stale cache).
            assert mock_tag2.call_count >= 1, (
                "_get_pqwave_texts_tag not called on second stamp_values "
                "— stale cache returned")
            # Must update existing text, not create new one.
            sent = mock_send.call_args[0][0]
            assert "setprop text 0 txt_ptr" in sent, (
                f"expected update, got: {sent}")


# ---------------------------------------------------------------------------
# xschem GAW "sent" tracking
# ---------------------------------------------------------------------------
# FHI: xschem's GAW protocol tracks which nets have been sent to the viewer
# via Alt+G and will NOT re-send ``copyvar`` for them until the highlight is
# cleared.  When a trace is deleted in pqwave, the handler must call both
# ``remove_stamp()`` (clear the back-annotation text) AND ``clear()`` (send
# ``xschem unhilight_all`` to reset xschem's sent-tracking).  Without the
# ``clear()`` call, Alt+G silently does nothing after trace deletion.
#
# This is documented here rather than as a deterministic test because the
# root cause is in xschem's GAW protocol, not in pqwave's code.  The fix is
# the pairing of remove_stamp + clear in _on_trace_removed_for_xschem.
# See: _on_trace_removed_for_xschem() in main_window.py.


# ---------------------------------------------------------------------------
# Guile bytecode cache staleness
# ---------------------------------------------------------------------------

def test_guile_cache_stale_detects_newer_source():
    """FHI: Guile auto-compiles ``.scm`` files to ``.go`` bytecode on first
    load and will NOT recompile when the source changes until lepton-schematic
    is restarted.  This causes edited ``pqwave-server.scm`` or
    ``menu-additions.scm`` to appear broken because the old ``.go`` is
    still running.

    ``_check_guile_cache_stale()`` compares mtimes and returns True when
    the source is newer than the compiled cache.  ``check_scheme_server()``
    includes ``guile_cache_stale`` in its result, and
    ``_start_lepton_connect()`` warns the user.
    """
    import tempfile
    import time
    from pqwave.bridge.lepton.cross_probe import _check_guile_cache_stale

    cache_root = os.path.expanduser("~/.cache/guile/ccache/3.0-LE-8-4.7")

    with tempfile.TemporaryDirectory() as tmpdir:
        scm_path = os.path.join(tmpdir, "pqwave-server.scm")
        with open(scm_path, "w") as f:
            f.write(";; VERSION: 99\n")

        # No .go exists yet → not stale.
        assert _check_guile_cache_stale(scm_path) is False

        # Create a fake .go older than the .scm → stale.
        go_path = os.path.join(cache_root, scm_path.lstrip("/") + ".go")
        os.makedirs(os.path.dirname(go_path), exist_ok=True)
        with open(go_path, "w") as f:
            f.write("")
        os.utime(go_path, (time.time() - 86400, time.time() - 86400))

        assert _check_guile_cache_stale(scm_path) is True, (
            ".scm newer than .go should be detected as stale")

        # Set .go mtime to future → not stale.
        os.utime(go_path, (time.time() + 86400, time.time() + 86400))
        assert _check_guile_cache_stale(scm_path) is False, (
            ".go newer than .scm should not be stale")
