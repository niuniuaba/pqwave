"""Multi-run statistical analysis for Monte Carlo data."""
import numpy as np
from scipy.stats import spearmanr


def compute_cross_run_stats(data: np.ndarray, run_mask: np.ndarray | None = None) -> dict:
    """Compute per-timepoint statistics across runs.

    Args:
        data: 2D array (n_runs, n_points) with one row per run.
        run_mask: Boolean array length n_runs. Only True runs are used.
            If None, all runs are used.

    Returns:
        dict with 'mean', 'std', 'min', 'max' — each a 1D array of length n_points.
    """
    if run_mask is not None:
        data = data[run_mask]
    if data.shape[0] == 0:
        n = data.shape[1] if data.ndim == 2 else 0
        return {"mean": np.zeros(n), "std": np.zeros(n), "min": np.zeros(n), "max": np.zeros(n)}
    return {
        "mean": np.mean(data, axis=0),
        "std": np.std(data, axis=0, ddof=1 if data.shape[0] > 1 else 0),
        "min": np.min(data, axis=0),
        "max": np.max(data, axis=0),
    }


def compute_run_measurements(data: np.ndarray, measure: str) -> np.ndarray:
    """Evaluate a scalar measurement on each run.

    Args:
        data: 2D array (n_runs, n_points).
        measure: One of 'max', 'min', 'mean', 'rms', 'pk_pk'.

    Returns:
        1D array of length n_runs with one scalar per run.
    """
    if measure == "max":
        return np.max(data, axis=1)
    elif measure == "min":
        return np.min(data, axis=1)
    elif measure == "mean":
        return np.mean(data, axis=1)
    elif measure == "rms":
        return np.sqrt(np.mean(data ** 2, axis=1))
    elif measure == "pk_pk":
        return np.max(data, axis=1) - np.min(data, axis=1)
    else:
        raise ValueError(f"Unknown measure: {measure}. Use max, min, mean, rms, or pk_pk.")


def compute_yield(data: np.ndarray, low: float, high: float,
                  measure: str | None = None) -> np.ndarray | float:
    """Compute yield — percentage of runs within [low, high].

    Args:
        data: 2D array (n_runs, n_points).
        low: Lower spec limit.
        high: Upper spec limit.
        measure: If given, compute the measurement per run first,
            then check if each scalar is within limits. Returns a single float.

    Returns:
        Per-point yield percentage array, or a single float if measure is given.
    """
    if measure is not None:
        scalars = compute_run_measurements(data, measure)
        within = (scalars >= low) & (scalars <= high)
        return float(np.mean(within) * 100.0)
    within = (data >= low) & (data <= high)
    return np.mean(within, axis=0) * 100.0


def compute_worst_cases(data: np.ndarray, nominal_index: int = 0, n: int = 5,
                         metric: str = "max_abs_diff") -> list[dict]:
    """Find the N runs with largest deviation from nominal.

    Args:
        data: 2D array (n_runs, n_points).
        nominal_index: Index of the nominal run.
        n: Number of worst cases to return.
        metric: 'max_abs_diff' or 'rms_diff'.

    Returns:
        List of dicts with 'run_index' and 'deviation', sorted largest first.
    """
    nominal = data[nominal_index]
    deviations = []
    for i in range(data.shape[0]):
        if i == nominal_index:
            continue
        diff = data[i] - nominal
        if metric == "max_abs_diff":
            dev = float(np.max(np.abs(diff)))
        elif metric == "rms_diff":
            dev = float(np.sqrt(np.mean(diff ** 2)))
        else:
            raise ValueError(f"Unknown metric: {metric}")
        deviations.append({"run_index": i, "deviation": dev})
    deviations.sort(key=lambda x: x["deviation"], reverse=True)
    return deviations[:n]


def compute_sensitivity(measurements: np.ndarray,
                         params: dict[str, np.ndarray]) -> list[dict]:
    """Rank parameters by their Spearman correlation with a measurement.

    Args:
        measurements: 1D array of scalar measurement per run.
        params: Dict of param_name -> 1D array of param values per run.

    Returns:
        List of dicts with 'param' and 'r', sorted by |r| descending.
    """
    results = []
    for name, values in params.items():
        if len(values) != len(measurements):
            continue
        if np.std(values) == 0 or np.std(measurements) == 0:
            results.append({"param": name, "r": 0.0, "p": 1.0})
            continue
        r, p = spearmanr(values, measurements)
        results.append({"param": name, "r": float(r), "p": float(p)})
    results.sort(key=lambda x: abs(x["r"]), reverse=True)
    return results
