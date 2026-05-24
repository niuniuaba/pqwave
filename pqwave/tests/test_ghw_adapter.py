"""Tests for GhwAdapter"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_ghw_adapter_missing_tool():
    """GhwAdapter raises when ghwdump is not found."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    state.tool_paths["ghwdump"] = ""

    with patch("shutil.which", return_value=None):
        try:
            from pqwave.models.ghw_adapter import GhwAdapter
            GhwAdapter("/nonexistent.ghw")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            msg = str(e)
            assert "ghwdump" in msg, f"Expected message to mention ghwdump, got: {msg}"
            assert "GHDL" in msg, f"Expected message to mention GHDL, got: {msg}"


def test_ghw_adapter_custom_tool_path():
    """GhwAdapter uses custom tool_path from settings."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    custom = "/opt/ghdl/bin/ghwdump"
    state.tool_paths["ghwdump"] = custom

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
            out = kwargs.get("stdout")
            if out is not None:
                out.write(vcd_content)
        return MagicMock(returncode=0)

    with patch("os.path.isfile", return_value=True), \
         patch("subprocess.run", side_effect=fake_run):
        from pqwave.models.ghw_adapter import GhwAdapter
        adapter = GhwAdapter("/test.ghw")
        names = adapter.get_variable_names()
        assert "top.clk" in names, f"Expected 'top.clk' in signal names, got: {names}"
        data = adapter.get_variable_data("top.clk")
        assert data is not None
        assert len(data) > 0

    state.tool_paths["ghwdump"] = ""


def test_ghw_adapter_conversion_failure():
    """GhwAdapter raises when ghwdump conversion fails."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    state.tool_paths["ghwdump"] = ""

    def fake_run(*args, **kwargs):
        raise Exception("Simulated conversion failure")

    with patch("shutil.which", return_value="/usr/bin/ghwdump"), \
         patch("subprocess.run", side_effect=fake_run):
        try:
            from pqwave.models.ghw_adapter import GhwAdapter
            GhwAdapter("/test.ghw")
            assert False, "Should have raised"
        except Exception as e:
            assert "test.ghw" in str(e).lower() or "conversion" in str(e).lower(), \
                f"Expected error about conversion, got: {e}"
