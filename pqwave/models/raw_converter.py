#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RawFileConverter - Convert SPICE raw files between formats.

Supports conversion between:
- LTspice (.raw): utf_16_le encoding, float32 real data, complex128 for AC
- QSPICE (.qraw): utf_8 encoding, float64 real data, complex128 for AC
- ngspice (.raw): utf_8 encoding, float64 real data, complex128 for AC
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
        'time_dtype': np.float64,
        'ac_dtype': np.complex128,
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

            if is_ac_or_complex and dtype == np.complex128:
                # Complex: store real then imag as float64
                val = complex(value)
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
