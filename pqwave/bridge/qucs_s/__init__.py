"""Qucs-S bridge integration.

Provides the headless post-simulation hook that runs ngspice in batch mode
and copies output files to the schematic directory for viewing in pqwave.
"""

from pqwave.bridge.qucs_s.wrapper import (
    QucsBridgeRunner,
    copy_output_files,
    extract_schematic_path,
    find_output_files,
    resolve_ngspice,
)

__all__ = [
    "QucsBridgeRunner",
    "copy_output_files",
    "extract_schematic_path",
    "find_output_files",
    "resolve_ngspice",
]
