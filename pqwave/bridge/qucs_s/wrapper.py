"""Headless post-simulation hook for Qucs-S integration.

This module is called when Qucs-S runs a simulation:
    pqwave --qucs-bridge spice4qucs.cir

It runs ngspice in batch mode, copies output files to the schematic
directory, and optionally launches the pqwave GUI.

CRITICAL: This module MUST NOT import Qt. It runs headless, before
QApplication exists.
"""

import os
import re
import shutil
import subprocess
import sys


def resolve_ngspice() -> str:
    """Resolve ngspice path with priority:

    1. ``PQWAVE_NGSPICE`` environment variable
    2. ``ApplicationState().tool_paths.get("ngspice", "")``
    3. ``shutil.which("ngspice")``
    4. Raise ``FileNotFoundError``

    This is intentionally self-contained (not delegated to
    :func:`pqwave.bridge.schem_bridge.resolve_ngspice`) so that the
    headless wrapper can add ``PQWAVE_NGSPICE`` without pulling in
    the bridge package's import graph.
    """
    env_path = os.environ.get("PQWAVE_NGSPICE", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    configured = state.tool_paths.get("ngspice", "")
    if configured and os.path.isfile(configured):
        return configured

    found = shutil.which("ngspice")
    if found:
        return found

    raise FileNotFoundError(
        "ngspice not found. Install ngspice or set PQWAVE_NGSPICE "
        "environment variable."
    )


_SCHEMATIC_LINE_RE = re.compile(
    r"^\*\s*Qucs\s+\S+\s+(.+\.sch)\s*$"
)


def extract_schematic_path(netlist_path: str) -> tuple | None:
    """Parse the first line of a Qucs-S netlist for the schematic path.

    Expected format::

        * Qucs 0.0.24  /home/user/projects/bridge.sch

    Returns ``(sch_dir, sch_basename)`` where *sch_basename* is the
    filename without the ``.sch`` extension, or ``None`` if the header
    line is missing or unparseable.
    """
    try:
        with open(netlist_path, "r", encoding="utf-8", errors="replace") as fh:
            first_line = fh.readline().rstrip("\n")
    except OSError:
        return None

    match = _SCHEMATIC_LINE_RE.match(first_line)
    if not match:
        return None

    sch_path = match.group(1).strip()
    sch_dir = os.path.dirname(sch_path)
    sch_basename = os.path.splitext(os.path.basename(sch_path))[0]
    return (sch_dir, sch_basename)


_OUTPUT_FILE_RE = re.compile(r"^spice4qucs\.[^.].*$")


def _is_spice4qucs_output(entry_name: str) -> bool:
    """Return True if *entry_name* is a spice4qucs output file (not a dir)."""
    return bool(_OUTPUT_FILE_RE.match(entry_name))


def find_output_files(workdir: str) -> list[str]:
    """Glob *workdir* for files matching ``spice4qucs.*``.

    Returns absolute paths sorted alphabetically.  Directories and the
    bare ``spice4qucs`` prefix without an extension are excluded.
    """
    try:
        entries = os.listdir(workdir)
    except OSError:
        return []

    files = []
    for name in entries:
        if not _is_spice4qucs_output(name):
            continue
        full = os.path.join(workdir, name)
        if os.path.isfile(full):
            files.append(full)

    files.sort()
    return files


def copy_output_files(
    files: list[str], sim_dir: str, basename: str
) -> list[str]:
    """Copy output files to *sim_dir*, renaming the prefix.

    Each file ``spice4qucs.<rest>`` is renamed to ``<basename>.<rest>``
    and copied into *sim_dir* via :func:`shutil.copy2`.  The destination
    directory is created if it does not exist.

    Files that already exist in the destination with a newer or equal
    modification time are skipped (preserves already-copied results).

    Returns the list of destination paths for the files that were
    actually copied.
    """
    os.makedirs(sim_dir, exist_ok=True)

    # Build mapping from src to dst, renaming the prefix
    renamed: dict[str, str] = {}
    for src in files:
        fname = os.path.basename(src)
        rest = fname[len("spice4qucs"):]  # e.g. ".tran1.plot"
        if rest.startswith("."):
            rest = rest[1:]  # strip the leading dot
        dst_name = f"{basename}.{rest}" if rest else basename
        dst = os.path.join(sim_dir, dst_name)
        renamed[src] = dst

    copied: list[str] = []
    for src, dst in sorted(renamed.items()):
        # Skip only when the destination is strictly newer — same size
        # does not guarantee identical content (e.g. same-length runs).
        if os.path.isfile(dst):
            try:
                if os.path.getmtime(dst) >= os.path.getmtime(src):
                    continue
            except OSError:
                pass

        shutil.copy2(src, dst)
        copied.append(dst)

    return copied


class QucsBridgeRunner:
    """Orchestrator for the Qucs-S post-simulation pipeline.

    Parameters:
        ngspice_path: Path to the ngspice binary.  If empty,
            :func:`resolve_ngspice` is called at run time.
        auto_open: When ``True`` (the default), the pqwave GUI is
            launched after successful simulation.  Set to ``False`` via
            the ``PQWAVE_QUCS_AUTO_OPEN=0`` environment variable to
            suppress the GUI launch.
    """

    def __init__(self, ngspice_path: str = "", auto_open: bool = True):
        self._ngspice_path = ngspice_path
        env_auto_open = os.environ.get("PQWAVE_QUCS_AUTO_OPEN", "")
        if env_auto_open == "0":
            auto_open = False
        self._auto_open = auto_open

    def run(self, workdir: str, netlist_name: str) -> int:
        """Run the full pipeline.

        Returns:
            Exit code: 0 on success.
        """
        # 1. Resolve ngspice path
        ngspice = self._ngspice_path or resolve_ngspice()

        # 2. Run ngspice -b <netlist_name> in workdir
        proc = subprocess.run(
            [ngspice, "-b", netlist_name],
            cwd=workdir,
            capture_output=True,
            text=True,
        )

        # 3. If ngspice fails, return its exit code (no post-processing)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            sys.stderr.write(proc.stdout)
            return proc.returncode

        netlist_path = os.path.join(workdir, netlist_name)

        # 4. Extract schematic path from netlist
        result = extract_schematic_path(netlist_path)
        if result is None:
            # No schematic path found — copy to CWD/simulation/ with
            # original file names (no renaming).  Never launch pqwave
            # in this case (we don't know where the user wants it).
            sys.stderr.write(
                "qucs-bridge: netlist header lacks schematic path; "
                "copying outputs to simulation/ in working directory\n"
            )
            output_files = find_output_files(workdir)
            sim_dir = os.path.join(workdir, "simulation")
            copy_output_files(output_files, sim_dir, "spice4qucs")
            return 0

        sch_dir, sch_basename = result
        sim_dir = os.path.join(sch_dir, "simulation")

        return self._copy_and_maybe_launch(workdir, sim_dir, sch_basename)

    # Extensions that pqwave can open as waveform data.
    # .plot and .raw are both standard SPICE raw binary format (ngspice
    # "write" command).  .prn is ASCII "print" output (DC op / scalars)
    # — not useful as a waveform, so it's excluded here.
    _WAVEFORM_EXTENSIONS = {".raw", ".plot"}

    def _copy_and_maybe_launch(
        self, workdir: str, sim_dir: str, basename: str
    ) -> int:
        """Find outputs, copy them, and (optionally) launch pqwave GUI."""
        # 5. Find output files
        output_files = find_output_files(workdir)

        # 6. Copy to <sim_dir>/ with renamed basename
        copied = copy_output_files(output_files, sim_dir, basename)

        if not copied:
            # No files copied; still exit 0 — ngspice succeeded
            return 0

        # 7. Launch pqwave GUI detached (if auto_open is True).
        #    Only pass waveform data files — netlists (.cir) and configs
        #    (.cfg) are not raw data that pqwave can open.
        if self._auto_open:
            data_files = [
                f for f in copied
                if os.path.splitext(f)[1] in self._WAVEFORM_EXTENSIONS
            ]
            if data_files:
                return self._launch_pqwave(data_files)

        return 0

    @staticmethod
    def _launch_pqwave(copied_files: list[str]) -> int:
        """Launch the pqwave GUI as a detached subprocess."""
        cmd = [sys.executable, "-m", "pqwave.main"] + copied_files
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
                "qucs-bridge: pqwave not found on PATH; "
                "simulation output was saved but viewer could not be launched\n"
            )
        except OSError as exc:
            sys.stderr.write(
                f"qucs-bridge: failed to launch pqwave: {exc}\n"
            )
        return 0


def main() -> int:
    """Entry point for ``pqwave --qucs-bridge``."""
    if len(sys.argv) < 2:
        print(
            "Usage: pqwave --qucs-bridge <netlist.cir>",
            file=sys.stderr,
        )
        return 1

    netlist_name = sys.argv[1]
    workdir = os.getcwd()

    runner = QucsBridgeRunner()
    return runner.run(workdir, netlist_name)


if __name__ == "__main__":
    sys.exit(main())
