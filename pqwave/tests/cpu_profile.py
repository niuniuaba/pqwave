#!/usr/bin/env python3
"""
CPU profiler for pqwave raw file loading.

Measures CPU time at each stage of the data pipeline and runs cProfile
on the full RawFile.parse() call.

Usage:
    python pqwave/tests/cpu_profile.py <raw_file>

    e.g.  python pqwave/tests/cpu_profile.py pqwave/tests/bridge.raw
          python pqwave/tests/cpu_profile.py tests/SMPS.qraw
"""

import sys
import os
import gc
import time
import cProfile
import pstats
import io
import numpy as np

# Allow running as script or as module
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(script_dir)))

from pqwave.models.rawfile import RawFile, preprocess_raw_file, _parse_header_variables
from pqwave.models.dataset import Dataset
from pqwave.models.expression import ExprEvaluator


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


def profile_stages(filepath: str) -> dict:
    """Profile each stage individually with timing."""
    print(f"\n{'='*70}")
    print(f"CPU Profile (per-stage timing): {filepath}")
    print(f"{'='*70}")

    file_size = os.path.getsize(filepath)
    print(f"File size: {fmt_bytes(file_size)}")
    print()

    timings = {}

    # Stage 1: Read raw bytes (for header parsing)
    t0 = time.perf_counter()
    with open(filepath, 'rb') as f:
        raw_bytes = f.read()
    t1 = time.perf_counter()
    timings['read_bytes'] = t1 - t0
    print(f'Stage 1: Read raw bytes               {timings["read_bytes"]:.3f}s  ({len(raw_bytes)/1024**2:.1f} MB)')

    # Stage 2: Preprocess + parse header
    t0 = time.perf_counter()
    correct_variables, is_ac_or_complex = _parse_header_variables(raw_bytes)
    t_parse = time.perf_counter()
    load_path = preprocess_raw_file(filepath)
    t_pre = time.perf_counter()
    timings['parse_header'] = t_parse - t0
    timings['preprocess'] = t_pre - t_parse
    is_tmp = load_path != filepath
    print(f'Stage 2a: _parse_header_variables     {timings["parse_header"]:.3f}s  ({len(correct_variables)} vars)')
    print(f'Stage 2b: preprocess_raw_file         {timings["preprocess"]:.3f}s')

    # Stage 3: Full RawFile.parse()
    print(f'\n--- Stage 3: RawFile.parse() (full pipeline) ---')
    t0 = time.perf_counter()
    rf = RawFile(filepath)
    t1 = time.perf_counter()
    timings['rawfile_parse'] = t1 - t0
    print(f'Stage 3: RawFile.parse()              {timings["rawfile_parse"]:.3f}s')

    if not rf.datasets:
        print("  No datasets found!")
        return timings

    ds = rf.datasets[0]
    data_matrix = ds['data']
    n_vars = data_matrix.shape[1] if data_matrix.ndim > 1 else 0
    n_points = data_matrix.shape[0] if data_matrix.ndim > 1 else 0
    var_names = [v['name'] for v in ds.get('variables', [])]

    print(f'  -> {n_vars} vars, {n_points:,} points, dtype={data_matrix.dtype}')
    print(f'  -> raw_data is None: {rf.raw_data is None}')

    # Stage 4: Dataset instantiation
    print(f'\n--- Stage 4: Dataset() ---')
    t0 = time.perf_counter()
    dataset = Dataset(rf, dataset_idx=0)
    t1 = time.perf_counter()
    timings['dataset_init'] = t1 - t0
    print(f'Stage 4: Dataset()                    {timings["dataset_init"]:.3f}s')

    # Stage 5: get_variable_data repeated calls (cache test)
    print(f'\n--- Stage 5: get_variable_data repeated calls (with cache) ---')
    t0 = time.perf_counter()
    for _ in range(5):
        for name in var_names[:5]:
            rf.get_variable_data(name, 0)
    t1 = time.perf_counter()
    timings['cached_get_5x5'] = t1 - t0
    print(f'Stage 5: 5x5 cached get_variable_data {timings["cached_get_5x5"]:.3f}s')
    # Verify cache works
    if var_names:
        a1 = rf.get_variable_data(var_names[0], 0)
        a2 = rf.get_variable_data(var_names[0], 0)
        print(f'  Cache working: {a1 is a2}')

    # Stage 6: Complex derivation if applicable
    if ds.get('_is_ac_or_complex', False):
        print(f'\n--- Stage 6: Complex derivation ---')
        t0 = time.perf_counter()
        for var in ds['variables'][:5]:
            vname = var['name']
            rf._get_complex_magnitude(vname, 0)
            rf._get_complex_real(vname, 0)
            rf._get_complex_imag(vname, 0)
            rf._get_complex_phase(vname, 0)
        t1 = time.perf_counter()
        timings['complex_derive_5'] = t1 - t0
        print(f'Stage 6: derive 5 complex vars     {timings["complex_derive_5"]:.3f}s')
    else:
        print(f'\n--- Stage 6: N/A (not AC/complex) ---')

    # Stage 7: ExprEvaluator
    print(f'\n--- Stage 7: ExprEvaluator ---')
    evaluator = ExprEvaluator(rf, 0)
    print(f'  n_points: {evaluator.n_points:,}')

    if len(var_names) >= 2:
        v0 = var_names[0]
        v1 = var_names[1]
    elif len(var_names) == 1:
        v0 = var_names[0]
        v1 = v0
    else:
        v0 = v1 = ''

    exprs = [
        ('simple', v0),
        ('add', f'{v0} + {v1}'),
        ('multiply', f'{v0} * {v1}'),
    ]

    for label, expr in exprs:
        t0 = time.perf_counter()
        for _ in range(5):
            result = evaluator.evaluate(expr)
        t1 = time.perf_counter()
        print(f'  [{label}] 5x evaluate  {(t1-t0)*1000:.1f}ms  -> {result.shape}, dtype={result.dtype}')

    # Cleanup temp file
    if is_tmp and os.path.exists(load_path):
        os.unlink(load_path)

    # Summary table
    print(f'\n{"="*70}')
    print('CPU TIME SUMMARY')
    print(f'{"="*70}')
    total_time = sum(timings.values())
    for name, t in timings.items():
        pct = t / total_time * 100
        print(f'  {name:30s}  {t:.3f}s  ({pct:5.1f}%)')
    print(f'  {"TOTAL":30s}  {total_time:.3f}s')

    return timings


def profile_cprofile(filepath: str):
    """Run cProfile on full RawFile.parse()."""
    print(f'\n{"="*70}')
    print(f'cProfile: RawFile.parse()')
    print(f'{"="*70}')

    gc.collect()
    pr = cProfile.Profile()
    pr.enable()
    rf = RawFile(filepath)
    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(25)
    print(s.getvalue())

    # Top by tottime
    print(f'{"="*70}')
    print(f'cProfile: Top by tottime (self time)')
    print(f'{"="*70}')
    s2 = io.StringIO()
    ps2 = pstats.Stats(pr, stream=s2).sort_stats('tottime')
    ps2.print_stats(15)
    print(s2.getvalue())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cpu_profile.py <raw_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    profile_stages(filepath)
    profile_cprofile(filepath)
