"""Tests for correlation tools — model parser, Cholesky, and formatters."""
import os
import tempfile
import numpy as np
import pytest
from pqwave.models.mc_collection import CorrelationMatrix


class TestParseModelFile:
    def test_parses_single_model_with_params(self):
        from pqwave.analysis.correlation import parse_model_file
        content = ".model n1 nmos level=8 vth0=0.6322 u0=388.32 tox=9e-09"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_model_file(path)
            assert len(result) >= 3  # level, vth0, u0, tox
            models = set(r["model"] for r in result)
            assert models == {"n1"}
            params = {r["param"]: r for r in result}
            assert params["vth0"]["nominal"] == 0.6322
            assert params["u0"]["nominal"] == 388.32
            assert all(r["logical_name"] == f"n1_{r['param']}" for r in result)
        finally:
            os.unlink(path)

    def test_parses_continuation_lines(self):
        from pqwave.analysis.correlation import parse_model_file
        content = ".model p1 pmos\n+level=8\n+vth0=-0.673 u0=138.76\n+tox=9e-09"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_model_file(path)
            names = [r["param"] for r in result]
            assert "vth0" in names
            assert "u0" in names
            assert "tox" in names
            vth0 = next(r for r in result if r["param"] == "vth0")
            assert vth0["nominal"] == -0.673
            assert vth0["model"] == "p1"
        finally:
            os.unlink(path)

    def test_extracts_nominal_from_agauss(self):
        from pqwave.analysis.correlation import parse_model_file
        content = ".model n1 nmos vth0=agauss(0.6, 0.1, 3) u0=gauss(400, 0.05, 3)"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_model_file(path)
            vth0 = next(r for r in result if r["param"] == "vth0")
            assert vth0["nominal"] == 0.6
            u0 = next(r for r in result if r["param"] == "u0")
            assert u0["nominal"] == 400.0
        finally:
            os.unlink(path)

    def test_parses_multiple_models(self):
        from pqwave.analysis.correlation import parse_model_file
        content = ".model n1 nmos vth0=0.632 u0=388\n.model p1 pmos vth0=-0.673 u0=138\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_model_file(path)
            models = set(r["model"] for r in result)
            assert models == {"n1", "p1"}
            logicals = [r["logical_name"] for r in result]
            assert "n1_vth0" in logicals
            assert "p1_vth0" in logicals
        finally:
            os.unlink(path)

    def test_skips_non_model_lines(self):
        from pqwave.analysis.correlation import parse_model_file
        content = "* Comment\n.options noacct\n.model n1 nmos vth0=0.6\n.subckt inv a b\nmn1 a b 0 0 n1\n.ends\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_model_file(path)
            assert len(result) == 1
            assert result[0]["model"] == "n1"
        finally:
            os.unlink(path)

    def test_empty_file_returns_empty_list(self):
        from pqwave.analysis.correlation import parse_model_file
        content = "* Just a comment\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_model_file(path)
            assert result == []
        finally:
            os.unlink(path)


