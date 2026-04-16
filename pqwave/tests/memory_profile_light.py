#!/usr/bin/env python3
"""Lightweight memory profiler for pqwave raw file loading.

Uses gc.collect() between stages and tracks RSS at each step.
No tracemalloc overhead — suitable for very large files (>500 MB).

Usage:
    python pqwave/tests/memory_profile_light.py <raw_file>

    e.g.  python pqwave/tests/memory_profile_light.py tests/bridge.raw
          python pqwave/tests/memory_profile_light.py tests/rc_ltspice.raw
"""

import sys
import os
import gc
import resource

# Allow running as script or as module
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile
from pqwave.models.dataset import Dataset


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
    rss_start = rss()
    print(f"  [initial] RSS: {fmt_bytes(rss_start):>10}")

    # Stage 1: RawFile parse
    print(f"\n--- Stage 1: RawFile().parse() ---")
    rf = RawFile(filepath)
    snap("after parse")

    # Report internal state
    ds = rf.datasets[0] if rf.datasets else None
    if ds is None:
        print("  No datasets found!")
        return

    data_matrix = ds.get('data')
    n_vars = len(ds.get('variables', []))
    n_points = data_matrix.shape[0] if data_matrix is not None and data_matrix.ndim > 1 else 0

    print(f"  Variables: {n_vars}")
    print(f"  Points: {n_points:,}")
    if data_matrix is not None:
        is_mmap = hasattr(data_matrix, 'filename')
        print(f"  Matrix shape: {data_matrix.shape}")
        print(f"  Matrix dtype: {data_matrix.dtype}")
        print(f"  Matrix size: {fmt_bytes(data_matrix.nbytes)}")
        print(f"  Storage: {'memmap' if is_mmap else 'column_stack'}")
    print(f"  raw_data is None: {rf.raw_data is None}")

    # Stage 2: Dataset instantiation
    print(f"\n--- Stage 2: Dataset() ---")
    dataset = Dataset(rf, dataset_idx=0)
    snap("after Dataset")
    print(f"  Variables: {dataset.n_variables}")
    print(f"  Points: {dataset.n_points}")

    # Stage 3: Variable access (cache verification)
    print(f"\n--- Stage 3: Variable access ---")
    for var in dataset.variables[:3]:
        d1 = rf.get_variable_data(var.name, 0)
        d2 = rf.get_variable_data(var.name, 0)
        d3 = rf.get_variable_data(var.name, 0)
        same = (d1 is d2 is d3) if d1 is not None else False
        dtype_str = str(d1.dtype) if d1 is not None else "None"
        print(f"  {var.name}: dtype={dtype_str}, cache_hits_same={same}")
    snap("after variable access")

    # Stage 4: Complex derived data if applicable
    print(f"\n--- Stage 4: Derived variables ---")
    has_complex = False
    for var in dataset.variables:
        if var.is_complex:
            has_complex = True
            mag = var.magnitude
            phase = var.phase
            print(f"  {var.name}: complex, mag dtype={mag.dtype}, phase dtype={phase.dtype}")
    if not has_complex:
        print(f"  (no complex variables)")
    snap("after derived access")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    rss_end = snap("FINAL")
    ratio = rss_end / file_size
    delta = rss_end - rss_start
    print(f"\n  RSS / file size ratio: {ratio:.2f}x")
    print(f"  RSS increase from start: {fmt_bytes(delta)}")
    print(f"  Matrix occupies: {fmt_bytes(data_matrix.nbytes) if data_matrix is not None else 'N/A'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python memory_profile_light.py <raw_file>")
        sys.exit(1)
    main(sys.argv[1])
