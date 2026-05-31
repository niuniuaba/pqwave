"""Xschem-specific SchematicBridge implementation."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix, resolve_ngspice
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState


class XschemBridge(SchematicBridge):
    """SchematicBridge for xschem.

    Uses xschem -n -s -q --quit for netlist export and ngspice for
    simulation. Cross-probe is handled by XschemCrossProbeClient
    communicating with pqwave-server.tcl running inside xschem.
    Wave push (Alt+G) is handled by WaveReceiver on port 2026.
    """

    def __init__(self, xschem_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._xschem = xschem_path
        self._ngspice = ngspice_path

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .sch file via xschem CLI."""
        xschem_bin = self._resolve_xschem()
        sch_dir = os.path.dirname(os.path.abspath(sch_path))
        sch_basename = os.path.splitext(os.path.basename(sch_path))[0]

        result = subprocess.run(
            [xschem_bin, "-n", "-s", "-q", "--quit",
             "--netlist_type", "spice", sch_path],
            capture_output=True, text=True, timeout=30,
            cwd=sch_dir,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"xschem failed with code {result.returncode}: {result.stderr}"
            )

        # xschem writes to netlist_dir/<basename>.spice
        netlist_dir = os.path.join(os.path.expanduser("~"), ".xschem", "simulations")
        spice_path = os.path.join(netlist_dir, f"{sch_basename}.spice")
        if os.path.exists(spice_path):
            with open(spice_path, "r") as f:
                return f.read()
        # Fallback: try same dir as schematic
        alt_path = os.path.join(sch_dir, "simulation", f"{sch_basename}.spice")
        if os.path.exists(alt_path):
            with open(alt_path, "r") as f:
                return f.read()
        # Last fallback: ngspice netlist name
        alt_path2 = os.path.join(sch_dir, f"{sch_basename}.spice")
        if os.path.exists(alt_path2):
            with open(alt_path2, "r") as f:
                return f.read()
        raise RuntimeError(
            f"xschem ran but no .spice file found. "
            f"Tried: {spice_path}, {alt_path}, {alt_path2}"
        )

    def get_netlist_fixes(self) -> list[NetlistFix]:
        """Xschem SPICE output is clean — no fixes needed."""
        return []

    def probe_net(self, net_name: str) -> None:
        self._ensure_cross_probe().probe_net(net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        cp = self._ensure_cross_probe()
        cp.probe_part(ref, pin)

    def clear_probe(self) -> None:
        self._ensure_cross_probe().clear()

    def detect_tool(self) -> Optional[str]:
        try:
            return self._resolve_xschem()
        except FileNotFoundError:
            return None

    def is_tool_running(self) -> bool:
        for cmd in (["pgrep", "-x", "xschem"], ["pidof", "xschem"]):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return False

    def get_watch_extensions(self) -> list[str]:
        return [".sch"]

    # ---- Simulation pipeline ----

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        """Run full pipeline: export → post-process → ngspice → .raw."""
        netlist = self.export_netlist(sch_path)
        processor = NetlistPostProcessor(self.get_netlist_fixes())
        fixed = processor.process(netlist)

        fd, cir_path = tempfile.mkstemp(suffix=".cir", prefix="pqwave_xschem_")
        os.close(fd)
        try:
            with open(cir_path, "w") as f:
                f.write(fixed)
            if raw_output is None:
                fd, raw_output = tempfile.mkstemp(
                    suffix=".raw", prefix="pqwave_xschem_"
                )
                os.close(fd)
                os.unlink(raw_output)
            ngspice = self._resolve_ngspice()
            result = subprocess.run(
                [ngspice, "-b", "-r", raw_output, cir_path],
                capture_output=True, text=True, timeout=300,
                cwd=os.path.dirname(os.path.abspath(sch_path)),
            )
            raw_ok = result.returncode == 0 and os.path.exists(raw_output)
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "raw_file": raw_output if raw_ok else None,
                "netlist": fixed,
                "fix_info": [],
            }
        finally:
            try:
                os.unlink(cir_path)
            except OSError:
                pass

    # ---- Tool resolution ----

    def _resolve_xschem(self) -> str:
        if self._xschem and os.path.isfile(self._xschem):
            return self._xschem
        state = ApplicationState()
        custom = state.tool_paths.get("xschem", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("xschem")
        if found:
            return found
        raise FileNotFoundError(
            "xschem not found. Install xschem or set the path in "
            "Settings > External Converter Paths."
        )

    def _resolve_ngspice(self) -> str:
        return resolve_ngspice(self._ngspice)

    def _ensure_cross_probe(self):
        from pqwave.bridge.xschem.cross_probe import XschemCrossProbeClient
        if not hasattr(self, "_cross_probe") or self._cross_probe is None:
            self._cross_probe = XschemCrossProbeClient()
        return self._cross_probe
