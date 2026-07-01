"""Worst-case analysis engine -- corner enumeration, tempco, sensitivity, netlist mod.

Pure-numpy where applicable; no Qt dependencies.
"""

from __future__ import annotations

import itertools
import re
from typing import Any


def enumerate_corners(components: dict[str, dict]) -> list[dict[str, float]]:
    """Enumerate all 2^N tolerance corners.

    Args:
        components: dict of refdes -> {nominal, tolerance, ...}

    Returns:
        List of corner dicts: [{refdes: value, ...}, ...]
    """
    refdes_list = list(components.keys())
    n = len(refdes_list)
    corners: list[dict[str, float]] = []

    # Generate all combinations of (min, max) for each component
    for bits in itertools.product([0, 1], repeat=n):
        corner: dict[str, float] = {}
        for i, refdes in enumerate(refdes_list):
            comp = components[refdes]
            nominal = comp["nominal"]
            tol = comp["tolerance"]
            if bits[i] == 0:
                corner[refdes] = nominal * (1.0 - tol)
            else:
                corner[refdes] = nominal * (1.0 + tol)
        corners.append(corner)

    return corners


def apply_tempco(
    nominal: float, tempco: float, t_actual: float, t_nom: float = 27.0
) -> float:
    """Apply temperature coefficient to a nominal value.

    Args:
        nominal: Nominal value at Tnom.
        tempco: Temperature coefficient (per deg C). e.g., 200e-6 for 200 ppm/deg C.
        t_actual: Actual temperature in deg C.
        t_nom: Nominal temperature in deg C (default 27).

    Returns:
        Temperature-adjusted value.
    """
    return nominal * (1.0 + tempco * (t_actual - t_nom))


def rank_by_sensitivity(sensitivities: dict[str, float], top_n: int = 8) -> list[str]:
    """Rank components by absolute sensitivity (highest first).

    Args:
        sensitivities: {refdes: abs_sensitivity, ...}
        top_n: Maximum number of components to return.

    Returns:
        List of refdes sorted by decreasing sensitivity.
    """
    sorted_items = sorted(sensitivities.items(), key=lambda x: abs(x[1]), reverse=True)
    return [refdes for refdes, _ in sorted_items[:top_n]]


def modify_netlist(netlist: str, corner: dict[str, float]) -> str:
    """Replace component values in a SPICE netlist for a given corner.

    Matches lines like: ``R1 n1 n2 10k`` or ``R1 n1 n2 10000``

    Args:
        netlist: Original SPICE netlist text.
        corner: {refdes: new_value, ...}

    Returns:
        Modified netlist text.
    """
    lines = netlist.splitlines()
    result: list[str] = []
    for line in lines:
        modified = line
        for refdes, value in corner.items():
            # Match: <refdes> <node1> <node2> <value> [optional rest]
            pattern = re.compile(
                rf"^({re.escape(refdes)})\s+(\S+)\s+(\S+)\s+(\S+)",
                re.IGNORECASE,
            )
            match = pattern.match(line.strip())
            if match:
                prefix = line[: match.start()]
                suffix = line[match.end() :]
                modified = (
                    f"{prefix}{match.group(1)} {match.group(2)} "
                    f"{match.group(3)} {_format_spice_value(value)}{suffix}"
                )
                break
        result.append(modified)
    return "\n".join(result)


def parse_op_output(stdout: str, target: str | None = None) -> float | None:
    """Parse an ngspice .op output for a voltage or current value.

    Args:
        stdout: ngspice stdout text from a .op simulation.
        target: Optional variable name to match (e.g., "v(out)").
                If None, returns the first voltage/current found.

    Returns:
        Float value or None if no match found.
    """
    pattern = re.compile(
        r"([vi])\((\S+)\)\s*=\s*([-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)",
        flags=re.MULTILINE,
    )
    for match in pattern.finditer(stdout):
        vtype = match.group(1)
        node = match.group(2)
        value_str = match.group(3)
        full_name = f"{vtype}({node})"
        if target is None or full_name.lower() == target.lower():
            return float(value_str)
    return None


def _format_spice_value(value: float) -> str:
    """Format a float as a SPICE-compatible value string."""
    if abs(value) >= 1e6:
        return f"{value/1e6:.6g}Meg"
    elif abs(value) >= 1e3:
        return f"{value/1e3:.6g}k"
    elif abs(value) >= 1.0:
        return f"{value:.6g}"
    elif abs(value) >= 1e-3:
        return f"{value*1e3:.6g}m"
    elif abs(value) >= 1e-6:
        return f"{value*1e6:.6g}u"
    elif abs(value) >= 1e-9:
        return f"{value*1e9:.6g}n"
    elif abs(value) >= 1e-12:
        return f"{value*1e12:.6g}p"
    else:
        return f"{value:.6g}"
