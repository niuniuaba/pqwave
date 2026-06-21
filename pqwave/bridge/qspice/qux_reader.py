"""QUX-based .qraw reader — official QSPICE data extraction.

Uses QSPICE's own ``QUX.exe -Export`` tool to extract simulation data
from .qraw files as properly-decoded CSV.  This avoids all encoding
issues present in spicelib's binary parser (no CP1252 mapping needed).

When QSPICE is not installed, callers fall back to spicelib transparently.

CRITICAL: This module MUST NOT import Qt.  It may run headless.
"""

import os
import re
import sys
import shutil
import subprocess

import numpy as np

from pqwave.logging_config import get_logger

logger = get_logger(__name__)

# Nline for metadata-only SPICE calls — need enough points so QUX reports
# accurate plot type info, but not so many that it's slow.
_META_NLINE = 10


def _build_qux_cmd(qux_path: str, qraw_path: str, probes: str,
                   nline: int, fmt: str) -> list:
    """Build the command list for invoking QUX.exe."""
    if sys.platform == "win32":
        return [qux_path, "-Export", qraw_path, probes,
                str(nline), fmt, "-stdout"]
    else:
        wine = shutil.which("wine")
        if not wine:
            return None
        return [wine, qux_path, "-Export", qraw_path, probes,
                str(nline), fmt, "-stdout"]


def _parse_spice_metadata(stdout: str) -> dict:
    """Parse QUX SPICE-format metadata output.

    Returns dict with keys: n_points, plotname, x_label, is_ac,
    is_complex, x_min, x_max, step_count.  Returns empty dict on
    parse failure.
    """
    meta: dict = {}
    flgv = 0

    for line in stdout.splitlines():
        line = line.rstrip("\r")
        if not line:
            continue

        if line.startswith("Values:"):
            break

        if line.startswith("No. Points:"):
            m = re.match(r"^No\. Points:\s*(\d+)", line)
            if m:
                meta["n_points"] = int(m.group(1))

        elif line.startswith("Plotname:"):
            pn = re.match(r"^Plotname:\s+(\S.*)$", line)
            if pn:
                meta["plotname"] = pn.group(1).strip()

        elif line.startswith("Abscissa:"):
            m = re.match(r"^Abscissa:\s+(\S+)\s+(\S+)", line)
            if m:
                meta["x_min"] = float(m.group(1))
                meta["x_max"] = float(m.group(2))

        elif line.startswith("Flags:"):
            flags = re.match(r"^Flags:\s+(\S.*)$", line)
            if flags:
                meta["flags"] = flags.group(1).strip()

        elif line.startswith("Variables:"):
            flgv = 1

        elif flgv == 1:
            # First variable line after Variables: carries X-axis info for DC/OP
            m = re.match(r"^\s*(\S+)\s+(\S+)\s+(\S+)", line)
            if m:
                x_name = m.group(2)
                meta.setdefault("x_label", x_name)
            flgv = 0

    # Determine analysis type
    pn = meta.get("plotname", "").lower()
    flags = meta.get("flags", "").lower()
    meta["is_ac"] = pn.startswith("ac")
    meta["is_complex"] = meta["is_ac"] or "complex" in flags

    # Derive X-axis label
    if "x_label" not in meta:
        if pn.startswith("tran"):
            meta["x_label"] = "Time"
        elif pn.startswith("ac"):
            meta["x_label"] = "Freq"
        elif pn.startswith("dc"):
            meta["x_label"] = "DC"
        elif pn.startswith("oper"):
            meta["x_label"] = "OP"

    # Step count — refined later by _extract_step_info() via header parse
    meta["step_count"] = 1 if meta.get("n_points", 0) > 0 else 0

    return meta


