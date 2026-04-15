#!/usr/bin/env python3
"""Lightweight memory profiler for large raw files.

Uses a staged approach with gc.collect() between stages to avoid OOM,
and tracks RSS at each step to identify where memory explodes.

Usage:
    venv/bin/python pqwave/tests/memory_profile_light.py tests/rc.raw
"""

import sys
import os
import gc
import resource
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pqwave.models.rawfile import _parse_header_variables, preprocess_raw_file

try:
    from spicelib import RawRead
except ImportError:
    print("spicelib not available")
    sys.exit(1)


def fmt_bytes(n: int) -> str:
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


def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def snap(label):
    gc.collect()
    rss_val = rss()
    if tracemalloc.is_tracing():
        tm = tracemalloc.get_traced_memory()
        print(f"  [{label}] RSS: {fmt_bytes(rss_val):>10}  tracemalloc: cur={fmt_bytes(tm[0]):>10} peak={fmt_bytes(tm[1]):>10}")
    else:
        print(f"  [{label}] RSS: {fmt_bytes(rss_val):>10}")
    return rss_val


def main(filepath):
    print(f"\n{'='*70}")
    print(f"Lightweight Memory Profile: {filepath}")
    print(f"{'='*70}")

    file_size = os.path.getsize(filepath)
    print(f"File size: {fmt_bytes(file_size)}")
    print()

    gc.collect()
    tracemalloc.start(10)

    rss_start = snap("initial")

    # Stage 1: preprocess_raw_file
    print(f"\n--- Stage 1: preprocess_raw_file ---")
    load_path = preprocess_raw_file(filepath)
    is_tmp = load_path != filepath
    print(f"  Result: {'temp file' if is_tmp else 'original file'}")
    snap("after preprocess")

    # Stage 2: RawRead header only
    print(f"\n--- Stage 2: RawRead() ---")
    raw_data = RawRead(load_path)
    trace_names = raw_data.get_trace_names()
    n_traces = len(trace_names)
    print(f"  Traces: {n_traces}")
    snap("after RawRead")

    # Stage 3: Load traces one by one, measure each
    print(f"\n--- Stage 3: Loading traces one by one ---")
    first5_rss = []
    plot = raw_data._plots[0]
    for i, name in enumerate(trace_names):
        trace = raw_data.get_trace(name)
        if trace is not None and hasattr(trace, 'get_wave'):
            arr = trace.get_wave()
            size = arr.nbytes
            if i < 5:
                r = snap(f"after trace {i} ({name})")
                first5_rss.append(r)
            if i >= n_traces - 3:
                snap(f"after trace {i} ({name})")
            del arr  # Free to avoid OOM
            if i == 5:
                print(f"  ... (skipping middle traces to avoid OOM) ...")

    # Stage 4: Load first few traces and column_stack
    print(f"\n--- Stage 4: column_stack first 10 traces ---")
    data_list = []
    for i, name in enumerate(trace_names[:10]):
        trace = raw_data.get_trace(name)
        if trace is not None and hasattr(trace, 'get_wave'):
            arr = trace.get_wave()
            data_list.append(arr)
    if data_list:
        import numpy as np
        stacked = np.column_stack(data_list)
        print(f"  10 traces stacked: {stacked.shape}, {fmt_bytes(stacked.nbytes)}")
        snap("after column_stack 10")
        del stacked
    del data_list

    # Estimate full memory
    print(f"\n{'='*70}")
    print("MEMORY ESTIMATION")
    print(f"{'='*70}")

    # Get one trace size as reference
    ref_trace = raw_data.get_trace(trace_names[0])
    ref_arr = ref_trace.get_wave()
    per_var = ref_arr.nbytes
    ref_dtype = ref_arr.dtype
    ref_len = len(ref_arr)
    del ref_arr

    matrix_bytes = per_var * n_traces
    print(f"  Points per trace: {ref_len:,}")
    print(f"  dtype: {ref_dtype}")
    print(f"  Per variable: {fmt_bytes(per_var)}")
    print(f"  All traces (spicelib internal): ~{fmt_bytes(per_var * n_traces)}")
    print(f"  Full column_stack matrix: ~{fmt_bytes(matrix_bytes)}")
    print(f"  Total (spicelib + matrix): ~{fmt_bytes(per_var * n_traces * 2)}")
    print(f"  Plus preprocess raw_bytes: ~{fmt_bytes(file_size)}")
    print(f"  Estimated peak: ~{fmt_bytes(per_var * n_traces * 2 + file_size)}")
    print()
    print(f"  Available RAM: ~10 GB")
    print(f"  Available + swap: ~14 GB")

    rss_end = snap("FINAL")
    rss_increase = rss_end - rss_start
    print(f"\n  RSS increase from start: {fmt_bytes(rss_increase)}")

    # Cleanup
    if is_tmp and os.path.exists(load_path):
        os.unlink(load_path)

    tracemalloc.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python memory_profile_light.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
