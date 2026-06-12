"""Unit tests for the Qucs-S bridge wrapper module.

These tests exercise every public function and the QucsBridgeRunner
orchestrator.  Subprocess calls are mocked so the tests run without a
real ngspice installation.
"""

import os
import shutil
import subprocess
import sys
from unittest import mock

import pytest

from pqwave.bridge.qucs_s.wrapper import (
    QucsBridgeRunner,
    copy_output_files,
    extract_schematic_path,
    find_output_files,
    main,
    resolve_ngspice,
)


# ---------------------------------------------------------------------------
# resolve_ngspice
# ---------------------------------------------------------------------------

class TestResolveNgspice:
    """Tests for :func:`resolve_ngspice`."""

    def test_uses_env_var_first(self, monkeypatch, tmp_path):
        """PQWAVE_NGSPICE env var takes highest priority."""
        fake = tmp_path / "custom-ngspice"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)
        monkeypatch.setenv("PQWAVE_NGSPICE", str(fake))
        result = resolve_ngspice()
        assert result == str(fake)

    def test_env_var_not_a_file_skipped(self, monkeypatch):
        """Non-existent PQWAVE_NGSPICE value is ignored."""
        monkeypatch.setenv("PQWAVE_NGSPICE", "/nonexistent/ngspice")
        with mock.patch.object(shutil, "which", return_value=None):
            with pytest.raises(FileNotFoundError):
                resolve_ngspice()

    def test_falls_back_to_tool_paths(self, monkeypatch):
        """Tool paths config is checked after env var."""
        monkeypatch.delenv("PQWAVE_NGSPICE", raising=False)
        state = mock.MagicMock()
        state.tool_paths = {"ngspice": "/configured/ngspice"}
        with mock.patch(
            "pqwave.models.state.ApplicationState",
            return_value=state,
        ):
            with mock.patch.object(shutil, "which", return_value=None):
                with mock.patch("os.path.isfile", return_value=True):
                    result = resolve_ngspice()
                    assert result == "/configured/ngspice"

    def test_falls_back_to_path(self, monkeypatch):
        """shutil.which is checked as last resort."""
        monkeypatch.delenv("PQWAVE_NGSPICE", raising=False)
        found = "/usr/bin/ngspice"
        with mock.patch.object(shutil, "which", return_value=found):
            result = resolve_ngspice()
            assert result == found

    def test_raises_when_not_found(self, monkeypatch):
        """FileNotFoundError when ngspice is not discoverable."""
        monkeypatch.delenv("PQWAVE_NGSPICE", raising=False)
        with mock.patch.object(shutil, "which", return_value=None):
            with mock.patch("os.path.isfile", return_value=False):
                with pytest.raises(FileNotFoundError, match="ngspice not found"):
                    resolve_ngspice()


# ---------------------------------------------------------------------------
# extract_schematic_path
# ---------------------------------------------------------------------------

class TestExtractSchematicPath:
    """Tests for :func:`extract_schematic_path`."""

    def test_valid_header(self, tmp_path):
        """Standard Qucs-S netlist header line is parsed correctly."""
        netlist = tmp_path / "spice4qucs.cir"
        netlist.write_text(
            "* Qucs 0.0.24  /home/user/projects/bridge.sch\n"
            ".title test\n"
        )
        result = extract_schematic_path(str(netlist))
        assert result == ("/home/user/projects", "bridge")

    def test_spaces_in_path(self, tmp_path):
        """Schematic path containing spaces is handled."""
        netlist = tmp_path / "spice4qucs.cir"
        netlist.write_text(
            "* Qucs 0.0.24  /home/user/my projects/bridge.sch\n"
        )
        result = extract_schematic_path(str(netlist))
        assert result == ("/home/user/my projects", "bridge")

    def test_missing_header(self, tmp_path):
        """Netlist without the Qucs header returns None."""
        netlist = tmp_path / "spice4qucs.cir"
        netlist.write_text(".title test\nR1 1 0 1k\n")
        result = extract_schematic_path(str(netlist))
        assert result is None

    def test_empty_file(self, tmp_path):
        """Empty netlist returns None."""
        netlist = tmp_path / "spice4qucs.cir"
        netlist.write_text("")
        result = extract_schematic_path(str(netlist))
        assert result is None

    def test_nonexistent_file(self):
        """Non-existent file returns None (OSError caught)."""
        result = extract_schematic_path("/nonexistent/netlist.cir")
        assert result is None

    def test_extra_whitespace_in_header(self, tmp_path):
        """Header with extra leading/trailing whitespace is tolerated."""
        netlist = tmp_path / "spice4qucs.cir"
        netlist.write_text(
            "* Qucs 0.0.24  /home/user/projects/bridge.sch  \n"
        )
        result = extract_schematic_path(str(netlist))
        assert result == ("/home/user/projects", "bridge")


