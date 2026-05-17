"""Tests for MC API commands."""
from pqwave.session.api import SessionAPI, get_command_registry


class TestMCCmdRegistration:
    def test_mc_commands_registered(self):
        registry = get_command_registry()
        mc_cmds = [k for k in registry if k.startswith("mc_")]
        assert "mc_load" in mc_cmds, f"mc_load not found in {sorted(registry.keys())}"
        assert "mc_stats" in mc_cmds
        assert "mc_style" in mc_cmds
        assert "mc_histogram" in mc_cmds

    def test_multi_dataset_commands_registered(self):
        registry = get_command_registry()
        assert "datasets" in registry, f"datasets not in {sorted(registry.keys())}"
        assert "unload" in registry

    def test_mc_commands_have_help(self):
        registry = get_command_registry()
        for cmd in ["mc_load", "mc_stats", "mc_yield"]:
            if cmd in registry:
                assert registry[cmd]["help"], f"{cmd} has no help text"


class TestDatasetCommands:
    def test_datasets_command(self):
        session = SessionAPI()
        result = session.datasets()
        assert isinstance(result, list)

    def test_unload_command(self):
        session = SessionAPI()
        session._state.clear_datasets()
        session._state.add_dataset("dummy")
        assert len(session._state.datasets) == 1
        session.unload(0)
        assert len(session._state.datasets) == 0
