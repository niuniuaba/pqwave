"""Tests for QUX-based .qraw reader."""

import os
import sys
from unittest import mock

import numpy as np
import pytest

from pqwave.bridge.qspice.qux_reader import (
    _parse_spice_metadata,
    _parse_csv_data,
    load_qraw_via_qux,
)


class TestParseSpiceMetadata:
    def test_ac_analysis(self):
        stdout = (
            "No. Points: 400\n"
            "Plotname: AC Analysis\n"
            "Abscissa: 1.0 100000000.0\n"
            "Flags: complex\n"
            "Variables:\n"
            "\t0\tFreq\tfrequency\n"
            "\t1\tV(vout)\tcomplex\n"
            "Values:\n"
        )
        meta = _parse_spice_metadata(stdout)
        assert meta["n_points"] == 400
        assert meta["plotname"] == "AC Analysis"
        assert meta["is_ac"] is True
        assert meta["is_complex"] is True
        assert meta["x_label"] == "Freq"
        assert meta["x_min"] == 1.0
        assert meta["x_max"] == 100000000.0

    def test_transient_analysis(self):
        stdout = (
            "No. Points: 5000\n"
            "Plotname: Transient Analysis\n"
            "Flags: real\n"
            "Variables:\n"
            "\t0\ttime\ttime\n"
            "\t1\tV(out)\tvoltage\n"
            "Values:\n"
        )
        meta = _parse_spice_metadata(stdout)
        assert meta["n_points"] == 5000
        assert meta["is_complex"] is False
        assert meta["is_ac"] is False
        assert meta["x_label"] == "time"  # first var name after Variables:

    def test_dc_analysis(self):
        stdout = (
            "No. Points: 30000\n"
            "Plotname: DC Transfer Characteristic\n"
            "Flags: real\n"
            "Variables:\n"
            "\t0\tV2\tvoltage\n"
            "\t1\tId(J1)\tcurrent\n"
            "Values:\n"
        )
        meta = _parse_spice_metadata(stdout)
        assert meta["n_points"] == 30000
        assert meta["x_label"] == "V2"  # first variable after Variables:
        assert meta["is_complex"] is False

    def test_missing_plotname(self):
        stdout = "No. Points: 100\nFlags: real\n"
        meta = _parse_spice_metadata(stdout)
        assert meta["n_points"] == 100
        assert "plotname" not in meta

    def test_empty_stdout(self):
        meta = _parse_spice_metadata("")
        assert meta.get("n_points", 0) == 0
        assert meta.get("step_count", 0) == 0


class TestParseCsvData:
    def test_transient_real_data(self):
        stdout = "0.0,1.0,2.0\n0.1,1.1,2.1\n0.2,1.2,2.2\n"
        data = _parse_csv_data(stdout, ["time", "V(out)", "I(R1)"], is_complex=False)
        assert data.shape == (3, 3)
        assert data.dtype == np.float32
        assert data[0, 0] == pytest.approx(0.0)
        assert data[1, 1] == pytest.approx(1.1)
        assert data[2, 2] == pytest.approx(2.2)

    def test_ac_complex_data(self):
        stdout = "1.0\t10.0-1.0\n10.0\t5.0+2.0\n"
        data = _parse_csv_data(stdout, ["Freq", "V(out)"], is_complex=True)
        assert data.shape == (2, 2)
        assert np.iscomplexobj(data)
        assert data[0, 0] == pytest.approx(complex(1, 0))
        assert data[0, 1] == pytest.approx(complex(10, -1))
        assert data[1, 1] == pytest.approx(complex(5, 2))

    def test_empty_csv(self):
        data = _parse_csv_data("", ["a"], is_complex=False)
        assert data.size == 0


