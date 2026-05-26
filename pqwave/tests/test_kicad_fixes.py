"""Tests for KiCad netlist post-processing fixes."""

import pytest

from pqwave.bridge.kicad.fixes import (
    FixBJTPins,
    FixDiodePins,
    MoveControlBlock,
    StripSlashes,
)


# ---------------------------------------------------------------------------
# StripSlashes
# ---------------------------------------------------------------------------

class TestStripSlashes:
    def test_strips_slash_from_diode_nodes(self):
        fix = StripSlashes()
        result = fix.apply("D1 /VOUT /VIN D1_model")
        assert result == "D1 VOUT VIN D1_model"

    def test_strips_slash_from_vsource_nodes(self):
        fix = StripSlashes()
        result = fix.apply("V1 /net1 /net0 DC 5")
        assert result == "V1 net1 net0 DC 5"

    def test_strips_slash_from_bsource(self):
        fix = StripSlashes()
        result = fix.apply("B1 /out 0 V=(/in)>0.5 ? 5 : 0")
        assert result == "B1 out 0 V=(in)>0.5 ? 5 : 0"

    def test_handles_multiple_slashes_in_one_line(self):
        fix = StripSlashes()
        result = fix.apply("XU1 /a /b /c /d subckt_model")
        assert result == "XU1 a b c d subckt_model"

    def test_does_not_strip_from_subckt_line(self):
        fix = StripSlashes()
        netlist = ".subckt opamp /in+ /in- /out"
        result = fix.apply(netlist)
        assert result == netlist

    def test_does_not_strip_from_comment(self):
        fix = StripSlashes()
        netlist = "* This is /a /comment about /stuff"
        result = fix.apply(netlist)
        assert result == netlist

    def test_does_not_modify_DC(self):
        fix = StripSlashes()
        netlist = ".DC V1 0 5 0.1"
        result = fix.apply(netlist)
        assert result == netlist

    def test_does_not_modify_DISTO(self):
        fix = StripSlashes()
        netlist = ".DISTO DEC 10 1k 100k"
        result = fix.apply(netlist)
        assert result == netlist

    def test_info_reports_unique_count(self):
        fix = StripSlashes()
        netlist = "D1 /VOUT /VIN\nD2 /VOUT 0"
        info = fix.info(netlist)
        assert len(info) == 1
        assert info[0]["fix"] == fix.name
        assert "2 node names" in info[0]["detail"]
        assert "VIN" in info[0]["detail"]
        assert "VOUT" in info[0]["detail"]

    def test_info_empty_when_no_slashes(self):
        fix = StripSlashes()
        assert fix.info("D1 VOUT VIN D1_model") == []

    def test_idempotent(self):
        fix = StripSlashes()
        original = "D1 /VOUT /VIN D1_model"
        first = fix.apply(original)
        second = fix.apply(first)
        assert second == first


# ---------------------------------------------------------------------------
# FixDiodePins
# ---------------------------------------------------------------------------

class TestFixDiodePins:
    def test_swaps_anode_cathode(self):
        fix = FixDiodePins()
        result = fix.apply("D1 anode cathode D1N4148")
        assert result == "D1 cathode anode D1N4148"

    def test_handles_trailing_params(self):
        fix = FixDiodePins()
        result = fix.apply("D2 n1 n2 DMOD area=2")
        assert result == "D2 n2 n1 DMOD area=2"

    def test_diode_without_model(self):
        fix = FixDiodePins()
        result = fix.apply("D3 a b")
        assert result == "D3 b a"

    def test_does_not_swap_DC(self):
        fix = FixDiodePins()
        netlist = ".DC V1 0 5 0.1"
        result = fix.apply(netlist)
        assert result == netlist

    def test_does_not_swap_DISTO(self):
        fix = FixDiodePins()
        netlist = ".DISTO DEC 10 1k 100k"
        result = fix.apply(netlist)
        assert result == netlist

    def test_info_reports_each_diode(self):
        fix = FixDiodePins()
        netlist = "D1 a b DMOD\nD2 c d\nR1 1 2 1k"
        info = fix.info(netlist)
        assert len(info) == 2
        assert "D1" in info[0]["detail"]
        assert "D2" in info[1]["detail"]

    def test_idempotent(self):
        fix = FixDiodePins()
        original = "D1 a b DMOD"
        first = fix.apply(original)
        second = fix.apply(first)
        assert second == original

    def test_empty_netlist(self):
        fix = FixDiodePins()
        assert fix.apply("") == ""


# ---------------------------------------------------------------------------
# FixBJTPins
# ---------------------------------------------------------------------------