# ---------------------------------------------------------------------------
# find_output_files
# ---------------------------------------------------------------------------

class TestFindOutputFiles:
    """Tests for :func:`find_output_files`."""

    def test_finds_all_output_types(self, tmp_path):
        """All spice4qucs.* files are discovered."""
        files = [
            "spice4qucs.cir",
            "spice4qucs.tran1.plot",
            "spice4qucs.ac1.raw",
            "spice4qucs.dc.print",
            "spice4qucs.tran1.four",
        ]
        for f in files:
            (tmp_path / f).write_text("data")

        found = find_output_files(str(tmp_path))
        expected = sorted(str(tmp_path / f) for f in files)
        assert found == expected

    def test_returns_sorted(self, tmp_path):
        """Output is sorted alphabetically."""
        (tmp_path / "spice4qucs.ac1.raw").write_text("a")
        (tmp_path / "spice4qucs.cir").write_text("b")
        found = find_output_files(str(tmp_path))
        assert found == sorted(found)

    def test_excludes_directories(self, tmp_path):
        """Directories matching the prefix are not included."""
        (tmp_path / "spice4qucs.mydir").mkdir()
        (tmp_path / "spice4qucs.cir").write_text("data")
        found = find_output_files(str(tmp_path))
        assert len(found) == 1
        assert found[0].endswith("spice4qucs.cir")

    def test_excludes_prefix_without_extension(self, tmp_path):
        """The bare 'spice4qucs' file without an extension is excluded."""
        (tmp_path / "spice4qucs").write_text("bare")
        (tmp_path / "spice4qucs.cir").write_text("data")
        found = find_output_files(str(tmp_path))
        assert len(found) == 1
        assert found[0].endswith("spice4qucs.cir")

    def test_empty_directory(self, tmp_path):
        """Empty workdir returns an empty list."""
        found = find_output_files(str(tmp_path))
        assert found == []

    def test_non_existent_directory(self):
        """Non-existent workdir returns an empty list."""
        found = find_output_files("/nonexistent/dir")
        assert found == []

    def test_ignores_unrelated_files(self, tmp_path):
        """Files not matching the prefix are ignored."""
        (tmp_path / "other.log").write_text("log")
        (tmp_path / "spice4qucs.cir").write_text("data")
        found = find_output_files(str(tmp_path))
        assert len(found) == 1
        assert found[0].endswith("spice4qucs.cir")


# ---------------------------------------------------------------------------
# copy_output_files
# ---------------------------------------------------------------------------

class TestCopyOutputFiles:
    """Tests for :func:`copy_output_files`."""

    def test_renames_prefix(self, tmp_path):
        """spice4qucs.<ext> is renamed to <basename>.<ext>."""
        src_dir = tmp_path / "workdir"
        dst_dir = tmp_path / "simulation"
        src_dir.mkdir()
        (src_dir / "spice4qucs.tran1.plot").write_text("tran data")
        (src_dir / "spice4qucs.dc.print").write_text("dc data")

        files = [
            str(src_dir / "spice4qucs.tran1.plot"),
            str(src_dir / "spice4qucs.dc.print"),
        ]
        copied = copy_output_files(files, str(dst_dir), "bridge")

        assert len(copied) == 2
        assert os.path.isfile(dst_dir / "bridge.tran1.plot")
        assert os.path.isfile(dst_dir / "bridge.dc.print")

    def test_creates_sim_dir(self, tmp_path):
        """Destination directory is created if it does not exist."""
        src_dir = tmp_path / "workdir"
        src_dir.mkdir()
        (src_dir / "spice4qucs.cir").write_text("netlist")
        dst_dir = tmp_path / "simulation"

        files = [str(src_dir / "spice4qucs.cir")]
        copied = copy_output_files(files, str(dst_dir), "bridge")
        assert len(copied) == 1
        assert dst_dir.is_dir()
        assert (dst_dir / "bridge.cir").is_file()

    def test_skips_identical_files(self, tmp_path):
        """Files that already exist with the same size are skipped."""
        src_dir = tmp_path / "workdir"
        dst_dir = tmp_path / "simulation"
        src_dir.mkdir()
        dst_dir.mkdir()

        src = src_dir / "spice4qucs.tran1.plot"
        dst = dst_dir / "bridge.tran1.plot"
        src.write_text("same content")
        dst.write_text("same content")

        # Make destination newer than source (simulates already-copied)
        dst_mtime = os.path.getmtime(dst)
        os.utime(src, (dst_mtime - 10, dst_mtime - 10))

        files = [str(src)]
        copied = copy_output_files(files, str(dst_dir), "bridge")
        assert len(copied) == 0

    def test_overwrites_stale_file(self, tmp_path):
        """Older destination is overwritten by newer source."""
        src_dir = tmp_path / "workdir"
        dst_dir = tmp_path / "simulation"
        src_dir.mkdir()
        dst_dir.mkdir()

        src = src_dir / "spice4qucs.tran1.plot"
        dst = dst_dir / "bridge.tran1.plot"
        src.write_text("new longer content")
        dst.write_text("old")

        # Make destination older than source (simulates previous run)
        src_mtime = os.path.getmtime(src)
        os.utime(dst, (src_mtime - 10, src_mtime - 10))

        files = [str(src)]
        copied = copy_output_files(files, str(dst_dir), "bridge")
        assert len(copied) == 1
        with open(dst) as f:
            assert f.read() == "new longer content"


