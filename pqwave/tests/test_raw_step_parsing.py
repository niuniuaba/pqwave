"""Tests for step-aware raw file parsing."""
import os
import pytest
from pqwave.models.rawfile import RawFile, parse_step_header, detect_naming_pattern


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "monte_carlo", "examples"
)


class TestStepHeaderParsing:
    """Parse QSPICE .step param lines from raw file header."""

    def test_parse_step_param_run(self):
        header = b'Flags: complex stepped\n.step param run 1 100 1\n.param temp=27\nBinary:\n'
        result = parse_step_header(header)
        assert result["step_count"] == 100
        assert result["step_param_names"] == ["run"]
        assert result["step_param_values"] == {"run": list(range(1, 101))}

    def test_parse_no_step_returns_none(self):
        header = b'Flags: real\nNo. Variables: 5\nBinary:\n'
        result = parse_step_header(header)
        assert result["step_count"] == 0


class TestNamingPatternDetection:
    """Detect vout0..voutN patterns in trace name lists."""

    def test_detect_vout_pattern(self):
        names = ["time", "vout0", "vout1", "vout2", "vout3", "vout4"]
        groups = detect_naming_pattern(names)
        assert "vout" in groups
        assert groups["vout"]["indices"] == [0, 1, 2, 3, 4]
        assert groups["vout"]["count"] == 5
        assert "time" not in groups  # single trace, not a group

    def test_detect_fft_pattern(self):
        names = ["frequency", "fft0", "fft1", "fft2"]
        groups = detect_naming_pattern(names)
        assert "fft" in groups
        assert groups["fft"]["count"] == 3

    def test_no_pattern_returns_empty(self):
        names = ["V(in)", "V(out)", "I(R1)"]
        groups = detect_naming_pattern(names)
        assert groups == {}

    def test_single_numeric_is_not_group(self):
        names = ["time", "vout0"]
        groups = detect_naming_pattern(names)
        assert groups == {}  # only one voutN, not a group