class TestLoadQrawViaQux:
    # resolve_qux is imported lazily inside load_qraw_via_qux via
    #   from pqwave.bridge.qspice.wrapper import resolve_qux
    # so the mock target is the wrapper module, not qux_reader.

    def test_qux_unavailable(self):
        """Returns None when QUX.exe is not found."""
        with mock.patch(
            "pqwave.bridge.qspice.wrapper.resolve_qux", return_value=None
        ):
            result = load_qraw_via_qux("/fake/path.qraw", ["V(out)"])
            assert result is None

    def test_empty_var_names(self):
        """Returns None when no variable names provided."""
        with mock.patch(
            "pqwave.bridge.qspice.wrapper.resolve_qux",
            return_value="/fake/qux.exe",
        ):
            result = load_qraw_via_qux("/fake/path.qraw", [])
            assert result is None

    def test_successful_load(self, monkeypatch):
        """Happy path: QUX returns valid metadata and data."""
        monkeypatch.setattr(sys, "platform", "linux")

        spice_stdout = (
            "No. Points: 3\n"
            "Plotname: Transient Analysis\n"
            "Flags: real\n"
            "Variables:\n"
            "\t0\ttime\ttime\n"
            "\t1\tV(out)\tvoltage\n"
            "Values:\n"
        )
        csv_stdout = "0.0,1.0\n0.1,2.0\n0.2,3.0\n"

        call_count = [0]

        def fake_run(cmd, **_kwargs):
            call_count[0] += 1
            result = mock.MagicMock()
            result.returncode = 0
            if call_count[0] == 1:
                result.stdout = spice_stdout
                result.stderr = ""
            else:
                result.stdout = csv_stdout
                result.stderr = ""
            return result

        with mock.patch(
            "pqwave.bridge.qspice.wrapper.resolve_qux",
            return_value="/fake/qux.exe",
        ):
            with mock.patch("shutil.which", return_value="/usr/bin/wine"):
                with mock.patch("subprocess.run", side_effect=fake_run):
                    result = load_qraw_via_qux(
                        "/fake/path.qraw", ["time", "V(out)"]
                    )
                    assert result is not None
                    data, meta = result
                    assert data.shape == (3, 2)
                    assert meta["n_points"] == 3
                    assert meta["is_complex"] is False

    def test_qux_nonzero_exit(self, monkeypatch):
        """Returns None when QUX exits non-zero."""
        monkeypatch.setattr(sys, "platform", "linux")
        bad_proc = mock.MagicMock()
        bad_proc.returncode = 1
        bad_proc.stderr = "error"

        with mock.patch(
            "pqwave.bridge.qspice.wrapper.resolve_qux",
            return_value="/fake/qux.exe",
        ):
            with mock.patch("shutil.which", return_value="/usr/bin/wine"):
                with mock.patch("subprocess.run", return_value=bad_proc):
                    result = load_qraw_via_qux(
                        "/fake/path.qraw", ["V(out)"]
                    )
                    assert result is None

    def test_wine_not_found_on_linux(self, monkeypatch):
        """Returns None when wine is missing."""
        monkeypatch.setattr(sys, "platform", "linux")
        with mock.patch(
            "pqwave.bridge.qspice.wrapper.resolve_qux",
            return_value="/fake/qux.exe",
        ):
            with mock.patch("shutil.which", return_value=None):
                result = load_qraw_via_qux("/fake/path.qraw", ["V(out)"])
                assert result is None


class TestRawFileQuxFallback:
    """Verify RawFile._try_load_qux correctly gates on QSPICE markers."""

    def test_skips_non_qspice_file(self):
        """Returns None for ngspice .raw files (no QSPICE marker)."""
        from pqwave.models.rawfile import RawFile

        raw_bytes = b"Title: ngspice\nPlotname: transient\nFlags: real\nBinary:\n"
        rf = RawFile.__new__(RawFile)
        rf.filename = "/tmp/test.raw"
        rf._step_count = 0

        result = rf._try_load_qux(
            [{"name": "time", "type": "time"}],
            False,
            raw_bytes,
        )
        assert result is None  # not a .qraw, no QSPICE marker

    def test_attempts_for_qspice_file(self):
        """Tries QUX for .qraw extension files."""
        from pqwave.models.rawfile import RawFile

        rf = RawFile.__new__(RawFile)
        rf.filename = "/tmp/test.qraw"
        rf._step_count = 0

        # Mock load_qraw_via_qux to succeed
        fake_data = np.array([[0.0, 1.0]], dtype=np.float32)
        fake_meta = {
            "plotname": "Transient Analysis",
            "flags": "real",
            "is_complex": False,
            "is_ac": False,
            "n_points": 1,
            "step_count": 1,
        }

        with mock.patch(
            "pqwave.bridge.qspice.qux_reader.load_qraw_via_qux",
            return_value=(fake_data, fake_meta),
        ):
            result = rf._try_load_qux(
                [{"name": "time", "type": "time"}, {"name": "V(out)", "type": "voltage"}],
                False,
                b"",
            )
            assert result is not None
            assert result["variables"][0]["name"] == "time"
            assert result["variables"][1]["type"] == "voltage"
            assert result["data"].shape == (1, 2)

    def test_qux_failure_returns_none(self):
        """Returns None when load_qraw_via_qux returns None."""
        from pqwave.models.rawfile import RawFile

        rf = RawFile.__new__(RawFile)
        rf.filename = "/tmp/test.qraw"
        rf._step_count = 0

        with mock.patch(
            "pqwave.bridge.qspice.qux_reader.load_qraw_via_qux",
            return_value=None,
        ):
            result = rf._try_load_qux(
                [{"name": "V(out)", "type": "voltage"}],
                False,
                b"",
            )
            assert result is None