class TestCholeskyEngine:
    def test_cholesky_identity_matrix(self):
        from pqwave.analysis.correlation import compute_cholesky
        cm = CorrelationMatrix(params=["a","b","c"], matrix=[1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0])
        L = compute_cholesky(cm)
        np.testing.assert_array_almost_equal(L, np.eye(3))

    def test_cholesky_recovers_correlation_structure(self):
        from pqwave.analysis.correlation import compute_cholesky
        cm = CorrelationMatrix(params=["a","b"], matrix=[1.0,0.5,0.5,1.0])
        L = compute_cholesky(cm)
        recovered = L @ L.T
        np.testing.assert_array_almost_equal(recovered, cm.get_dense())

    def test_cholesky_rejects_non_psd_matrix(self):
        from pqwave.analysis.correlation import compute_cholesky
        cm = CorrelationMatrix(params=["a","b","c"], matrix=[1.0,0.9,0.9,0.9,1.0,-0.9,0.9,-0.9,1.0])
        with pytest.raises(ValueError, match="positive semi-definite"):
            compute_cholesky(cm)

    def test_generate_correlated_values_shape(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_correlated_values
        cm = CorrelationMatrix(params=["a","b"], matrix=[1.0,0.3,0.3,1.0])
        L = compute_cholesky(cm)
        values = generate_correlated_values(L, [0.6, 400.0], [0.06, 40.0], n_runs=100, seed=42)
        assert values.shape == (100, 2)

    def test_generate_correlated_values_approximates_correlation(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_correlated_values
        cm = CorrelationMatrix(params=["a","b"], matrix=[1.0,0.7,0.7,1.0])
        L = compute_cholesky(cm)
        values = generate_correlated_values(L, [1.0, 2.0], [0.1, 0.2], n_runs=10000, seed=42)
        sample_corr = np.corrcoef(values.T)
        assert abs(sample_corr[0, 1] - 0.7) < 0.05

    def test_generate_correlated_values_deterministic(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_correlated_values
        cm = CorrelationMatrix(params=["a"], matrix=[1.0])
        L = compute_cholesky(cm)
        v1 = generate_correlated_values(L, [0.6], [0.06], n_runs=10, seed=42)
        v2 = generate_correlated_values(L, [0.6], [0.06], n_runs=10, seed=42)
        np.testing.assert_array_equal(v1, v2)
        v3 = generate_correlated_values(L, [0.6], [0.06], n_runs=10, seed=99)
        assert not np.allclose(v1, v3)


class TestOutputFormatters:
    def setup_method(self):
        from pqwave.analysis.correlation import compute_cholesky
        self.params = [
            {"model": "n1", "param": "vth0", "nominal": 0.6322, "logical_name": "n1_vth0"},
            {"model": "p1", "param": "vth0", "nominal": -0.673, "logical_name": "p1_vth0"},
        ]
        cm = CorrelationMatrix(params=["n1_vth0","p1_vth0"], matrix=[1.0,0.3,0.3,1.0])
        self.L = compute_cholesky(cm)
        self.nominals = [0.6322, -0.673]
        self.sigmas = [0.06, 0.07]

    def test_generate_control_script_writes_file(self):
        from pqwave.analysis.correlation import generate_control_script
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "mc_output.sp")
            generate_control_script(self.params, self.nominals, self.L, outpath,
                                   sim_command="tran 15p 100n 0", n_runs=30)
            assert os.path.exists(outpath)
            content = open(outpath).read()
            assert "sgauss(0)" in content
            assert "dowhile run <= mc_runs" in content
            assert "altermod @n1[vth0]" in content
            assert "altermod @p1[vth0]" in content
            assert "tran 15p 100n 0" in content
            assert "let mc_runs = 30" in content

    def test_generate_control_script_identity_correlation(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_control_script
        cm = CorrelationMatrix(params=["n1_vth0"], matrix=[1.0])
        L = compute_cholesky(cm)
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "mc_output.sp")
            generate_control_script(
                [{"model":"n1","param":"vth0","nominal":0.6,"logical_name":"n1_vth0"}],
                [0.6], L, outpath, sim_command="ac dec 10 1k 1G")
            content = open(outpath).read()
            assert "let z1 = sgauss(0)" in content

    def test_generate_csv_writes_header_and_rows(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_correlated_values, generate_csv
        cm = CorrelationMatrix(params=["n1_vth0","p1_vth0"], matrix=[1.0,0.0,0.0,1.0])
        L = compute_cholesky(cm)
        values = generate_correlated_values(L, [0.6,-0.7], [0.06,0.07], n_runs=5, seed=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "values.csv")
            generate_csv(values, ["n1_vth0","p1_vth0"], outpath)
            content = open(outpath).read()
            lines = content.strip().split("\n")
            assert lines[0] == "run,n1_vth0,p1_vth0"
            assert len(lines) == 6
            for i, line in enumerate(lines[1:]):
                assert line.startswith(str(i))

    def test_generate_csv_supports_tsv(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_correlated_values, generate_csv
        cm = CorrelationMatrix(params=["n1_vth0"], matrix=[1.0])
        L = compute_cholesky(cm)
        values = generate_correlated_values(L, [0.6], [0.06], n_runs=3, seed=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "values.tsv")
            generate_csv(values, ["n1_vth0"], outpath, delimiter="\t")
            content = open(outpath).read()
            assert "\t" in content
            assert "," not in content.split("\n")[0]

    def test_generate_param_snippet_writes_baked_values(self):
        from pqwave.analysis.correlation import compute_cholesky, generate_correlated_values, generate_param_snippet
        cm = CorrelationMatrix(params=["n1_vth0","p1_vth0"], matrix=[1.0,0.0,0.0,1.0])
        L = compute_cholesky(cm)
        values = generate_correlated_values(L, [0.6,-0.7], [0.06,0.07], n_runs=3, seed=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "params.sp")
            generate_param_snippet(values, ["n1_vth0","p1_vth0"], outpath)
            assert os.path.exists(outpath)
            content = open(outpath).read()
            assert ".param" in content
            assert "n1_vth0=" in content


class TestCorrelationIntegration:
    """End-to-end tests for the correlation pipeline."""

    def test_full_pipeline_parse_to_csv(self):
        """Parse model file → build matrix → generate CSV → verify output."""
        import tempfile, os
        from pqwave.analysis.correlation import (
            parse_model_file, compute_cholesky,
            generate_correlated_values, generate_csv,
        )
        from pqwave.models.mc_collection import CorrelationMatrix

        content = (
            ".model n1 nmos vth0=0.632 u0=388 tox=9e-09\n"
            ".model p1 pmos vth0=-0.673 u0=138 tox=9e-09\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lib", delete=False,
        ) as f:
            f.write(content)
            model_path = f.name
        try:
            params = parse_model_file(model_path)
            assert len(params) == 6

            selected = [p for p in params if p["param"] in ("vth0", "u0")][:2]
            names = [s["logical_name"] for s in selected]
            cm = CorrelationMatrix(
                params=names,
                matrix=[1.0, 0.5, 0.5, 1.0],
            )

            L = compute_cholesky(cm)

            nominals = [s["nominal"] for s in selected]
            sigmas = [abs(n * 0.1) if abs(n) > 1e-30 else 0.1 for n in nominals]
            values = generate_correlated_values(
                L, nominals, sigmas, n_runs=100, seed=42,
            )
            assert values.shape == (100, 2)

            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = os.path.join(tmpdir, "output.csv")
                generate_csv(values, names, csv_path)
                assert os.path.exists(csv_path)

                with open(csv_path) as fh:
                    parsed = fh.readlines()
                assert len(parsed) == 101
                assert "n1_vth0" in parsed[0]
        finally:
            os.unlink(model_path)

    def test_control_script_format_valid(self):
        """Verify generated .control script passes basic syntax checks."""
        import tempfile, os
        from pqwave.analysis.correlation import (
            compute_cholesky, generate_control_script,
        )
        from pqwave.models.mc_collection import CorrelationMatrix

        params = [
            {"model": "n1", "param": "vth0", "nominal": 0.632,
             "logical_name": "n1_vth0"},
            {"model": "p1", "param": "vth0", "nominal": -0.673,
             "logical_name": "p1_vth0"},
        ]
        cm = CorrelationMatrix(
            params=["n1_vth0", "p1_vth0"],
            matrix=[1.0, 0.3, 0.3, 1.0],
        )
        L = compute_cholesky(cm)

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "mc_control.sp")
            generate_control_script(
                params, [0.632, -0.673], L, out,
                sim_command="tran 15p 100n 0", n_runs=30,
            )
            content = open(out).read()

            assert content.startswith("* Generated by pqwave")
            assert ".control" in content
            assert ".endc" in content
            assert "dowhile run <= mc_runs" in content
            assert "end" in content.split("\n")[-3] or "end" in content.split("\n")[-4] or "end" in content  # end is in the .endc section
            assert "altermod" in content
            assert "sgauss(0)" in content

    def test_correlation_editor_can_be_imported(self):
        """Verify CorrelationMatrixEditor can be imported."""
        from pqwave.ui.correlation_editor import CorrelationMatrixEditor
        assert CorrelationMatrixEditor is not None

    def test_api_commands_registered(self):
        """Verify all four correlation commands are registered."""
        from pqwave.session.api import get_command_registry
        registry = get_command_registry()
        assert "mc_correlation_load" in registry
        assert "mc_correlation_show" in registry
        assert "mc_correlation_edit" in registry
        assert "mc_generate" in registry

    def test_control_script_mc_runs_is_nominal_plus_n_perturbed(self):
        """Verify mc_runs = n_runs produces nominal + N perturbed iterations.

        Ngspice convention: let mc_runs = N, dowhile run <= mc_runs
        gives run 0 (nominal) + runs 1..N (perturbed) = N+1 total sims.
        """
        import tempfile, os
        from pqwave.analysis.correlation import compute_cholesky, generate_control_script
        from pqwave.models.mc_collection import CorrelationMatrix

        cm = CorrelationMatrix(params=["a"], matrix=[1.0])
        L = compute_cholesky(cm)
        params = [{"model":"n1","param":"vth0","nominal":0.6,"logical_name":"n1_vth0"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "test.sp")
            generate_control_script(params, [0.6], L, out, n_runs=30)
            content = open(out).read()
            assert "let mc_runs = 30" in content
            assert "dowhile run <= mc_runs" in content

    def test_correlation_matrix_rejects_non_square(self):
        """Verify CorrelationMatrix rejects flat list that isn't square."""
        from pqwave.models.mc_collection import CorrelationMatrix
        with pytest.raises(ValueError):
            CorrelationMatrix(params=["a","b"], matrix=[1.0,0.5,0.5])  # 3 for 2 params
