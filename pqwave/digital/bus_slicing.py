"""Bus slicing and concatenation for digital signal expressions.

Supports Verilog-style syntax: bus[msb:lsb] for extraction,
{bus_a, bus_b} for concatenation.
"""

import numpy as np
from typing import List, Optional, Tuple


def slice_bus(bus_values: np.ndarray, msb: int, lsb: int) -> np.ndarray:
    """Extract a bit range from bus integer values.

    bus[7:4] extracts bits 7 down to 4.  bus[3] extracts bit 3.
    """
    bv = bus_values.astype(np.int64)
    if msb == lsb:
        return (bv >> lsb) & 1
    width = msb - lsb + 1
    mask = (1 << width) - 1
    return ((bv >> lsb) & mask).astype(np.float64)


def concat_buses(*bus_arrays: np.ndarray) -> np.ndarray:
    """Concatenate bus values: {bus_a, bus_b} where bus_a is MSB."""
    if not bus_arrays:
        return np.array([], dtype=np.float64)
    n = len(bus_arrays[0])
    if n == 0:
        return np.array([], dtype=np.float64)
    result = np.zeros(n, dtype=np.int64)
    for arr in bus_arrays:
        arr_clean = np.nan_to_num(arr, nan=0.0)
        arr_max = float(arr_clean.max())
        if arr_max <= 0:
            width = 1
        else:
            width = max(1, int(np.ceil(np.log2(arr_max + 1))))
        result = (result << width) | arr_clean.astype(np.int64)
    return result.astype(np.float64)


def parse_bus_slice(expr: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Parse a bus slice expression like 'bus_name[7:4]' or 'bus_name[3]'.

    Returns (base_name, msb, lsb) or (expr, None, None) if not a slice.
    """
    if '[' not in expr or not expr.endswith(']'):
        return expr, None, None

    bracket_pos = expr.index('[')
    base = expr[:bracket_pos]
    inner = expr[bracket_pos + 1:-1]

    if ':' in inner:
        parts = inner.split(':')
        try:
            return base, int(parts[0]), int(parts[1])
        except ValueError:
            return expr, None, None
    try:
        bit = int(inner)
        return base, bit, bit
    except ValueError:
        return expr, None, None
