"""Tests for FstAdapter"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


def test_fst_adapter_missing_tool():
    """FstAdapter raises when fst2vcd is not found."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    # Ensure tool_paths is empty and shutil.which returns None
    state = ApplicationState()
    state.tool_paths["fst2vcd"] = ""

    with patch("shutil.which", return_value=None):
        try:
            from pqwave.models.fst_adapter import FstAdapter
            FstAdapter("/nonexistent.fst")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            msg = str(e)
            assert "fst2vcd" in msg, f"Expected message to mention fst2vcd, got: {msg}"
            assert "gtkwave" in msg, f"Expected message to mention gtkwave, got: {msg}"


def test_fst_adapter_custom_tool_path():
    """FstAdapter uses custom tool_path from settings."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    custom = "/opt/my/gtkwave/bin/fst2vcd"
    state.tool_paths["fst2vcd"] = custom

    # Mock subprocess.run to succeed and create a minimal VCD file
    vcd_content = (
        "$date test $end\n"
        "$version test $end\n"
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n#10\n1!\n"
    )

    def fake_run(args, **kwargs):
        if args[0] == custom:
            with open(args[3], 'w') as f:
                f.write(vcd_content)
        return MagicMock(returncode=0)

    with patch("os.path.isfile", return_value=True), \
         patch("subprocess.run", side_effect=fake_run):
        from pqwave.models.fst_adapter import FstAdapter
        adapter = FstAdapter("/test.fst")
        names = adapter.get_variable_names()
        assert "top.clk" in names, f"Expected 'top.clk' in signal names, got: {names}"
        data = adapter.get_variable_data("top.clk")
        assert data is not None
        assert len(data) > 0

    # Cleanup
    state.tool_paths["fst2vcd"] = ""


def test_fst_adapter_conversion_failure():
    """FstAdapter raises when fst2vcd conversion fails."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    state.tool_paths["fst2vcd"] = ""

    def fake_run(*args, **kwargs):
        raise Exception("Simulated conversion failure")

    with patch("shutil.which", return_value="/usr/bin/fst2vcd"), \
         patch("subprocess.run", side_effect=fake_run):
        try:
            from pqwave.models.fst_adapter import FstAdapter
            FstAdapter("/test.fst")
            assert False, "Should have raised"
        except Exception as e:
            assert "test.fst" in str(e).lower() or "conversion" in str(e).lower(), \
                f"Expected error about conversion, got: {e}"
