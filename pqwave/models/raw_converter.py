#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RawFileConverter - Convert SPICE raw files between formats.

Supports conversion between:
- LTspice (.raw): utf_16_le encoding, float32 real data, complex64 for AC
- QSPICE (.qraw): utf_8 encoding, float32 real data, complex64 for AC
- ngspice (.raw): utf_8 encoding, float32 real data, complex64 for AC
"""

import struct
import numpy as np
from pqwave.logging_config import get_logger

logger = get_logger(__name__)

# Format configurations
FORMAT_CONFIG = {
    'ltspice': {
        'encoding': 'utf_16_le',
        'command_line': 'Command: Linear Technology Corporation LTspice XVII',
        'real_dtype': np.float32,
        'time_dtype': np.float64,  # LTspice stores time axis as float64
        'ac_dtype': np.complex128,  # AC: complex as pair of float64
        'freq_dtype': np.float64,
        'extension': '.raw',
    },
    'qspice': {
        'encoding': 'utf_8',
        'command_line': 'Command: QSPICE64',
        'real_dtype': np.float64,
        'time_dtype': np.float64,
        'ac_dtype': np.complex128,
        'freq_dtype': np.float64,
        'extension': '.qraw',
    },
    'ngspice': {
        'encoding': 'utf_8',
        'command_line': 'Command: ngspice-45.2',
        'real_dtype': np.float64,
        'time_dtype': np.float64,
        'ac_dtype': np.complex128,
        'freq_dtype': np.float64,
        'extension': '.raw',
    },
}


def _get_dtype_for_variable(var, config, is_ac_or_complex):
    """Determine the numpy dtype for a variable based on format and type."""
    var_name = var['name'].lower()

    if is_ac_or_complex:
        if var_name in ('freq', 'frequency', 'hz'):
            return config['freq_dtype']
        else:
            return config['ac_dtype']
    else:
        if var_name == 'time':
            return config['time_dtype']
        else:
            return config['real_dtype']


def _infer_variable_type(expression: str, raw_file, dataset_idx: int = 0) -> str:
    """Infer the SPICE variable type string for a trace expression.

    Tokenizes the expression to find variable references, then looks up
    their type in the source dataset.
    """
    if not expression:
        return 'voltage'

    from pqwave.models.expression import ExprEvaluator
    evaluator = ExprEvaluator(raw_file, dataset_idx)
    tokens = evaluator.tokenize(expression)

    # Collect all VARIABLE tokens
    var_tokens = [t[1] for t in tokens if t[0] == 'VARIABLE']
    has_operators = any(t[0] == 'OPERATOR' for t in tokens)

    # Determine the variable name to look up
    lookup_name = None
    if var_tokens and not has_operators and len(var_tokens) == 1:
        lookup_name = var_tokens[0]
    elif var_tokens:
        first_var = var_tokens[0]
        for prefix in ('mag(', 'real(', 'imag(', 'ph(', 're(', 'im(', 'cph(', 'phase('):
            if first_var.startswith(prefix) and first_var.endswith(')'):
                lookup_name = first_var[len(prefix):-1]
                break
        if lookup_name is None:
            lookup_name = first_var

    if lookup_name is None:
        return 'voltage'

    dataset = raw_file.datasets[dataset_idx]
    for var in dataset.get('variables', []):
        if var['name'] == lookup_name:
            return var.get('type', 'voltage')

    return 'voltage'


def extract_traces_to_raw(
    output_path: str,
    traces: list,
    raw_file,
    target_format: str = 'ltspice',
    output_is_ac: bool = False,
    x_var_name: str | None = None,
    x_var_data: np.ndarray | None = None,
    dataset_idx: int = 0,
):
    """Extract currently displayed traces to a new SPICE raw file.

    Assembles trace data (x_data, y_data) into a 2D column-major array
    and writes via write_raw_file().

    Args:
        output_path: Path to write the output file
        traces: List of Trace dataclass objects with x_data, y_data
        raw_file: Source RawFile instance (for dataset metadata and type inference)
        target_format: One of 'ltspice', 'qspice', 'ngspice'
        output_is_ac: Force AC output mode (default: auto-detect from source dataset)
        x_var_name: Custom X variable name; appended as extra variable in output
        x_var_data: Custom X variable data array (uses first trace x_data if omitted)
    """
    config = FORMAT_CONFIG[target_format]
    dataset = raw_file.datasets[dataset_idx]
    is_ac = output_is_ac or dataset.get('_is_ac_or_complex', False)

    if not traces:
        raise ValueError("No traces to extract")

    # Determine n_points: use minimum across all traces
    n_points = min(len(t.x_data) for t in traces)

    # Build variable list from traces first (Y traces)
    variables = []
    for i, trace in enumerate(traces):
        var_type = _infer_variable_type(trace.expression, raw_file, dataset_idx)
        variables.append({
            'index': i,
            'name': trace.expression,
            'type': var_type,
        })

    # Append X variable if provided and not already in the list
    have_x_var = False
    if x_var_name:
        existing_names = {v['name'] for v in variables}
        if x_var_name not in existing_names:
            x_type = 'frequency' if is_ac else 'time'
            variables.append({
                'index': len(variables),
                'name': x_var_name,
                'type': x_type,
            })
            have_x_var = True

    n_vars = len(variables)

    # Check if any trace actually has non-zero imaginary data
    has_complex_data = False
    if is_ac:
        for trace in traces:
            y = trace.y_data[:n_points]
            if np.iscomplexobj(y) and np.any(y.imag != 0):
                has_complex_data = True
                break
        if have_x_var and not has_complex_data:
            x_col = x_var_data[:n_points] if x_var_data is not None else traces[0].x_data[:n_points]
            if np.iscomplexobj(x_col) and np.any(x_col.imag != 0):
                has_complex_data = True

    if has_complex_data:
        data = np.zeros((n_points, n_vars), dtype=np.complex128)
        for i, trace in enumerate(traces):
            data[:, i] = trace.y_data[:n_points]
        if have_x_var:
            x_col = x_var_data[:n_points] if x_var_data is not None else traces[0].x_data[:n_points]
            data[:, -1] = x_col
    else:
        # Transient output: all real
        data = np.zeros((n_points, n_vars), dtype=np.float64)
        for i, trace in enumerate(traces):
            data[:, i] = trace.y_data[:n_points].real
        if have_x_var:
            x_col = x_var_data[:n_points] if x_var_data is not None else traces[0].x_data[:n_points]
            data[:, -1] = x_col

    # Get metadata from source dataset
    title = dataset.get('title', 'pqwave extraction')
    date = dataset.get('date', '')
    plotname = 'ac' if has_complex_data else 'transient'
    flags = 'complex' if has_complex_data else 'real'

    write_raw_file(
        output_path=output_path,
        title=title,
        date=date,
        plotname=plotname,
        flags=flags,
        variables=variables,
        data=data,
        target_format=target_format,
        is_ac_or_complex=has_complex_data,
    )
    logger.info(f"Extracted {len(traces)} traces to {output_path} ({target_format})")


def write_raw_file(
    output_path: str,
    title: str,
    date: str,
    plotname: str,
    flags: str,
    variables: list,
    data: np.ndarray,
    target_format: str = 'ltspice',
    is_ac_or_complex: bool = False,
):
    """Write a SPICE raw file in the specified format.

    Args:
        output_path: Path to write the output file
        title: Plot title
        date: Date string
        plotname: Plot name (e.g. 'transient', 'ac')
        flags: Flags string
        variables: List of variable dicts with 'index', 'name', 'type'
        data: 2D numpy array, shape (n_points, n_variables)
        target_format: One of 'ltspice', 'qspice', 'ngspice'
        is_ac_or_complex: Whether this is an AC/complex analysis
    """
    config = FORMAT_CONFIG[target_format]
    encoding = config['encoding']
    n_points = data.shape[0] if data.ndim > 1 else len(data)
    n_vars = data.shape[1] if data.ndim > 1 else 1

    # Ensure data is at least 2D
    if data.ndim == 1:
        data = data.reshape(-1, 1)

    # Build header lines
    header_lines = []
    header_lines.append(f'Title: {title}')
    header_lines.append(f'Date: {date}')
    header_lines.append(f'Plotname: {plotname}')
    header_lines.append(f'Flags: {flags}')
    header_lines.append(f'No. Variables: {n_vars}')
    header_lines.append(f'No. Points: {n_points}')

    # Command line must come BEFORE Variables: for dialect detection
    header_lines.append(config['command_line'])

    # Variables section
    header_lines.append('Variables:')
    for i, var in enumerate(variables):
        var_name = var['name']

        # Map dtype to SPICE type string
        if is_ac_or_complex:
            if var_name.lower() in ('freq', 'frequency', 'hz'):
                spice_type = 'frequency'
            else:
                spice_type = 'complex'
        else:
            if var_name.lower() == 'time':
                spice_type = 'time'
            elif var_name.lower().startswith('v('):
                spice_type = 'voltage'
            elif var_name.lower().startswith('i('):
                spice_type = 'current'
            else:
                spice_type = var.get('type', 'unknown')

        header_lines.append(f'\t{i}\t{var_name}\t{spice_type}')

    header_lines.append('Binary:')

    # Join header with newlines, encode, and add Binary marker
    header_text = '\n'.join(header_lines) + '\n'
    header_bytes = header_text.encode(encoding)

    # Write binary data
    # Data is stored as row-interleaved: all vars for point 0, then all vars for point 1, ...
    binary_parts = []
    for pt_idx in range(n_points):
        for var_idx, var in enumerate(variables):
            dtype = _get_dtype_for_variable(var, config, is_ac_or_complex)
            value = data[pt_idx, var_idx]

            if is_ac_or_complex and dtype in (np.complex64, np.complex128):
                # Complex: store real then imag
                val = complex(value)
                if dtype == np.complex64:
                    binary_parts.append(struct.pack('<f', val.real))
                    binary_parts.append(struct.pack('<f', val.imag))
                else:
                    binary_parts.append(struct.pack('<d', val.real))
                    binary_parts.append(struct.pack('<d', val.imag))
            else:
                # Real value
                val = float(np.real(value))
                if dtype == np.float32:
                    binary_parts.append(struct.pack('<f', val))
                else:
                    binary_parts.append(struct.pack('<d', val))

    binary_data = b''.join(binary_parts)

    # Write file
    with open(output_path, 'wb') as f:
        f.write(header_bytes)
        f.write(binary_data)

    logger.info(
        f"Written {target_format} raw file: {output_path} "
        f"({n_points} points, {n_vars} variables)"
    )
