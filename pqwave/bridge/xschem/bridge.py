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
        self._cross_probe = None  # lazily instantiated in _ensure_cross_probe()

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .sch file via xschem CLI.

        Uses a temporary directory as netlist_dir (set via --tcl) so we
        always know exactly where the output .spice file lands, regardless
        of the user's xschemrc netlist_dir configuration.
        """
        xschem_bin = self._resolve_xschem()
        sch_dir = os.path.dirname(os.path.abspath(sch_path))
        sch_basename = os.path.splitext(os.path.basename(sch_path))[0]

        # Create a temp dir for netlist output so we control the output path.
        # This avoids fragility from guessing ~/.xschem/simulations/ or
        # schematic-relative paths — xschemrc may override netlist_dir.
        temp_netlist_dir = tempfile.mkdtemp(prefix="pqwave_xschem_nl_")
        try:
            # --tcl runs before file load and netlist, overriding netlist_dir
            result = subprocess.run(
                [xschem_bin, "--tcl",
                 f"set netlist_dir {temp_netlist_dir}",
                 "-n", "-s", "-q", "--quit",
                 "--netlist_type", "spice", sch_path],
                capture_output=True, text=True, timeout=30,
                cwd=sch_dir,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"xschem failed with code {result.returncode}: {result.stderr}"
                )

            spice_path = os.path.join(temp_netlist_dir, f"{sch_basename}.spice")
            if os.path.exists(spice_path):
                with open(spice_path, "r") as f:
                    netlist = f.read()
                # Clean up temp files on success path
                try:
                    os.unlink(spice_path)
                    os.rmdir(temp_netlist_dir)
                except OSError:
                    pass
                return netlist
            raise RuntimeError(
                f"xschem ran but no .spice file found at {spice_path}. "
                f"stderr: {result.stderr}"
            )
        finally:
            # Ensure temp dir is cleaned up on error paths too
            try:
                netlist_dir_path = temp_netlist_dir
                if os.path.exists(netlist_dir_path):
                    for f in os.listdir(netlist_dir_path):
                        os.unlink(os.path.join(netlist_dir_path, f))
                    os.rmdir(netlist_dir_path)
            except OSError:
                pass

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
        # Try process-based detection first (pgrep / pidof).
        for cmd in (["pgrep", "-x", "xschem"], ["pidof", "xschem"]):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        # Fallback: check if the cross-probe TCP port is accepting connections.
        # This also works in containers / restricted shells where pgrep/pidof
        # are unavailable.
        import socket as _socket
        state = ApplicationState()
        cp_config = getattr(state, "_xschem_config", {})
        port = cp_config.get("cross_probe_port", 2021)
        try:
            sock = _socket.create_connection(
                ("localhost", port), timeout=0.5
            )
            sock.close()
            return True
        except (OSError, _socket.timeout):
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
        if self._cross_probe is None:
            self._cross_probe = XschemCrossProbeClient()
        return self._cross_probe
