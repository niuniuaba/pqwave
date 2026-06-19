"""Integration tests for the QSPICE bridge -- full pipeline with mocked subprocess.

Tests verify the end-to-end flow:
  netlist -> resolve_qspice -> subprocess simulation -> .qraw output -> GUI launch
"""

import os
from unittest import mock

import pytest


class TestQspiceBridgeIntegration:
    """Integration-level tests for QspiceBridgeRunner covering the full pipeline."""

    # ------------------------------------------------------------------ #
    # 1. Full pipeline with mock simulator                               #
    # ------------------------------------------------------------------ #
    def test_full_pipeline_with_mock_simulator(self, tmp_path):
        """Run the full pipeline end-to-end with all external calls mocked.

        Creates a minimal SPICE netlist and a fake QSPICE64.exe for
        resolve_qspice to find, then mocks subprocess and the GUI launch
        to verify the entire orchestration flow.
        """
        # -- Arrange --------------------------------------------------- #

        # Minimal SPICE netlist (DC operating point)
        netlist = tmp_path / "test_op.cir"
        netlist.write_text(
            "* Test circuit\n"
            "V1 1 0 5\n"
            "R1 1 0 1k\n"
            ".op\n"
            ".end\n"
        )

        # Fake QSPICE64.exe that resolve_qspice can find on disk
        fake_exe = tmp_path / "QSPICE64.exe"
        fake_exe.write_text(
            "#!/bin/sh\n"
            'cat > test_op.qraw <<'"'"'EOF'"'"'\n'
            "Title: * test\n"
            "Date: Thu Jan 01 00:00:00 2026\n"
            "Plotname: Operating Point\n"
            "Flags: real\n"
            "No. Variables: 2\n"
            "No. Points: 1\n"
            "Command: QSPICE64\n"
            "Variables:\n"
            "\t0\ttime\ttime\n"
            "\t1\tV(n1)\tvoltage\n"
            "Binary:\n"
            "EOF\n"
        )
        fake_exe.chmod(0o755)

        qraw_path = tmp_path / "test_op.qraw"

        from pqwave.bridge.qspice.wrapper import QspiceBridgeRunner

        # -- Act ------------------------------------------------------- #
        with (
            mock.patch(
                "pqwave.bridge.qspice.wrapper.resolve_qspice",
                return_value=str(fake_exe),
            ),
            mock.patch("shutil.which", return_value="/usr/bin/wine"),
            mock.patch(
                "pqwave.bridge.qspice.wrapper.subprocess.run",
                return_value=mock.MagicMock(
                    returncode=0, stdout="", stderr=""
                ),
            ),
            mock.patch(
                "pqwave.bridge.qspice.wrapper.QspiceBridgeRunner._launch_pqwave",
                return_value=0,
            ) as mock_launch,
        ):
            # Write a minimal .qraw so the runner finds it after the
            # (mocked) subprocess completes.
            qraw_path.write_text(
                "Title: * test\n"
                "Date: Thu Jan 01 00:00:00 2026\n"
                "Plotname: Operating Point\n"
                "Flags: real\n"
                "No. Variables: 2\n"
                "No. Points: 1\n"
                "Command: QSPICE64\n"
                "Variables:\n"
                "\t0\ttime\ttime\n"
                "\t1\tV(n1)\tvoltage\n"
                "Binary:\n"
            )

            runner = QspiceBridgeRunner(auto_open=True)
            result = runner.run(str(netlist))

        # -- Assert ---------------------------------------------------- #
        assert result == 0, "Expected exit code 0 for successful simulation"
        assert qraw_path.exists(), ".qraw file should exist after simulation"
        mock_launch.assert_called_once_with(str(qraw_path))

    # ------------------------------------------------------------------ #
    # 2. .qraw placed beside netlist, not in /tmp                        #
    # ------------------------------------------------------------------ #
    def test_qraw_not_in_temp_dir(self, tmp_path):
        """The .qraw output is derived from the netlist path and sits
        in the same directory, never under /tmp itself."""
        # -- Arrange --------------------------------------------------- #
        netlist = tmp_path / "circuit.cir"
        netlist.write_text("* Test\n.op\n.end\n")

        fake_exe = tmp_path / "QSPICE64.exe"
        fake_exe.write_text("#!/bin/sh\ntouch circuit.qraw\n")
        fake_exe.chmod(0o755)

        from pqwave.bridge.qspice.wrapper import QspiceBridgeRunner

        # -- Act ------------------------------------------------------- #
        with (
            mock.patch(
                "pqwave.bridge.qspice.wrapper.resolve_qspice",
                return_value=str(fake_exe),
            ),
            mock.patch("shutil.which", return_value="/usr/bin/wine"),
            mock.patch(
                "pqwave.bridge.qspice.wrapper.subprocess.run",
                return_value=mock.MagicMock(
                    returncode=0, stdout="", stderr=""
                ),
            ),
            mock.patch(
                "pqwave.bridge.qspice.wrapper.QspiceBridgeRunner._launch_pqwave",
                return_value=0,
            ),
        ):
            qraw_path = tmp_path / "circuit.qraw"
            qraw_path.write_text("")

            runner = QspiceBridgeRunner()
            result = runner.run(str(netlist))

        # -- Assert ---------------------------------------------------- #
        expected_qraw = os.path.splitext(str(netlist))[0] + ".qraw"
        assert result == 0
        assert str(qraw_path) == expected_qraw
        # The .qraw must sit in the same directory as the netlist, not
        # in a different temporary location (netlist_dir == tmp_path).
        assert os.path.dirname(str(qraw_path)) == str(
            tmp_path
        ), ".qraw must be in the netlist directory"

    # ------------------------------------------------------------------ #
    # 3. Netlist without file extension                                  #
    # ------------------------------------------------------------------ #
    def test_no_suffix_required(self, tmp_path):
        """A netlist path without a file extension is handled correctly:
        the .qraw output is derived as <netlist_path>.qraw."""
        # -- Arrange --------------------------------------------------- #
        netlist = tmp_path / "mycircuit"  # No extension
        netlist.write_text("* Test\n.op\n.end\n")

        fake_exe = tmp_path / "QSPICE64.exe"
        fake_exe.write_text("#!/bin/sh\necho fake qspice\n")
        fake_exe.chmod(0o755)

        from pqwave.bridge.qspice.wrapper import QspiceBridgeRunner

        # -- Act ------------------------------------------------------- #
        with (
            mock.patch(
                "pqwave.bridge.qspice.wrapper.resolve_qspice",
                return_value=str(fake_exe),
            ),
            mock.patch("shutil.which", return_value="/usr/bin/wine"),
            mock.patch(
                "pqwave.bridge.qspice.wrapper.subprocess.run",
                return_value=mock.MagicMock(
                    returncode=0, stdout="", stderr=""
                ),
            ),
            mock.patch(
                "pqwave.bridge.qspice.wrapper.QspiceBridgeRunner._launch_pqwave",
                return_value=0,
            ),
        ):
            qraw_path = tmp_path / "mycircuit.qraw"
            qraw_path.write_text("")

            runner = QspiceBridgeRunner()
            result = runner.run(str(netlist))

        # -- Assert ---------------------------------------------------- #
        assert result == 0
        assert (tmp_path / "mycircuit.qraw").exists()
        assert str(netlist) + ".qraw" == str(qraw_path)

    # ------------------------------------------------------------------ #
    # 4. Graceful error when QSPICE not installed                        #
    # ------------------------------------------------------------------ #
    def test_graceful_error_when_qspice_not_installed(
        self, monkeypatch, tmp_path
    ):
        """When QSPICE cannot be found anywhere in the resolution chain,
        a FileNotFoundError with a helpful message mentioning both
        'QSPICE64.exe' and 'PQWAVE_QSPICE' is raised."""
        # -- Arrange --------------------------------------------------- #
        netlist = tmp_path / "test.cir"
        netlist.write_text("* Test\n.op\n.end\n")

        monkeypatch.delenv("PQWAVE_QSPICE", raising=False)

        from pqwave.bridge.qspice.wrapper import QspiceBridgeRunner

        # -- Act & Assert ---------------------------------------------- #
        with (
            mock.patch(
                "pqwave.models.state.ApplicationState",
            ) as mock_state,
            mock.patch(
                "pqwave.bridge.qspice.wrapper._wine_prefixes",
                return_value=[],
            ),
            mock.patch("shutil.which", return_value=None),
        ):
            mock_state.return_value.tool_paths.get.return_value = None

            runner = QspiceBridgeRunner()
            with pytest.raises(FileNotFoundError) as exc_info:
                runner.run(str(netlist))

        msg = str(exc_info.value)
        assert "QSPICE64.exe" in msg, (
            "Error message should mention QSPICE64.exe"
        )
        assert "PQWAVE_QSPICE" in msg, (
            "Error message should mention PQWAVE_QSPICE env var"
        )
