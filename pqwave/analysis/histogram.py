#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Histogram computation engine — pure numpy, no Qt dependencies.

Provides the compute_histogram function used by both the UI dialog and
the session API.
"""

from typing import Optional, Tuple

import numpy as np


def compute_histogram(
    data: np.ndarray,
    bins: Optional[int] = None,
    range: Optional[Tuple[float, float]] = None,
    norm: str = "count",
) -> dict:
    """Compute a histogram over *data* and return bins, edges, and centers.

    Args:
        data: 1-D array of values to histogram.
        bins: Number of bins (default: Sturges' rule).
        range: (lo, hi) bounds.  Defaults to (data.min(), data.max()).
        norm: Normalization mode.
            - ``"count"``     — raw counts
            - ``"density"``   — area integrates to 1
            - ``"probability"`` — sum of counts == 1

    Returns:
        dict with keys ``counts``, ``edges``, ``centers``, ``norm``.
    """
    if bins is None:
        n = len(data)
        bins = max(1, int(np.ceil(np.log2(n)) + 1))  # Sturges' rule

    rng = range if range is not None else (float(np.min(data)), float(np.max(data)))

    counts, edges = np.histogram(data, bins=bins, range=rng)

    if norm == "density":
        bin_widths = np.diff(edges)
        total = np.sum(counts)
        counts = counts.astype(np.float64) / (total * bin_widths) if total > 0 else counts.astype(np.float64)
    elif norm == "probability":
        total = np.sum(counts)
        counts = counts.astype(np.float64) / total if total > 0 else counts.astype(np.float64)

    centers = (edges[:-1] + edges[1:]) / 2.0

    return {"counts": counts, "edges": edges, "centers": centers, "norm": norm}
