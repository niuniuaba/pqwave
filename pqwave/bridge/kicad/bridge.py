"""KiCad-specific SchematicBridge implementation."""

import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix
from pqwave.bridge.kicad.fixes import StripSlashes, FixDiodePins, FixBJTPins, MoveControlBlock
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState


class KiCadBridge(SchematicBridge):
    """SchematicBridge for KiCad Eeschema.

    Uses kicad-cli for netlist export, ngspice for simulation, and KiCad's
    built-in cross-probe server (port 4243) for back-annotation.

    Tool detection follows the same pattern as FstAdapter._resolve_tool()
    and GhwAdapter._resolve_tool(): shutil.which() with tool_paths override.
    """

    def __init__(self, kicad_cli_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._kicad_cli = kicad_cli_path
        self._ngspice = ngspice_path

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .kicad_sch file via kicad-cli."""
        kicad_cli = self._resolve_kicad_cli()

        fd, tmp_path = tempfile.mkstemp(suffix=".cir", prefix="pqwave_kicad_")
        os.close(fd)
        try:
            result = subprocess.run(
                [kicad_cli, "sch", "export", "netlist", "--format", "spice",
                 "-o", tmp_path, sch_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"kicad-cli failed with code {result.returncode}: {result.stderr}"
                )
            with open(tmp_path, "r") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def get_netlist_fixes(self) -> list[NetlistFix]:
        """Return KiCad-specific fixes in the correct order."""
        return [StripSlashes(), FixDiodePins(), FixBJTPins(), MoveControlBlock()]

    def probe_net(self, net_name: str) -> None:
        self._ensure_cross_probe().probe_net(net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        self._ensure_cross_probe().probe_part(ref, pin)

    def clear_probe(self) -> None:
        self._ensure_cross_probe().clear()

    def detect_tool(self) -> Optional[str]:
        try:
            return self._resolve_kicad_cli()
        except FileNotFoundError:
            return None

    def is_tool_running(self) -> bool:
        """Check if a KiCad process is running via pgrep or pidof."""
        for cmd in (["pgrep", "-x", "kicad"], ["pidof", "kicad"]):
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
        return [".kicad_sch"]

    # ---- Simulation pipeline ----

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        """Run the full pipeline: export → post-process → ngspice → .raw.

        Returns a dict with keys:
          returncode, stdout, stderr, raw_file, netlist, fix_info
        """
        netlist = self.export_netlist(sch_path)
        context = self._build_context(sch_path)

        processor = NetlistPostProcessor(self.get_netlist_fixes())
        fix_info = [
            entry["detail"]
            for entry in processor.dry_run(netlist, context)
        ]
        fixed = processor.process(netlist, context)

        fd, cir_path = tempfile.mkstemp(suffix=".cir", prefix="pqwave_kicad_")
        os.close(fd)
        try:
            with open(cir_path, "w") as f:
                f.write(fixed)

            if raw_output is None:
                fd, raw_output = tempfile.mkstemp(
                    suffix=".raw", prefix="pqwave_kicad_"
                )
                os.close(fd)
                os.unlink(raw_output)  # ngspice -r creates the file fresh

            ngspice = self._resolve_ngspice()
            result = subprocess.run(
                [ngspice, "-b", "-r", raw_output, cir_path],
                capture_output=True, text=True, timeout=300,
            )
            raw_ok = result.returncode == 0 and os.path.exists(raw_output)
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "raw_file": raw_output if raw_ok else None,
                "netlist": fixed,
                "fix_info": fix_info,
            }
        finally:
            try:
                os.unlink(cir_path)
            except OSError:
                pass

    # ---- Sim.Pins extraction ----

    def _build_context(self, sch_path: str) -> dict:
        """Build the context dict for NetlistFix.apply()."""
        return {"sim_pins": self.extract_sim_pins(sch_path)}

    def extract_sim_pins(self, sch_path: str) -> dict[str, dict[str, str]]:
        """Parse Sim.Pins from a .kicad_sch S-expression file.

        Returns a dict mapping reference designators to pin mappings:
          {"Q1": {"1": "E", "2": "B", "3": "C"}, ...}
        """
        try:
            with open(sch_path, "r") as f:
                content = f.read()
        except OSError:
            return {}

        result = {}
        symbol_blocks = re.findall(
            r"\(\s*symbol\b.*?\(\s*pin\b", content, re.DOTALL
        )
        for block in symbol_blocks:
            ref_m = re.search(r'\(\s*property\s+"Reference"\s+"(\S+)"', block)
            pins_m = re.search(r'\(\s*property\s+"Sim\.Pins"\s+"([^"]+)"', block)
            if ref_m and pins_m:
                ref = ref_m.group(1)
                sim_pins = self._parse_sim_pins_value(pins_m.group(1))
                if sim_pins:
                    result[ref] = sim_pins
        return result

    def _parse_sim_pins_value(self, text: str) -> dict[str, str]:
        """Parse a Sim.Pins value string like "1=K 2=A" into a dict."""
        result = {}
        for part in text.split():
            if "=" in part:
                pin_num, pin_name = part.split("=", 1)
                result[pin_num.strip()] = pin_name.strip()
        return result

    # ---- Tool resolution ----

    def _resolve_kicad_cli(self) -> str:
        # Priority: constructor arg > settings > PATH
        if self._kicad_cli and os.path.isfile(self._kicad_cli):
            return self._kicad_cli
        state = ApplicationState()
        custom = state.tool_paths.get("kicad_cli", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("kicad-cli")
        if found:
            return found
        raise FileNotFoundError(
            "kicad-cli not found. Install KiCad 8.0+ or set the path in "
            "Settings > External Converter Paths."
        )

    def _resolve_ngspice(self) -> str:
        if self._ngspice and os.path.isfile(self._ngspice):
            return self._ngspice
        state = ApplicationState()
        custom = state.tool_paths.get("ngspice", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("ngspice")
        if found:
            return found
        raise FileNotFoundError(
            "ngspice not found. Install ngspice or set the path in "
            "Settings > External Converter Paths."
        )

    def _ensure_cross_probe(self):
        """Lazy-import CrossProbeClient to avoid circular dependencies."""
        from pqwave.bridge.kicad.cross_probe import CrossProbeClient

        if not hasattr(self, "_cross_probe") or self._cross_probe is None:
            self._cross_probe = CrossProbeClient()
        return self._cross_probe
