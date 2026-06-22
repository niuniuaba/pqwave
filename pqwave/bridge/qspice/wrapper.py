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

from pqwave.logging_config import get_logger

logger = get_logger(__name__)


def _wine_prefixes() -> list[str]:
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

    # 1. PQWAVE_QSPICE env var
    env_path = os.environ.get("PQWAVE_QSPICE")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. ApplicationState.tool_paths
    # Lazy import to avoid pulling in Qt at module level.
    from pqwave.models.state import ApplicationState  # noqa: PLC0415

    state = ApplicationState()
    state_path = state.tool_paths.get("qspice")
    if state_path and os.path.isfile(state_path):
        return state_path

    # 3. Wine prefix search
    qspice64_name = "QSPICE64.exe"
    qspice_name = "QSPICE.exe"
    for prefix in _wine_prefixes():
        for exe_name in (qspice64_name, qspice_name):
            candidate = os.path.join(
                prefix,
                "drive_c",
                "Program Files",
                "QSPICE",
                exe_name,
            )
            if os.path.isfile(candidate):
                return candidate

    # 4. shutil.which search
    found = shutil.which(qspice64_name)
    if found:
        return found
    found = shutil.which(qspice_name)
    if found:
        return found

    # 5. All lookups exhausted
    raise FileNotFoundError(
        "Could not locate QSPICE64.exe / QSPICE.exe. "
        "Set the PQWAVE_QSPICE environment variable to the correct path, "
        "or configure it in Tool Paths in the pqwave settings dialog."
    )


def resolve_qux() -> str | None:
    """Find QUX.exe alongside QSPICE64.exe.

    QUX is QSPICE's data export tool, shipped in the same directory
    as QSPICE64.exe.  Returns the path to QUX.exe, or None if QSPICE
    is not installed.

    This function MUST NOT import Qt.
    """
    try:
        qspice_path = resolve_qspice()
    except FileNotFoundError:
        return None

    qspice_dir = os.path.dirname(qspice_path)
    for name in ("QUX.exe", "qux.exe", "QUX", "qux"):
        candidate = os.path.join(qspice_dir, name)
        if os.path.isfile(candidate):
            return candidate

    found = shutil.which("QUX.exe") or shutil.which("qux")
    if found:
        return found

    return None


def qsch2cir(qsch_path: str, timeout: int = 30) -> str:
    """Convert a .qsch schematic to a .cir netlist via QUX.exe -Netlist.

    QUX.exe is QSPICE's CLI tool — this does NOT require the QSPICE GUI.
    Works under Wine on Linux.

    Args:
        qsch_path: Path to the .qsch schematic file.
        timeout: Seconds to wait for QUX -Netlist (default 30).

    Returns the path to the generated .cir file (alongside the .qsch).
    Raises FileNotFoundError if QUX is unavailable.
    Raises RuntimeError if QUX exits non-zero.
    """
    qux = resolve_qux()
    if not qux:
        raise FileNotFoundError(
            "QUX.exe not found. QSPICE must be installed to convert "
            ".qsch schematics. Set PQWAVE_QSPICE to the QSPICE64.exe path."
        )

    cir_path = os.path.splitext(qsch_path)[0] + ".cir"

    if sys.platform == "win32":
        cmd = [qux, "-Netlist", qsch_path, "-stdout"]
    else:
        wine = shutil.which("wine")
        if not wine:
            raise FileNotFoundError("wine not found on PATH")
        cmd = [wine, qux, "-Netlist", qsch_path, "-stdout"]

    proc = subprocess.run(
        cmd, capture_output=True, timeout=timeout,
    )

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(
            f"QUX -Netlist failed (exit {proc.returncode}): {stderr[:500]}"
        )

    # Write netlist bytes as-is — QSPICE64.exe reads the same encoding
    with open(cir_path, "wb") as fh:
        fh.write(proc.stdout)

    logger.info("Converted %s → %s", os.path.basename(qsch_path),
                 os.path.basename(cir_path))
    return cir_path


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

    @staticmethod
    def _launch_pqwave(qraw_path: str) -> int:
        """Launch the pqwave GUI with the given .qraw file (headless)."""
        cmd = [sys.executable, "-m", "pqwave.main", qraw_path]
        try:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            sys.stderr.write(
                "qspice-bridge: pqwave not found on PATH; "
                ".qraw was saved but viewer could not be launched\n"
            )
        except OSError as exc:
            sys.stderr.write(
                f"qspice-bridge: failed to launch pqwave: {exc}\n"
            )
        return 0

    def run(self, netlist_path: str) -> int:
        """Run the full pipeline.

        1. Verify netlist exists.
        2. Resolve QSPICE path.
        3. Build and execute the simulation command.
        4. Verify .qraw output was created.
        5. Optionally launch pqwave GUI.

        Returns:
            Exit code: 0 on success.
        """
        # 1. Verify netlist exists
        abs_netlist = os.path.abspath(netlist_path)
        if not os.path.isfile(abs_netlist):
            raise FileNotFoundError(
                f"Netlist not found: {abs_netlist}"
            )

        # 2. Resolve QSPICE path
        qspice = self._qspice_path or resolve_qspice()

        # 3. Build command
        netlist_dir = os.path.dirname(os.path.abspath(netlist_path))
        netlist_name = os.path.basename(netlist_path)

        if sys.platform == "win32":
            cmd = [qspice, netlist_name]
        else:
            wine = shutil.which("wine")
            if wine is None:
                raise FileNotFoundError(
                    "wine not found on PATH; QSPICE requires Wine on this platform"
                )
            cmd = [wine, qspice, netlist_name]

        try:
            proc = subprocess.run(
                cmd,
                cwd=netlist_dir,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(
                "qspice-bridge: QSPICE simulation timed out after 300 seconds\n"
            )
            return 1

        # 4. Handle non-zero exit
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            if not proc.stderr and proc.stdout:
                sys.stderr.write(proc.stdout)
            return proc.returncode

        # 5. Verify .qraw output
        qraw_path = os.path.splitext(abs_netlist)[0] + ".qraw"
        if not os.path.isfile(qraw_path):
            sys.stderr.write(
                f"qspice-bridge: expected .qraw output not found: {qraw_path}\n"
            )
            return 1

        # 6. Optionally launch GUI
        if self._auto_open:
            self._launch_pqwave(qraw_path)

        return 0