def _parse_csv_data(stdout: str, var_names: list, is_complex: bool) -> np.ndarray:
    """Parse QUX CSV-format data output into a numpy array.

    AC analysis: tab-separated, complex values like "1.23-4.56j".
    Transient/DC/OP: comma-separated, real float values.

    Returns (n_points, n_vars) float32 or complex64 array.
    On parse failure, returns empty array.
    """
    try:
        text = stdout.strip()
        if not text:
            return np.array([])

        lines = text.splitlines()

        # QUX CSV output has a header line with quoted column names
        if lines and lines[0].startswith('"'):
            lines = lines[1:]

        n_vars = len(var_names)
        n_points = len(lines)

        if n_points == 0 or n_vars == 0:
            return np.array([])

        sep = "\t" if is_complex else ","
        dtype = np.complex64 if is_complex else np.float32
        data = np.zeros((n_points, n_vars), dtype=dtype)

        # QUX CSV has an X-axis column at index 0, followed by the
        # requested probes at indices 1..n_vars.  Skip column 0.
        col_offset = 1

        if is_complex:
            _has_sign = re.compile(r".\d[-+]")
            for i, line in enumerate(lines):
                parts = line.split(sep)
                for j in range(min(n_vars, len(parts) - col_offset)):
                    val = parts[j + col_offset].strip()
                    if not val:
                        continue
                    if _has_sign.search(val):
                        normalized = val.replace(",-", "-").replace(",", "+")
                        try:
                            data[i, j] = complex(normalized + "j")
                        except ValueError:
                            data[i, j] = complex(0, 0)
                    else:
                        try:
                            data[i, j] = complex(float(val), 0)
                        except ValueError:
                            data[i, j] = complex(0, 0)
        else:
            for i, line in enumerate(lines):
                parts = line.split(sep)
                for j in range(min(n_vars, len(parts) - col_offset)):
                    try:
                        data[i, j] = float(parts[j + col_offset].strip())
                    except ValueError:
                        data[i, j] = 0.0

        return data

    except Exception:
        logger.warning("Failed to parse QUX CSV data", exc_info=True)
        return np.array([])


def load_qraw_via_qux(filepath: str, var_names: list,
                      total_points: int = 0):
    """Try to load .qraw data via QUX.exe -Export.

    Args:
        filepath: Path to the .qraw file.
        var_names: List of variable names to extract (from header parse).
        total_points: Actual point count from the file header (No. Points
            line).  Used for the data-export Nline so QUX returns every
            point.  If 0, falls back to a large fixed Nline.

    Returns:
        ``(data, metadata)`` on success where *data* is a 2-D numpy
        array (n_points, n_vars) and *metadata* is a dict with keys
        ``plotname``, ``flags``, ``is_ac``, ``is_complex``,
        ``x_label``, ``n_points``, ``step_count``.

        ``None`` if QUX is not available or extraction fails.
    """
    from pqwave.bridge.qspice.wrapper import resolve_qux

    qux = resolve_qux()
    if not qux:
        logger.debug("QUX.exe not found — skipping QUX-based .qraw read")
        return None

    if not var_names:
        return None

    # Probe names are already Latin-1 strings preserving original CP1252
    # byte values (from _extract_raw_var_names in rawfile.py).
    probes = ",".join(var_names)

    # --- Step 1: metadata via SPICE format (minimal Nline — header only) ---
    cmd = _build_qux_cmd(qux, filepath, probes, _META_NLINE, "SPICE")
    if cmd is None:
        return None

    try:
        proc = subprocess.run(
            cmd, capture_output=True, encoding="latin-1", errors="replace", timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("QUX metadata call failed, falling back to spicelib: %s", exc)
        return None

    if proc.returncode != 0:
        logger.debug("QUX SPICE call exited %d: %s", proc.returncode,
                      proc.stderr[:200] if proc.stderr else "")
        return None

    meta = _parse_spice_metadata(proc.stdout)
    if not meta:
        return None

    # --- Step 2: data via CSV format ---
    # Use the actual point count from the file header (trustworthy), not
    # the metadata call's No. Points (which reports export count = Nline+1).
    if total_points > 0:
        nline = total_points - 1
    else:
        nline = 1_000_000  # fallback: generous but not absurd
        logger.warning(
            "No. Points unavailable from header; using fallback Nline=%d "
            "— data may be truncated for simulations with >%d points",
            nline, nline + 1,
        )

    cmd = _build_qux_cmd(qux, filepath, probes, nline, "CSV")
    if cmd is None:
        return None

    try:
        proc = subprocess.run(
            cmd, capture_output=True, encoding="latin-1", errors="replace", timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("QUX data call failed, falling back to spicelib: %s", exc)
        return None

    if proc.returncode != 0:
        logger.debug("QUX CSV call exited %d: %s", proc.returncode,
                      proc.stderr[:200] if proc.stderr else "")
        return None

    is_complex = meta.get("is_complex", False)
    data = _parse_csv_data(proc.stdout, var_names, is_complex)
    if data.size == 0:
        return None

    logger.info(
        "Loaded %s via QUX: %d points, %d vars, %s",
        os.path.basename(filepath),
        data.shape[0], data.shape[1],
        "complex" if is_complex else "real",
    )
    return data, meta