# ---------------------------------------------------------------------------
# QucsBridgeRunner
# ---------------------------------------------------------------------------

class TestQucsBridgeRunner:
    """Tests for the :class:`QucsBridgeRunner` orchestrator."""

    # ------------------------------------------------------------------
    # Full pipeline mock
    # ------------------------------------------------------------------

    def test_full_pipeline(self, tmp_path, monkeypatch):
        """End-to-end pipeline: run ngspice, copy files, launch pqwave."""
        monkeypatch.delenv("PQWAVE_NGSPICE", raising=False)
        monkeypatch.setenv("PQWAVE_QUCS_AUTO_OPEN", "1")

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        sch_dir = tmp_path / "projects"
        sch_dir.mkdir()

        (workdir / "spice4qucs.cir").write_text(
            f"* Qucs 0.0.24  {sch_dir}/bridge.sch\n"
            ".title test\n"
        )
        (workdir / "spice4qucs.tran1.plot").write_text("tran data")

        runner = QucsBridgeRunner(
            ngspice_path="/fake/ngspice", auto_open=True
        )

        mock_proc = mock.MagicMock(returncode=0, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=mock_proc) as mock_run:
            with mock.patch.object(
                runner, "_launch_pqwave", return_value=0
            ) as mock_launch:
                exit_code = runner.run(str(workdir), "spice4qucs.cir")
                assert exit_code == 0
                mock_run.assert_called_once_with(
                    ["/fake/ngspice", "-b", "spice4qucs.cir"],
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                )
                mock_launch.assert_called_once()
                copied_arg = mock_launch.call_args[0][0]
                # Only waveform data files are passed to pqwave (.plot, .raw)
                # .cir and .cfg files are copied but not opened
                assert len(copied_arg) == 1
                copied_names = [os.path.basename(p) for p in copied_arg]
                assert "bridge.tran1.plot" in copied_names

    # ------------------------------------------------------------------
    # Ngspice failure path
    # ------------------------------------------------------------------

    def test_ngspice_failure_returns_exit_code(self, tmp_path):
        """When ngspice exits non-zero, the exit code is returned verbatim."""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        netlist = workdir / "spice4qucs.cir"
        netlist.write_text("* Qucs 0.0.24  /tmp/bridge.sch\n")

        runner = QucsBridgeRunner(
            ngspice_path="/fake/ngspice", auto_open=True
        )

        mock_proc = mock.MagicMock(returncode=3, stdout="", stderr="error")
        with mock.patch("subprocess.run", return_value=mock_proc) as mock_run:
            with mock.patch.object(
                runner, "_launch_pqwave", return_value=0
            ) as mock_launch:
                exit_code = runner.run(str(workdir), "spice4qucs.cir")
                assert exit_code == 3
                mock_run.assert_called_once()
                mock_launch.assert_not_called()

    # ------------------------------------------------------------------
    # Missing schematic path
    # ------------------------------------------------------------------

    def test_missing_schematic_path_fallback(self, tmp_path):
        """When the netlist header lacks a .sch path, outputs go to
        CWD/simulation/ and no pqwave is launched."""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        netlist = workdir / "spice4qucs.cir"
        netlist.write_text("* Qucs 0.0.24  \n.title test\n")

        (workdir / "spice4qucs.tran1.plot").write_text("tran data")

        runner = QucsBridgeRunner(
            ngspice_path="/fake/ngspice", auto_open=True
        )

        mock_proc = mock.MagicMock(returncode=0, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=mock_proc):
            with mock.patch.object(
                runner, "_launch_pqwave", return_value=0
            ) as mock_launch:
                exit_code = runner.run(str(workdir), "spice4qucs.cir")
                assert exit_code == 0
                # No launch because schematic path was missing
                mock_launch.assert_not_called()
                # Output files kept original names (basename="spice4qucs")
                fallback = workdir / "simulation" / "spice4qucs.tran1.plot"
                assert fallback.is_file()

    # ------------------------------------------------------------------
    # auto_open=False
    # ------------------------------------------------------------------

    def test_auto_open_false_skips_launch(self, tmp_path, monkeypatch):
        """When auto_open is False, files are copied but pqwave is not launched."""
        monkeypatch.setenv("PQWAVE_QUCS_AUTO_OPEN", "0")
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        sch_dir = tmp_path / "projects"
        sch_dir.mkdir()
        (workdir / "spice4qucs.cir").write_text(
            f"* Qucs 0.0.24  {sch_dir}/bridge.sch\n"
        )
        (workdir / "spice4qucs.tran1.plot").write_text("tran data")

        runner = QucsBridgeRunner(
            ngspice_path="/fake/ngspice", auto_open=True
        )

        mock_proc = mock.MagicMock(returncode=0, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=mock_proc):
            with mock.patch.object(
                runner, "_launch_pqwave", return_value=0
            ) as mock_launch:
                exit_code = runner.run(str(workdir), "spice4qucs.cir")
                assert exit_code == 0
                mock_launch.assert_not_called()
                assert (sch_dir / "simulation" / "bridge.tran1.plot").is_file()

    # ------------------------------------------------------------------
    # _launch_pqwave
    # ------------------------------------------------------------------

    def test_launch_pqwave_detached(self, tmp_path):
        """pqwave is launched with start_new_session=True."""
        copied = [str(tmp_path / "bridge.tran1.plot")]
        with mock.patch("subprocess.Popen") as mock_popen:
            exit_code = QucsBridgeRunner._launch_pqwave(copied)
            assert exit_code == 0
            mock_popen.assert_called_once()
            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs["start_new_session"] is True
            assert call_kwargs["stdin"] == subprocess.DEVNULL
            assert call_kwargs["stdout"] == subprocess.DEVNULL
            assert call_kwargs["stderr"] == subprocess.DEVNULL

            cmd = mock_popen.call_args[0][0]
            assert cmd[0] == sys.executable
            assert cmd[1] == "-m"
            assert cmd[2] == "pqwave.main"
            assert copied[0] in cmd

    def test_launch_pqwave_file_not_found(self, tmp_path):
        """When pqwave is not found, a warning is printed and 0 is returned."""
        copied = [str(tmp_path / "bridge.tran1.plot")]
        with mock.patch("subprocess.Popen", side_effect=FileNotFoundError):
            exit_code = QucsBridgeRunner._launch_pqwave(copied)
            assert exit_code == 0


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

