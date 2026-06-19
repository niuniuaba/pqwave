"""Tests for the QSPICE bridge wrapper."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestResolveQspice:
    """Tests for resolve_qspice() priority chain."""

    # ------------------------------------------------------------------ #
    # 1. PQWAVE_QSPICE env var takes priority                            #
    # ------------------------------------------------------------------ #
    def test_env_var_takes_priority(self, monkeypatch, tmp_path):
        """Set PQWAVE_QSPICE to a real file — should be returned."""
        fake_exe = tmp_path / "QSPICE64.exe"
        fake_exe.write_text("")

        monkeypatch.setenv("PQWAVE_QSPICE", str(fake_exe))

        from pqwave.bridge.qspice.wrapper import resolve_qspice

        result = resolve_qspice()
        assert result == str(fake_exe)

    # ------------------------------------------------------------------ #
    # 2. PQWAVE_QSPICE env var points to missing file — fall through    #
    # ------------------------------------------------------------------ #
    def test_env_var_ignored_if_file_missing(self, monkeypatch):
        """Env var set but file does not exist — must raise."""
        monkeypatch.setenv("PQWAVE_QSPICE", "/nonexistent/qspice.exe")

        # Stub out deeper levels so the only reason to fail is the
        # missing env-var file.
        with (
            patch("pqwave.models.state.ApplicationState") as mock_state,
            patch(
                "pqwave.bridge.qspice.wrapper._wine_prefixes", return_value=[]
            ),
            patch("shutil.which", return_value=None),
        ):
            mock_state.return_value.tool_paths.get.return_value = None

            from pqwave.bridge.qspice.wrapper import resolve_qspice

            with pytest.raises(FileNotFoundError):
                resolve_qspice()

    # ------------------------------------------------------------------ #
    # 3. ApplicationState.tool_paths used when no env var                #
    # ------------------------------------------------------------------ #
    def test_tool_paths_used_when_no_env_var(self, monkeypatch, tmp_path):
        """No env var — should pick up tool_paths entry."""
        fake_exe = tmp_path / "QSPICE64.exe"
        fake_exe.write_text("")

        monkeypatch.delenv("PQWAVE_QSPICE", raising=False)

        with (
            patch("pqwave.models.state.ApplicationState") as mock_state,
        ):
            mock_state.return_value.tool_paths.get.return_value = str(fake_exe)

            from pqwave.bridge.qspice.wrapper import resolve_qspice

            result = resolve_qspice()
            assert result == str(fake_exe)
            mock_state.return_value.tool_paths.get.assert_called_once_with(
                "qspice"
            )

    # ------------------------------------------------------------------ #
    # 4. tool_paths entry missing file — skip and continue               #
    # ------------------------------------------------------------------ #
    def test_tool_paths_skipped_if_file_missing(self, monkeypatch):
        """tool_paths points to missing file — must fall through."""
        monkeypatch.delenv("PQWAVE_QSPICE", raising=False)

        with (
            patch("pqwave.models.state.ApplicationState") as mock_state,
            patch(
                "pqwave.bridge.qspice.wrapper._wine_prefixes", return_value=[]
            ),
            patch("shutil.which", return_value=None),
        ):
            mock_state.return_value.tool_paths.get.return_value = (
                "/nonexistent/qspice.exe"
            )

            from pqwave.bridge.qspice.wrapper import resolve_qspice

            with pytest.raises(FileNotFoundError):
                resolve_qspice()

    # ------------------------------------------------------------------ #
    # 5. Wine prefix search — QSPICE64.exe                              #
    # ------------------------------------------------------------------ #
    def test_wine_prefix_search_finds_exe(self, monkeypatch, tmp_path):
        """Search wine prefixes and find QSPICE64.exe."""
        # Create the fake directory structure
        prefix_dir = tmp_path / "wine_prefix"
        exe_path = (
            prefix_dir / "drive_c" / "Program Files" / "QSPICE" / "QSPICE64.exe"
        )
        exe_path.parent.mkdir(parents=True)
        exe_path.write_text("")

        monkeypatch.delenv("PQWAVE_QSPICE", raising=False)

        with (
            patch("pqwave.models.state.ApplicationState") as mock_state,
            patch(
                "pqwave.bridge.qspice.wrapper._wine_prefixes",
                return_value=[str(prefix_dir)],
            ),
            patch("shutil.which", return_value=None),
        ):
            mock_state.return_value.tool_paths.get.return_value = None

            from pqwave.bridge.qspice.wrapper import resolve_qspice

            result = resolve_qspice()
            assert result == str(exe_path)

    # ------------------------------------------------------------------ #
    # 6. Wine prefix search — QSPICE.exe (32-bit fallback)              #
    # ------------------------------------------------------------------ #
    def test_wine_prefix_finds_qspice_exe_not_64(self, monkeypatch, tmp_path):
        """Search wine prefixes and find QSPICE.exe (no 64-bit variant)."""
        prefix_dir = tmp_path / "wine_prefix32"
        exe_path = (
            prefix_dir / "drive_c" / "Program Files" / "QSPICE" / "QSPICE.exe"
        )
        exe_path.parent.mkdir(parents=True)
        exe_path.write_text("")

        monkeypatch.delenv("PQWAVE_QSPICE", raising=False)

        with (
            patch("pqwave.models.state.ApplicationState") as mock_state,
            patch(
                "pqwave.bridge.qspice.wrapper._wine_prefixes",
                return_value=[str(prefix_dir)],
            ),
            patch("shutil.which", return_value=None),
        ):
            mock_state.return_value.tool_paths.get.return_value = None

            from pqwave.bridge.qspice.wrapper import resolve_qspice

            result = resolve_qspice()
            assert result == str(exe_path)

    # ------------------------------------------------------------------ #
    # 7. All levels fail — FileNotFoundError with helpful message        #
    # ------------------------------------------------------------------ #
    def test_file_not_found_error(self, monkeypatch):
        """All levels fail — check error message content."""
        monkeypatch.delenv("PQWAVE_QSPICE", raising=False)

        with (
            patch("pqwave.models.state.ApplicationState") as mock_state,
            patch(
                "pqwave.bridge.qspice.wrapper._wine_prefixes", return_value=[]
            ),
            patch("shutil.which", return_value=None),
        ):
            mock_state.return_value.tool_paths.get.return_value = None

            from pqwave.bridge.qspice.wrapper import resolve_qspice

            with pytest.raises(FileNotFoundError) as exc_info:
                resolve_qspice()
            msg = str(exc_info.value)
            assert "QSPICE64.exe" in msg
            assert "PQWAVE_QSPICE" in msg
