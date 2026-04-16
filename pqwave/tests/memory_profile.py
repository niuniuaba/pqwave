#!/usr/bin/env python3
"""
Memory profiler for pqwave raw file loading.

Measures memory at each stage of the optimized data pipeline:
  1. After RawFile.parse() (spicelib released, float32/complex64)
  2. After Dataset instantiation (memmap column views)
  3. get_variable_data cache behavior (should be zero-copy views)
  4. Complex data derivation (mag/real/imag/ph)
  5. After ExprEvaluator expression evaluation

Also tracks OS-level RSS to capture C-extension memory not visible to tracemalloc.

Usage:
    python pqwave/tests/memory_profile.py <raw_file>

    e.g.  python pqwave/tests/memory_profile.py pqwave/tests/bridge.raw
          python pqwave/tests/memory_profile.py tests/SMPS.qraw
"""

import sys
import os
import gc
import resource
import tracemalloc
import numpy as np

# Allow running as script or as module
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile
from pqwave.models.dataset import Dataset
from pqwave.models.expression import ExprEvaluator


def fmt_bytes(n: int) -> str:
    """Format bytes as human-readable string."""
    if n < 0:
        return f"-{fmt_bytes(-n)}"
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024**2:.1f} MB"
    else:
        return f"{n / 1024**3:.2f} GB"


