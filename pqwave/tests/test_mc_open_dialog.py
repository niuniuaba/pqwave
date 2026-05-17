"""Tests for MCOpenDialog configuration parsing."""
from pqwave.ui.mc_open_dialog import MCConfig


class TestMCConfig:
    def test_single_stepped_config(self):
        cfg = MCConfig(
            source_type="stepped",
            file_path="/tmp/test.raw",
            grouping_pattern=None,
        )
        assert cfg.source_type == "stepped"
        assert cfg.is_stepped
        assert not cfg.is_multi_file

    def test_multi_file_config(self):
        cfg = MCConfig(
            source_type="multi",
            file_paths=["/tmp/r1.raw", "/tmp/r2.raw"],
        )
        assert cfg.source_type == "multi"
        assert cfg.is_multi_file
        assert not cfg.is_stepped

    def test_pattern_config(self):
        cfg = MCConfig(
            source_type="pattern",
            file_path="/tmp/test.raw",
            grouping_pattern="vout",
        )
        assert cfg.grouping_pattern == "vout"
