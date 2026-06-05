"""Lepton-EDA SchematicBridge implementation."""

import os
import shutil
import subprocess
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix, resolve_ngspice
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState


class LeptonBridge(SchematicBridge):
    """SchematicBridge for lepton-eda.

    Uses lepton-netlist -g spice-sdb for netlist export and ngspice
    for simulation. Cross-probe and back-annotation are handled by
    LeptonCrossProbeClient communicating with pqwave-server.scm running
    inside lepton-schematic.
    """

    def __init__(self, lepton_netlist_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._lepton_netlist = lepton_netlist_path
        self._ngspice = ngspice_path

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .sch file via lepton-netlist."""
        lepton_netlist = self._resolve_lepton_netlist()
        result = subprocess.run(
            [lepton_netlist, "-g", "spice-sdb", "-o", "-", sch_path],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.abspath(sch_path)),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"lepton-netlist failed with code {result.returncode}: {result.stderr}"
            )
        return result.stdout

    def get_netlist_fixes(self) -> list[NetlistFix]:
        """Lepton-eda spice-sdb backend produces clean SPICE -- no fixes needed."""
        return []

    def probe_net(self, net_name: str) -> None:
        self._ensure_cross_probe().probe_net(net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        self._ensure_cross_probe().probe_part(ref, pin)

    def clear_probe(self) -> None:
        self._ensure_cross_probe().clear()

    def detect_tool(self) -> Optional[str]:
        try:
            return self._resolve_lepton_netlist()
        except FileNotFoundError:
            return None

    def is_tool_running(self) -> bool:
        for cmd in (["pgrep", "-x", "lepton-schematic"], ["pidof", "lepton-schematic"]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return False

    def get_watch_extensions(self) -> list[str]:
        return [".sch"]

    # ---- Simulation pipeline ----

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        """Run full pipeline: export -> post-process -> ngspice -> .raw.

        Places netlist and .raw output alongside the schematic in a
        ``simulation/`` subdirectory, matching xschem's behaviour.
        """
        # Clear floating labels before export so they don't interfere.
        self._ensure_cross_probe().send_command("$CLEAR:ANNOTATIONS")

        netlist = self.export_netlist(sch_path)
        processor = NetlistPostProcessor(self.get_netlist_fixes())
        fixed = processor.process(netlist)

        sch_dir = os.path.dirname(os.path.abspath(sch_path))
        sim_dir = os.path.join(sch_dir, "simulation")
        os.makedirs(sim_dir, exist_ok=True)

        basename = os.path.splitext(os.path.basename(sch_path))[0]
        cir_path = os.path.join(sim_dir, f"{basename}.cir")
        if raw_output is None:
            raw_output = os.path.join(sim_dir, f"{basename}.raw")
            # Remove stale file so ngspice creates it fresh.
            try:
                os.unlink(raw_output)
            except OSError:
                pass

        with open(cir_path, "w") as f:
            f.write(fixed)

        ngspice = self._resolve_ngspice()
        result = subprocess.run(
            [ngspice, "-b", "-r", raw_output, cir_path],
            capture_output=True, text=True, timeout=300,
            cwd=sch_dir,
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

    # ---- Back-annotation methods ----

    def annotate_dc(self, voltages: dict[str, float]) -> None:
        cp = self._ensure_cross_probe()
        for netname, voltage in voltages.items():
            cp.send_command(f"$ANNOTATE:DC {netname} {voltage}")

    def annotate_label(self, netname: str, text: str, x: int, y: int) -> None:
        cp = self._ensure_cross_probe()
        cp.send_command(f"$ANNOTATE:LABEL|{netname}|{text}|{x}|{y}")

    def clear_annotations(self) -> None:
        self._ensure_cross_probe().send_command("$CLEAR:ANNOTATIONS")

    def clear_dc_stamps(self) -> None:
        self._ensure_cross_probe().send_command("$CLEAR:DC")

    # ---- Tool resolution ----

    def _resolve_lepton_netlist(self) -> str:
        if self._lepton_netlist and os.path.isfile(self._lepton_netlist):
            return self._lepton_netlist
        state = ApplicationState()
        custom = state.tool_paths.get("lepton_netlist", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("lepton-netlist")
        if found:
            return found
        raise FileNotFoundError(
            "lepton-netlist not found. Install lepton-eda or set the path in "
            "Settings > External Converter Paths."
        )

    def _resolve_ngspice(self) -> str:
        return resolve_ngspice(self._ngspice)

    def _ensure_cross_probe(self):
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        if not hasattr(self, "_cross_probe") or self._cross_probe is None:
            self._cross_probe = LeptonCrossProbeClient()
        return self._cross_probe