class TestMain:
    """Smoke tests for the ``main()`` entry point."""

    def test_no_args_prints_usage(self, capsys):
        """Calling main() with no args prints usage and returns 1."""
        with mock.patch.object(sys, "argv", ["pqwave"]):
            exit_code = main()
            assert exit_code == 1
            captured = capsys.readouterr()
            assert "Usage" in captured.err

    def test_with_netlist_arg_calls_runner(self, tmp_path, monkeypatch):
        """With a valid netlist arg, the runner is invoked."""
        monkeypatch.delenv("PQWAVE_NGSPICE", raising=False)
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        netlist = workdir / "spice4qucs.cir"
        netlist.write_text(
            f"* Qucs 0.0.24  {tmp_path}/bridge.sch\n"
            ".title test\n"
        )

        # Change CWD to workdir so main() picks it up
        with mock.patch.object(sys, "argv", [
            "pqwave", "--qucs-bridge", str(netlist)
        ]):
            mock_proc = mock.MagicMock(returncode=0, stdout="", stderr="")
            with mock.patch("subprocess.run", return_value=mock_proc):
                with mock.patch(
                    "pqwave.bridge.qucs_s.wrapper.QucsBridgeRunner._launch_pqwave",
                    return_value=0,
                ):
                    exit_code = main()
                    assert exit_code == 0