class TestFixBJTPins:
    def test_reorder_bjt_pins(self):
        fix = FixBJTPins()
        netlist = "Q1 nc_01 nc_02 nc_03 2N3904"
        context = {"sim_pins": {"Q1": ["E", "B", "C"]}}
        result = fix.apply(netlist, context)
        # Original order E-B-C, SPICE wants C-B-E
        assert result == "Q1 nc_03 nc_02 nc_01 2N3904"

    def test_no_context_none(self):
        fix = FixBJTPins()
        netlist = "Q1 1 2 3 NPN"
        result = fix.apply(netlist, None)
        assert result == netlist

    def test_no_context_empty_dict(self):
        fix = FixBJTPins()
        netlist = "Q1 1 2 3 NPN"
        result = fix.apply(netlist, {})
        assert result == netlist

    def test_mosfet_reorder(self):
        fix = FixBJTPins()
        netlist = "M1 net_d net_g net_s NMOS"
        context = {"sim_pins": {"M1": ["S", "G", "D"]}}
        result = fix.apply(netlist, context)
        # Original order S-G-D, SPICE wants D-G-S
        assert result == "M1 net_s net_g net_d NMOS"

    def test_jfet_reorder(self):
        fix = FixBJTPins()
        netlist = "J1 net_d net_g net_s NJF"
        context = {"sim_pins": {"J1": ["S", "G", "D"]}}
        result = fix.apply(netlist, context)
        # Original order S-G-D, SPICE wants D-G-S
        assert result == "J1 net_s net_g net_d NJF"

    def test_missing_pin_maps_to_NC(self):
        fix = FixBJTPins()
        netlist = "Q2 1 2 3 NPN"
        context = {"sim_pins": {"Q2": ["E", "B"]}}  # C missing
        result = fix.apply(netlist, context)
        # C→NC, B→2, E→1
        assert result == "Q2 NC 2 1 NPN"

    def test_dict_format_sim_pins(self):
        fix = FixBJTPins()
        netlist = "Q3 na nb nc NPN"
        context = {"sim_pins": {"Q3": {"E": 0, "B": 1, "C": 2}}}
        result = fix.apply(netlist, context)
        assert result == "Q3 nc nb na NPN"

    def test_info_reports_transistors(self):
        fix = FixBJTPins()
        netlist = "Q1 1 2 3 NPN\nM1 4 5 6 NMOS\nR1 a b 1k"
        context = {"sim_pins": {"Q1": ["E", "B", "C"], "M1": ["S", "G", "D"]}}
        info = fix.info(netlist, context)
        assert len(info) == 2
        assert "Q1" in info[0]["detail"]
        assert "M1" in info[1]["detail"]

    def test_info_ignores_unmapped_transistors(self):
        fix = FixBJTPins()
        netlist = "Q1 1 2 3 NPN\nQ2 4 5 6 PNP"
        context = {"sim_pins": {"Q1": ["E", "B", "C"]}}  # Q2 not mapped
        info = fix.info(netlist, context)
        assert len(info) == 1
        assert "Q1" in info[0]["detail"]

    def test_handles_trailing_params_on_transistor(self):
        fix = FixBJTPins()
        netlist = "Q10 nc1 nc2 nc3 BC547 temp=25"
        context = {"sim_pins": {"Q10": ["E", "B", "C"]}}
        result = fix.apply(netlist, context)
        assert result == "Q10 nc3 nc2 nc1 BC547 temp=25"


# ---------------------------------------------------------------------------
# MoveControlBlock
# ---------------------------------------------------------------------------

class TestMoveControlBlock:
    def test_moves_before_end(self):
        fix = MoveControlBlock()
        netlist = (
            "Circuit\n"
            "R1 1 0 1k\n"
            ".control\n"
            "tran 1u 1m\n"
            "plot v(1)\n"
            ".endc\n"
            ".end\n"
        )
        result = fix.apply(netlist)
        expected = (
            "Circuit\n"
            "R1 1 0 1k\n"
            ".control\n"
            "tran 1u 1m\n"
            "plot v(1)\n"
            ".endc\n"
            ".end\n"
        )
        assert result == expected

    def test_moves_from_middle_to_before_end(self):
        fix = MoveControlBlock()
        netlist = (
            "Circuit\n"
            ".control\n"
            "echo test\n"
            ".endc\n"
            "R1 1 0 1k\n"
            "V1 1 0 DC 5\n"
            ".end\n"
        )
        result = fix.apply(netlist)
        expected = (
            "Circuit\n"
            "R1 1 0 1k\n"
            "V1 1 0 DC 5\n"
            ".control\n"
            "echo test\n"
            ".endc\n"
            ".end\n"
        )
        assert result == expected

    def test_no_block_no_change(self):
        fix = MoveControlBlock()
        netlist = "R1 1 0 1k\nV1 1 0 DC 5\n.end\n"
        result = fix.apply(netlist)
        assert result == netlist

    def test_info_reports_line_number(self):
        fix = MoveControlBlock()
        netlist = "Circuit\nR1 1 0 1k\n.control\ntran 1u\n.endc\n.end\n"
        info = fix.info(netlist)
        assert len(info) == 1
        assert "line 3" in info[0]["detail"]

    def test_info_empty_when_no_block(self):
        fix = MoveControlBlock()
        netlist = "R1 1 0 1k\n.end\n"
        assert fix.info(netlist) == []

    def test_idempotent(self):
        fix = MoveControlBlock()
        netlist = (
            "Circuit\n"
            "R1 1 0 1k\n"
            ".control\n"
            "tran 1u 1m\n"
            ".endc\n"
            ".end\n"
        )
        first = fix.apply(netlist)
        second = fix.apply(first)
        assert second == first
