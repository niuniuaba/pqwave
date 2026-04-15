#!/usr/bin/env python3
"""
Memory profiler for pqwave raw file loading.

Measures memory at each stage of the data pipeline:
  1. After spicelib RawRead parse
  2. After numpy column_stack
  3. After multiple get_variable_data calls (NO caching!)
  4. After complex derivation (mag/real/imag/ph each create new arrays)
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
    if os.path.basename(script_dir) == "tests":
        sys.path.insert(0, os.path.dirname(script_dir))
    else:
        sys.path.insert(0, script_dir)

from pqwave.models.rawfile import RawFile
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
    snapshot("before load")

    # ---- Stage 1: RawFile.parse() ----
    print(f"\n--- Stage 1: spicelib parse + numpy column_stack ---")
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

    print(f"  Dataset title: {ds.get('title', 'N/A')}")
    print(f"  Variables: {n_vars}")
    print(f"  Points per variable: {n_points:,}")
    print(f"  dtype: {data_matrix.dtype}")
    print(f"  column_stack matrix: {fmt_bytes(matrix_bytes)}")

    # ---- Stage 2: spicelib internal memory ----
    print(f"\n--- Stage 2: spicelib RawRead internal data ---")
    trace_names = rf.raw_data.get_trace_names()
    print(f"  Traces in spicelib: {len(trace_names)}")

    trace_sizes = []
    for name in trace_names:
        try:
            trace = rf.raw_data.get_trace(name)
            if trace is not None:
                if hasattr(trace, 'get_wave'):
                    arr = trace.get_wave()
                else:
                    arr = np.array(trace)
                trace_sizes.append((name, arr.nbytes))
        except Exception:
            pass

    trace_sizes.sort(key=lambda x: x[1], reverse=True)
    print(f"  Top 5 largest traces:")
    for name, size in trace_sizes[:5]:
        print(f"    {name}: {fmt_bytes(size)}")
    total_trace_mem = sum(s for _, s in trace_sizes)
    print(f"  All spicelib traces total: {fmt_bytes(total_trace_mem)}")

    _, rss2, _ = snapshot("after reading all spicelib traces")

    # ---- Stage 3: get_variable_data repeated calls (NO CACHING!) ----
    print(f"\n--- Stage 3: get_variable_data - NO CACHING impact ---")
    if ds['variables']:
        test_var = ds['variables'][0]['name']
        arrays = []
        for i in range(5):
            arr = rf.get_variable_data(test_var)
            if arr is not None:
                arrays.append(id(arr))

        unique_ids = len(set(arrays))
        print(f"  Called get_variable_data('{test_var}') 5 times")
        print(f"  Created {unique_ids} DISTINCT numpy array objects")
        if unique_ids > 1:
            print(f"  ** WASTE: {unique_ids} x {fmt_bytes(per_var_bytes)} = "
                  f"{fmt_bytes(unique_ids * per_var_bytes)} "
                  f"(should be 1 x {fmt_bytes(per_var_bytes)})")
        else:
            print(f"  (spicelib may be caching internally)")

        for var in ds['variables']:
            rf.get_variable_data(var['name'])

        _, rss3, _ = snapshot("after calling all variables once")

    # ---- Stage 4: Complex data derivation ----
    if ds.get('_is_ac_or_complex', False):
        print(f"\n--- Stage 4: Complex data derivation (AC mode) ---")

        for var in ds['variables'][:5]:
            vname = var['name']
            mag = rf._get_complex_magnitude(vname)
            real = rf._get_complex_real(vname)
            imag = rf._get_complex_imag(vname)
            ph = rf._get_complex_phase(vname)

            derived_size = sum(
                v.nbytes for v in [mag, real, imag, ph] if v is not None
            )
            print(f"  {vname}: mag+real+imag+ph = {fmt_bytes(derived_size)}")

        _, rss4, _ = snapshot("after complex derivation (first 5 vars)")

        estimated_all = n_vars * 4 * per_var_bytes
        extra_copies = n_vars * 4 * per_var_bytes
        print(f"\n  For all {n_vars} variables:")
        print(f"    Derived arrays: {fmt_bytes(estimated_all)}")
        print(f"    Extra get_variable_data copies: {fmt_bytes(extra_copies)}")
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
            print(f"  [{label}] '{expr}' -> {fmt_bytes(result.nbytes)}")
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
    print(f"")
    print(f"  Known memory consumers:")
    print(f"    column_stack matrix (1 copy):    {fmt_bytes(matrix_bytes):>12}")
    print(f"    spicelib internal (all traces):  {fmt_bytes(total_trace_mem):>12}")
    print(f"    spicelib + matrix subtotal:      {fmt_bytes(matrix_bytes + total_trace_mem):>12}")

    if ds.get('_is_ac_or_complex', False):
        complex_derived = n_vars * 4 * per_var_bytes
        complex_extra = n_vars * 4 * per_var_bytes
        print(f"    complex derived (mag/real/imag/ph): {fmt_bytes(complex_derived):>12}")
        print(f"    complex extra copies (4x get_var): {fmt_bytes(complex_extra):>12}")
        total_ac = matrix_bytes + total_trace_mem + complex_derived + complex_extra
        print(f"    AC mode subtotal:                {fmt_bytes(total_ac):>12}")

    print(f"\n  Per-call waste (get_variable_data, NO caching):")
    print(f"    Each call creates: {fmt_bytes(per_var_bytes)}")
    print(f"    Typical trace (5 expressions x 3 vars): ~{fmt_bytes(per_var_bytes * 15)}")

    print(f"\n  Final RSS: {fmt_bytes(final_rss)}")
    print(f"  Final tracemalloc: {fmt_bytes(final_tm)}")
    print(f"  RSS - tracemalloc = {fmt_bytes(final_rss - final_tm)} (C-extensions, Qt, Python runtime)")

    tracemalloc.stop()

    return {
        'file_size': file_size,
        'n_vars': n_vars,
        'n_points': n_points,
        'matrix_bytes': matrix_bytes,
        'total_trace_mem': total_trace_mem,
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
