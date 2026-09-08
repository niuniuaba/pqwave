"""Tests for worst-case analysis engine."""
import numpy as np
import pytest


class TestCornerEnumeration:
    """Test 2^N corner generation."""

    def test_two_components_generates_four_corners(self):
        from pqwave.analysis.worst_case import enumerate_corners
        components = {
            "R1": {"nominal": 10000.0, "tolerance": 0.05},  # ±5%
            "C1": {"nominal": 1e-7, "tolerance": 0.10},     # ±10%
        }
        corners = enumerate_corners(components)
        assert len(corners) == 4  # 2^2

    def test_corner_values_at_extremes(self):
        from pqwave.analysis.worst_case import enumerate_corners
        components = {
            "R1": {"nominal": 100.0, "tolerance": 0.10},
        }
        corners = enumerate_corners(components)
        values = sorted([c["R1"] for c in corners])
        assert abs(values[0] - 90.0) < 1e-9  # min
        assert abs(values[1] - 110.0) < 1e-9  # max

    def test_three_components_generates_eight_corners(self):
        from pqwave.analysis.worst_case import enumerate_corners
        components = {
            "R1": {"nominal": 1e3, "tolerance": 0.01},
            "R2": {"nominal": 2e3, "tolerance": 0.01},
            "R3": {"nominal": 3e3, "tolerance": 0.01},
        }
        corners = enumerate_corners(components)
        assert len(corners) == 8  # 2^3

    def test_empty_components_returns_single_corner(self):
        from pqwave.analysis.worst_case import enumerate_corners
        corners = enumerate_corners({})
        assert len(corners) == 1
        assert corners[0] == {}


class TestTempcoComputation:
    """Test temperature coefficient value adjustment."""

    def test_positive_tempco_increases_value_at_high_temp(self):
        from pqwave.analysis.worst_case import apply_tempco
        nominal = 10000.0
        tempco = 200e-6  # 200 ppm/°C
        t_nom = 27.0
        t_actual = 85.0
        result = apply_tempco(nominal, tempco, t_actual, t_nom)
        # 10000 * (1 + 200e-6 * (85-27)) = 10000 * 1.0116 = 10116
        assert abs(result - 10116.0) < 1.0

    def test_negative_tempco_decreases_value_at_high_temp(self):
        from pqwave.analysis.worst_case import apply_tempco
        nominal = 10000.0
        tempco = -200e-6
        t_nom = 27.0
        t_actual = 85.0
        result = apply_tempco(nominal, tempco, t_actual, t_nom)
        assert result < nominal

    def test_zero_tempco_no_change(self):
        from pqwave.analysis.worst_case import apply_tempco
        assert apply_tempco(1000.0, 0.0, 100.0, 27.0) == 1000.0

    def test_lower_than_nominal_when_temp_below_nominal(self):
        from pqwave.analysis.worst_case import apply_tempco
        result = apply_tempco(1000.0, 100e-6, 0.0, 27.0)
        # 1000 * (1 + 100e-6 * (0 - 27)) = 1000 * 0.9973 = 997.3
        assert result < 1000.0


class TestSensitivityFilter:
    """Test sensitivity-based component ranking."""

    def test_ranks_more_sensitive_first(self):
        from pqwave.analysis.worst_case import rank_by_sensitivity
        # Mock sensitivity data
        sensitivities = {
            "R1": 0.15,   # 15% change in output
            "R2": 0.02,   # 2% change
            "C1": 0.45,   # 45% change — most sensitive
        }
        ranked = rank_by_sensitivity(sensitivities)
        assert ranked[0] == "C1"
        assert ranked[1] == "R1"
        assert ranked[2] == "R2"

    def test_top_n_returns_correct_count(self):
        from pqwave.analysis.worst_case import rank_by_sensitivity
        sensitivities = {f"R{i}": 0.01 * i for i in range(1, 16)}
        ranked = rank_by_sensitivity(sensitivities, top_n=8)
        assert len(ranked) == 8

    def test_negative_sensitivities_ranked_by_abs(self):
        from pqwave.analysis.worst_case import rank_by_sensitivity
        sensitivities = {
            "R1": -0.50,
            "R2": 0.10,
        }
        ranked = rank_by_sensitivity(sensitivities)
        assert ranked[0] == "R1"

    def test_empty_sensitivities_returns_empty_list(self):
        from pqwave.analysis.worst_case import rank_by_sensitivity
        assert rank_by_sensitivity({}) == []


