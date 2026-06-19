"""Headless QSPICE simulation runner.

This module is called when pqwave runs a QSPICE simulation:
    pqwave --qspice-bridge circuit.cir

It invokes QSPICE64.exe (via wine on Linux), waits for the .qraw
output, and optionally launches the pqwave GUI.

CRITICAL: This module MUST NOT import Qt. It runs headless, before
QApplication exists.
"""

import os
import sys
import subprocess
import shutil


def _wine_prefixes() -> list:
    """Return common Wine prefix paths to search for QSPICE."""
    home = os.path.expanduser("~")
    return [
        os.path.join(home, ".wine"),
        os.path.join(home, ".wine32"),
        os.path.join(home, ".wine64"),
        os.path.join(home, "Games", "qspice"),
    ]


def resolve_qspice() -> str:
    """Resolve QSPICE64.exe path with priority chain.

    1. ``PQWAVE_QSPICE`` environment variable
    2. ``ApplicationState().tool_paths.get("qspice")``
    3. Filesystem search under common Wine prefixes
    4. ``shutil.which("QSPICE64.exe")`` / ``shutil.which("QSPICE.exe")``
    5. Raise ``FileNotFoundError``

    This function MUST NOT import Qt.
    """
    raise NotImplementedError("resolve_qspice not yet implemented")


class QspiceBridgeRunner:
    """Orchestrator for the QSPICE post-simulation pipeline.

    Parameters:
        qspice_path: Path to QSPICE64.exe. If empty, resolve_qspice()
            is called at run time.
        auto_open: When True (the default), the pqwave GUI is launched
            after successful simulation. Set to False via the
            ``PQWAVE_QSPICE_AUTO_OPEN=0`` environment variable.
    """

    def __init__(self, qspice_path: str = "", auto_open: bool = True):
        self._qspice_path = qspice_path
        env_auto_open = os.environ.get("PQWAVE_QSPICE_AUTO_OPEN", "")
        if env_auto_open == "0":
            auto_open = False
        self._auto_open = auto_open

    def run(self, netlist_path: str) -> int:
        """Run the full pipeline.

        Returns:
            Exit code: 0 on success.
        """
        raise NotImplementedError("run not yet implemented")
