"""Monte Carlo correlation analysis — model parsing, Cholesky, and output formatters.

Pure NumPy module, no Qt dependencies. Callable from both UI and CLI.
"""
from __future__ import annotations

import re
import warnings
import numpy as np

from pqwave.models.mc_collection import CorrelationMatrix

# ---------------------------------------------------------------------------
# Part A: parse model file
# ---------------------------------------------------------------------------


def parse_model_file(path: str) -> list[dict]:
    """Parse SPICE .model statements to extract parameters and nominal values."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    # Normalize continuation lines: join lines ending with '\n+' to previous line
    text = re.sub(r"\n\+\s*", " ", text)

    results: list[dict] = []
    # Match .model <name> <type> followed by parameter pairs
    model_pattern = re.compile(
        r"^\.model\s+(\S+)\s+\S+\s+(.*?)(?=^\.model|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    # Extract individual param=value tokens
    param_pattern = re.compile(
        r"(\w+)\s*=\s*("
        r"(?:agauss|gauss|aunif|unif)\s*\([^)]*\)"  # function call
        r"|"
        r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"  # number
        r")",
    )

    for model_match in model_pattern.finditer(text):
        model_name = model_match.group(1)
        params_str = model_match.group(2)

        for param_match in param_pattern.finditer(params_str):
            param_name = param_match.group(1)
            value_str = param_match.group(2)

            nominal = _extract_nominal(value_str)
            if nominal is None:
                warnings.warn(
                    f"Skipping param '{param_name}' in model '{model_name}': "
                    f"could not parse value '{value_str}'"
                )
                continue

            results.append({
                "model": model_name,
                "param": param_name,
                "nominal": nominal,
                "logical_name": f"{model_name}_{param_name}",
            })

    return results


def _extract_nominal(value_str: str) -> float | None:
    """Extract the nominal value from a parameter value string."""
    func_match = re.match(
        r"(?:agauss|gauss|aunif|unif)\s*\(\s*"
        r"(-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)",
        value_str,
    )
    if func_match:
        return float(func_match.group(1))
    try:
        return float(value_str)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Part B: Cholesky engine
# ---------------------------------------------------------------------------


def compute_cholesky(correlation_matrix: CorrelationMatrix) -> np.ndarray:
    """Compute Cholesky decomposition L of correlation matrix R. R = L @ L.T."""
    dense = correlation_matrix.get_dense()
    try:
        L = np.linalg.cholesky(dense)
    except np.linalg.LinAlgError:
        raise ValueError(
            "Correlation matrix is not positive semi-definite. "
            "Check for inconsistent correlation values."
        ) from None
    return L


def generate_correlated_values(
    L: np.ndarray,
    nominals: list[float],
    sigmas: list[float],
    n_runs: int,
    seed: int | None = None,
) -> np.ndarray:
    """Generate (n_runs, n_params) array of correlated physical parameter values."""
    n_params = L.shape[0]
    if len(nominals) != n_params or len(sigmas) != n_params:
        raise ValueError(
            f"nominals ({len(nominals)}) and sigmas ({len(sigmas)}) "
            f"must match L dimension ({n_params})"
        )

    rng = np.random.default_rng(seed)
    Z = rng.normal(0.0, 1.0, (n_runs, n_params))
    Zc = Z @ L.T
    nominals_arr = np.array(nominals, dtype=np.float64)
    sigmas_arr = np.array(sigmas, dtype=np.float64)
    return Zc * sigmas_arr + nominals_arr


# ---------------------------------------------------------------------------
# Part C: Output formatters
# ---------------------------------------------------------------------------


def _build_cholesky_let_expressions(L: np.ndarray, param_names: list[str]) -> list[str]:
    """Build ngspice let expressions for Cholesky-correlated normals."""
    n = L.shape[0]
    lines = []
    for i in range(n):
        terms = []
        for j in range(i + 1):
            coeff = L[i, j]
            if coeff == 0.0:
                continue
            if abs(coeff - 1.0) < 1e-12:
                terms.append(f"z{j + 1}")
            elif abs(coeff + 1.0) < 1e-12:
                terms.append(f"(-z{j + 1})")
            else:
                terms.append(f"({coeff:.6g} * z{j + 1})")
        if not terms:
            terms.append("0.0")
        expr = " + ".join(terms)
        lines.append(f"  let zc{i + 1} = {expr}  $ correlated {param_names[i]}")
    return lines


def generate_control_script(
    params: list[dict],
    nominals: list[float],
    L: np.ndarray,
    output_path: str,
    sim_command: str = "tran 1n 100n 0",
    n_runs: int = 100,
    seed: int | None = None,
) -> str:
    """Generate ngspice .control script with correlated parameter variation."""
    n_params = len(params)
    if n_params != L.shape[0]:
        raise ValueError(
            f"params count ({n_params}) must match L dimension ({L.shape[0]})"
        )
    param_names = [p["logical_name"] for p in params]

    lines: list[str] = []
    lines.append("* Generated by pqwave — correlated MC control script")
    lines.append(f"* Parameters: {', '.join(param_names)}")
    lines.append(f"* Runs: {n_runs}")
    lines.append("")
    lines.append(".control")
    lines.append(f"  let mc_runs = {n_runs}")
    lines.append("  let run = 0")
    if seed is not None:
        lines.append(f"  setseed {seed}")
    lines.append("  set curplot = new")
    lines.append("  set scratch = $curplot")
    lines.append("")
    lines.append("  * Distribution wrapper: agauss(nom, avar, sigma)")
    lines.append("  define agauss(nom, avar, sig) (nom + avar/sig * sgauss(0))")
    lines.append("")
    lines.append("  * Capture nominal values from model parameter set")
    for p in params:
        model = p["model"]
        param = p["param"]
        logical = p["logical_name"]
        lines.append(f"  let {logical}_nom = @{model}[{param}]")
    lines.append("")
    lines.append("  * MC simulation loop")
    lines.append("  dowhile run <= mc_runs")
    lines.append("    if run > 0")
    lines.append("      * Independent standard normal draws")
    for i in range(n_params):
        lines.append(f"      let z{i + 1} = sgauss(0)")
    lines.append("")
    lines.append("      * Correlated normals via Cholesky decomposition")
    cholesky_lines = _build_cholesky_let_expressions(L, param_names)
    for cl in cholesky_lines:
        lines.append(f"    {cl}")
    lines.append("")
    for i, p in enumerate(params):
        model = p["model"]
        param = p["param"]
        logical = p["logical_name"]
        sigma_val = abs(nominals[i]) * 0.1 if nominals[i] != 0 else 0.1
        lines.append(
            f"      altermod @{model}[{param}] = "
            f"{logical}_nom + {sigma_val:.6g} * zc{i + 1}"
        )
    lines.append("    end")
    lines.append(f"    {sim_command}")
    lines.append("")
    lines.append('    set run="$&run"')
    lines.append("    set dt = $curplot")
    lines.append("    setplot $scratch")
    lines.append("    let vout{$run}={$dt}.v(out)")
    lines.append("    setplot $dt")
    lines.append("    let run = run + 1")
    lines.append("    reset")
    lines.append("  end")
    lines.append("")
    lines.append("  * Save all results")
    lines.append("  write $rawfile {$scratch}.all")
    lines.append("  rusage")
    lines.append("  quit")
    lines.append(".endc")

    content = "\n".join(lines) + "\n"
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return output_path


def generate_csv(
    values: np.ndarray,
    param_names: list[str],
    output_path: str,
    delimiter: str = ",",
) -> str:
    """Write correlated parameter values as CSV (or TSV) file."""
    n_runs = values.shape[0]
    header = delimiter.join(["run"] + param_names)
    rows = [header]
    for run_idx in range(n_runs):
        row = [str(run_idx)]
        row.extend(f"{v:.8g}" for v in values[run_idx])
        rows.append(delimiter.join(row))

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    return output_path


def generate_param_snippet(
    values: np.ndarray,
    param_names: list[str],
    output_path: str,
) -> str:
    """Write per-run .param lines with baked correlated values."""
    n_runs, n_params = values.shape
    lines: list[str] = []
    lines.append("* Generated by pqwave — correlated .param values")
    lines.append(f"* {n_runs} runs, {n_params} parameters: {', '.join(param_names)}")

    for run_idx in range(n_runs):
        lines.append(f"* --- Run {run_idx} ---")
        param_pairs = []
        for p_idx, name in enumerate(param_names):
            param_pairs.append(f"{name}={values[run_idx, p_idx]:.8g}")
        lines.append(".param " + " ".join(param_pairs))
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return output_path