class TestNetlistModification:
    """Test netlist component value replacement."""

    def test_replace_resistor_value(self):
        from pqwave.analysis.worst_case import modify_netlist
        netlist = "R1 n1 n2 10k\nR2 n2 0 1k\n.op\n"
        corner = {"R1": 9500.0}
        result = modify_netlist(netlist, corner)
        assert "R1 n1 n2 9500" in result or "R1 n1 n2 9.5k" in result

    def test_no_change_for_unspecified_components(self):
        from pqwave.analysis.worst_case import modify_netlist
        netlist = "R1 n1 n2 10k\nC1 n2 0 100n\n.op\n"
        corner = {"R1": 9000.0}
        result = modify_netlist(netlist, corner)
        assert "C1 n2 0 100n" in result  # unchanged

    def test_multiple_values_modified(self):
        from pqwave.analysis.worst_case import modify_netlist
        netlist = "R1 n1 n2 10k\nR2 n2 0 1k\n.op\n"
        corner = {"R1": 5000.0, "R2": 2000.0}
        result = modify_netlist(netlist, corner)
        lines = [line.strip() for line in result.splitlines()]
        assert any(line.startswith("R1") and ("5k" in line or "5000" in line)
                   for line in lines)
        assert any(line.startswith("R2") and ("2k" in line or "2000" in line)
                   for line in lines)

    def test_model_card_unchanged(self):
        from pqwave.analysis.worst_case import modify_netlist
        netlist = ".model NMOS_1 nmos\nR1 n1 n2 10k\n.op\n"
        corner = {"R1": 5000.0}
        result = modify_netlist(netlist, corner)
        assert ".model NMOS_1 nmos" in result


class TestFormatSpiceValue:
    """Test SPICE value formatting."""

    def test_meg_format(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert "Meg" in _format_spice_value(1e6)

    def test_k_format(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert "k" in _format_spice_value(1000.0)

    def test_m_format(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert "m" in _format_spice_value(0.001)

    def test_u_format(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert "u" in _format_spice_value(1e-6)

    def test_n_format(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert "n" in _format_spice_value(1e-9)

    def test_p_format(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert "p" in _format_spice_value(1e-12)

    def test_tiny_value_no_suffix(self):
        from pqwave.analysis.worst_case import _format_spice_value
        result = _format_spice_value(1e-15)
        assert "e" in result or "e" in result  # scientific notation

    def test_zero_formatted(self):
        from pqwave.analysis.worst_case import _format_spice_value
        assert _format_spice_value(0.0) == "0"

    def test_value_between_one_and_k(self):
        from pqwave.analysis.worst_case import _format_spice_value
        # Values between 1 and 1000 should not have suffix
        result = _format_spice_value(999.0)
        assert "k" not in result
        assert "M" not in result
        assert result == "999"


class TestParseOpOutput:
    """Test ngspice .op output parsing."""

    def test_parse_simple_voltage(self):
        from pqwave.analysis.worst_case import parse_op_output
        stdout = "v(out) = 5.000000e+00\nv(in) = 1.000000e+00\n"
        result = parse_op_output(stdout, "v(out)")
        assert abs(result - 5.0) < 1e-9

    def test_parse_first_voltage_when_no_target(self):
        from pqwave.analysis.worst_case import parse_op_output
        stdout = "v(1) = 3.300000e+00\nv(2) = 1.800000e+00\n"
        result = parse_op_output(stdout)
        assert abs(result - 3.3) < 1e-9

    def test_parse_no_match_returns_none(self):
        from pqwave.analysis.worst_case import parse_op_output
        stdout = "some random text\nwithout voltages\n"
        result = parse_op_output(stdout, "v(out)")
        assert result is None

    def test_parse_current(self):
        from pqwave.analysis.worst_case import parse_op_output
        stdout = "i(vsource) = 1.234000e-03\n"
        result = parse_op_output(stdout, "i(vsource)")
        assert abs(result - 0.001234) < 1e-9
