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
    if os.path.basename(script_dir) == "tests":
        sys.path.insert(0, os.path.dirname(script_dir))
    else:
        sys.path.insert(0, script_dir)

from pqwave.models.rawfile import RawFile, preprocess_raw_file, _parse_header_variables
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

    # Stage 1: Read raw bytes
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
    print(f'Stage 2a: _parse_header_variables     {timings["parse_header"]:.3f}s  ({len(correct_variables)} vars)')
    print(f'Stage 2b: preprocess_raw_file         {timings["preprocess"]:.3f}s')

    # Stage 3: RawRead (header only)
    from spicelib import RawRead
    t0 = time.perf_counter()
    raw_data = RawRead(load_path)
    t1 = time.perf_counter()
    spicelib_traces = raw_data.get_trace_names()
    timings['rawread_header'] = t1 - t0
    print(f'Stage 3: RawRead() parse header       {timings["rawread_header"]:.3f}s  ({len(spicelib_traces)} traces)')

    # Stage 4: get_trace loop (current approach - one by one)
    print(f'')
    print(f'--- Stage 4: get_trace() loop (current: one by one) ---')
    t0 = time.perf_counter()
    data_list = []
    for i, name in enumerate(spicelib_traces):
        t_each = time.perf_counter()
        trace = raw_data.get_trace(name)
        data = trace.get_wave()
        data_list.append(data)
        t_each_end = time.perf_counter()
        if i < 5 or i >= len(spicelib_traces) - 3:
            print(f'  get_trace #{i:2d} {name:20s}  {t_each_end - t_each:.3f}s')
        elif i == 5:
            print(f'  ...')
    t1 = time.perf_counter()
    timings['get_trace_loop'] = t1 - t0
    print(f'Stage 4: get_trace() ({len(spicelib_traces)} vars)  {timings["get_trace_loop"]:.3f}s')
    print(f'  avg per variable: {timings["get_trace_loop"] / len(spicelib_traces):.3f}s')

    # Stage 5: column_stack
    t0 = time.perf_counter()
    data = np.column_stack(data_list)
    t1 = time.perf_counter()
    timings['column_stack'] = t1 - t0
    print(f'Stage 5: np.column_stack              {timings["column_stack"]:.3f}s  ({data.shape}, {data.dtype}, {data.nbytes/1024**2:.0f} MB)')

    # Stage 6: get_variable_data repeated (no caching)
    print(f'\n--- Stage 6: get_variable_data repeated calls (no caching) ---')
    t0 = time.perf_counter()
    for _ in range(3):
        for name in spicelib_traces[:5]:
            trace = raw_data.get_trace(name)
            arr = trace.get_wave()
    t1 = time.perf_counter()
    timings['repeated_get'] = t1 - t0
    print(f'Stage 6: 3x5 get_trace calls          {timings["repeated_get"]:.3f}s')

    # Stage 7: ExprEvaluator
    print(f'\n--- Stage 7: ExprEvaluator ---')
    class CachedMockRF:
        def __init__(self, data_list, trace_names, n_points):
            self._data = {name: arr for name, arr in zip(trace_names, data_list)}
            self._n_points = n_points
        def get_variable_data(self, name, idx=0):
            return self._data.get(name)
        def get_num_points(self, idx=0):
            return self._n_points

    mock_rf = CachedMockRF(data_list, spicelib_traces, len(data_list[0]))
    evaluator = ExprEvaluator(mock_rf, 0)
    print(f'  n_points: {evaluator.n_points:,}')

    v0 = spicelib_traces[0]
    v1 = spicelib_traces[1] if len(spicelib_traces) > 1 else v0

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
        print(f'  [{label}] 5x evaluate  {(t1-t0)*1000:.1f}ms  -> {result.shape}')

    # Cleanup temp file
    if load_path != filepath and os.path.exists(load_path):
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