def get_rss() -> int:
    """Get current process RSS in bytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def snapshot(label: str):
    """Print current tracemalloc + RSS snapshot stats."""
    gc.collect()
    tm_snap = tracemalloc.take_snapshot()
    tm_total = sum(s.size for s in tm_snap.statistics('filename'))
    rss = get_rss()
    print(f"  [{label}] tracemalloc: {fmt_bytes(tm_total):>10}   RSS: {fmt_bytes(rss):>10}")
    return tm_total, rss, tm_snap


def profile_rawfile(filepath: str):
    print(f"\n{'='*70}")
    print(f"Memory Profile: {filepath}")
    print(f"{'='*70}")

    file_size = os.path.getsize(filepath)
    print(f"File size on disk: {fmt_bytes(file_size)}")

    gc.collect()
    tracemalloc.start(25)
    _, rss_before, _ = snapshot("before load")

    # ---- Stage 1: RawFile.parse() ----
    print(f"\n--- Stage 1: RawFile.parse() ---")
    rf = RawFile(filepath)
    _, rss1, snap1 = snapshot("after RawFile.parse()")

    if not rf.datasets:
        print("  No datasets found!")
        tracemalloc.stop()
        return

    ds = rf.datasets[0]
    data_matrix = ds['data']
    n_vars = data_matrix.shape[1] if data_matrix.ndim > 1 else 0
    n_points = data_matrix.shape[0] if data_matrix.ndim > 1 else 0
    matrix_bytes = data_matrix.nbytes if data_matrix.size > 0 else 0
    per_var_bytes = matrix_bytes // n_vars if n_vars > 0 else 0

    is_mmap = isinstance(data_matrix, np.memmap)
    print(f"  Dataset title: {ds.get('title', 'N/A')}")
    print(f"  Variables: {n_vars}")
    print(f"  Points per variable: {n_points:,}")
    print(f"  dtype: {data_matrix.dtype}")
    print(f"  Storage: {'memmap' if is_mmap else 'column_stack'}")
    print(f"  Matrix size: {fmt_bytes(matrix_bytes)}")
    if is_mmap:
        mmap_size = os.path.getsize(data_matrix.filename)
        print(f"  Memmap file size: {fmt_bytes(mmap_size)}")
    print(f"  raw_data is None: {rf.raw_data is None}")

    # ---- Stage 2: Dataset instantiation ----
    print(f"\n--- Stage 2: Dataset() ---")
    dataset = Dataset(rf, dataset_idx=0)
    _, rss2, _ = snapshot("after Dataset")
    print(f"  Dataset variables: {dataset.n_variables}")
    print(f"  Dataset points: {dataset.n_points}")

    # Check Variable data shares base with matrix
    if n_vars > 0:
        v = dataset.variables[0]
        shares_base = v.data.base is data_matrix or (v.data.base is not None and getattr(v.data.base, 'base', None) is data_matrix)
        print(f"  Variable[0] shares matrix base: {shares_base}")

    # ---- Stage 3: get_variable_data cache behavior ----
    print(f"\n--- Stage 3: get_variable_data cache ---")
    if ds['variables']:
        test_var = ds['variables'][0]['name']
        arrays = []
        for i in range(5):
            arr = rf.get_variable_data(test_var, 0)
            if arr is not None:
                arrays.append(id(arr))

        unique_ids = len(set(arrays))
        print(f"  Called get_variable_data('{test_var}') 5 times")
        print(f"  Unique array objects: {unique_ids}")
        if unique_ids == 1:
            print(f"  Cache working: same view returned every time")
        else:
            print(f"  ** WASTE: {unique_ids} DISTINCT arrays of {fmt_bytes(per_var_bytes)}")

        # Verify variable data shares matrix
        for var in ds['variables']:
            rf.get_variable_data(var['name'], 0)

        _, rss3, _ = snapshot("after all variables accessed once")

    # ---- Stage 4: Complex data derivation ----
    if ds.get('_is_ac_or_complex', False):
        print(f"\n--- Stage 4: Complex data derivation (AC mode) ---")

        for var in ds['variables'][:5]:
            vname = var['name']
            mag = rf._get_complex_magnitude(vname, 0)
            real = rf._get_complex_real(vname, 0)
            imag = rf._get_complex_imag(vname, 0)
            ph = rf._get_complex_phase(vname, 0)

            derived_size = sum(
                v.nbytes for v in [mag, real, imag, ph] if v is not None
            )
            dtypes = f"mag={mag.dtype}" if mag is not None else ""
            print(f"  {vname}: derived total = {fmt_bytes(derived_size)}  ({dtypes})")

        _, rss4, _ = snapshot("after complex derivation (first 5 vars)")

        estimated_all = n_vars * 4 * per_var_bytes
        print(f"\n  For all {n_vars} variables:")
        print(f"    Derived arrays total (mag/real/imag/ph): {fmt_bytes(estimated_all)}")
    else:
        print(f"\n--- Stage 4: N/A (not AC/complex) ---")

    # ---- Stage 5: ExprEvaluator ----
    print(f"\n--- Stage 5: ExprEvaluator ---")
    evaluator = ExprEvaluator(rf, 0)

    test_exprs = []
    if n_vars >= 2:
        v0 = ds['variables'][0]['name']
        v1 = ds['variables'][min(1, n_vars - 1)]['name']
        test_exprs = [
            ("simple variable", v0),
            ("multiply", f"{v0} * {v1}"),
            ("add", f"{v0} + {v1}"),
        ]
    elif n_vars == 1:
        v0 = ds['variables'][0]['name']
        test_exprs = [
            ("simple", v0),
            ("multiply by 2", f"{v0} * 2"),
        ]

    for label, expr in test_exprs:
        try:
            result = evaluator.evaluate(expr)
            print(f"  [{label}] '{expr}' -> {fmt_bytes(result.nbytes)}, dtype={result.dtype}")
        except Exception as e:
            print(f"  [{label}] '{expr}' -> ERROR: {e}")

    _, rss5, _ = snapshot("after ExprEvaluator")

    # ---- Summary ----
    final_tm, final_rss, _ = snapshot("FINAL")

    print(f"\n{'='*70}")
    print("MEMORY BREAKDOWN SUMMARY")
    print(f"{'='*70}")
    print(f"  Data: {n_points:,} points x {n_vars} variables, dtype={data_matrix.dtype}")
    print(f"  File size: {fmt_bytes(file_size)}")
    print(f"  RSS / file ratio: {final_rss / file_size:.2f}x")
    print(f"  RSS increase from start: {fmt_bytes(final_rss - rss_before)}")
    print(f"")
    print(f"  Known memory consumers:")
    print(f"    column_stack / memmap matrix:      {fmt_bytes(matrix_bytes):>12}")
    per_var_approx = matrix_bytes / n_vars if n_vars > 0 else 0
    print(f"    Per variable (avg):                {fmt_bytes(int(per_var_approx)):>12}")

    if ds.get('_is_ac_or_complex', False):
        complex_derived = n_vars * 4 * per_var_bytes
        print(f"    Derived (mag/real/imag/ph) all vars: {fmt_bytes(complex_derived):>12}")

    print(f"\n  Final RSS: {fmt_bytes(final_rss)}")
    print(f"  Final tracemalloc: {fmt_bytes(final_tm)}")
    print(f"  RSS - tracemalloc = {fmt_bytes(final_rss - final_tm)} (C-extensions, Qt, Python runtime)")

    tracemalloc.stop()

    return {
        'file_size': file_size,
        'n_vars': n_vars,
        'n_points': n_points,
        'matrix_bytes': matrix_bytes,
        'rss_after_parse': rss1,
        'rss_final': final_rss,
        'tm_final': final_tm,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python memory_profile.py <raw_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    profile_rawfile(filepath)
