"""KiCad-specific SchematicBridge implementation."""

import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix, resolve_ngspice
from pqwave.bridge.kicad.fixes import StripSlashes, FixDiodePins, FixBJTPins, MoveControlBlock
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState


class KiCadBridge(SchematicBridge):
    """SchematicBridge for KiCad Eeschema.

    Uses kicad-cli for netlist export and ngspice for simulation.
    Cross-probe back-annotation requires KiCad's schematic IPC API
    (selection/action handlers — not yet available in KiCad 10.99.0).

    Tool detection follows the same pattern as FstAdapter._resolve_tool()
    and GhwAdapter._resolve_tool(): shutil.which() with tool_paths override.
    """

    def __init__(self, kicad_cli_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._kicad_cli = kicad_cli_path
        self._ngspice = ngspice_path
        self._ipc_probe = None       # IpcProbeClient, lazy-created
        self._suppress_ipc_poll = False  # guard against feedback loop
        self._last_sel_ids: set | None = None  # for poll_selection()

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
        """Cross-probe: highlight a net in KiCad Eeschema via IPC API."""
        self._suppress_ipc_poll = True
        try:
            probe = self._get_ipc_probe()
            if probe:
                probe.probe_net(net_name)
        finally:
            self._suppress_ipc_poll = False

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        """Cross-probe: highlight a component in KiCad Eeschema via IPC API."""
        self._suppress_ipc_poll = True
        try:
            probe = self._get_ipc_probe()
            if probe:
                probe.probe_part(ref, pin)
        finally:
            self._suppress_ipc_poll = False

    def clear_probe(self) -> None:
        """Clear all cross-probe highlights via IPC API."""
        probe = self._get_ipc_probe()
        if probe:
            probe.clear()

    def _get_ipc_probe(self):
        """Get or create an IpcProbeClient connected to the running KiCad.

        Caches the client for reuse.  On re-watch, the old client is
        disconnected before creating a new one.
        """
        if self._ipc_probe is not None:
            if self._ipc_probe.is_connected():
                return self._ipc_probe
            self._ipc_probe.disconnect()
            self._ipc_probe = None

        try:
            import kipy
        except ImportError:
            return None

        socket_path = os.environ.get("KICAD_API_SOCKET", "/tmp/kicad/api.sock")
        if not socket_path.startswith("ipc://"):
            socket_path = f"ipc://{socket_path}"

        try:
            kicad = kipy.KiCad(socket_path=socket_path, timeout_ms=3000)
            from pqwave.bridge.kicad.cross_probe import IpcProbeClient
            probe = IpcProbeClient()
            probe.set_kicad(kicad)
            self._ipc_probe = probe
            return probe
        except Exception:
            return None

    def poll_selection(self) -> list[str]:
        """Poll Eeschema selection and return newly selected net names.

        Returns a list of net names that are currently selected in
        Eeschema.  Returns an empty list if nothing is selected, IPC
        is unavailable, or the selection hasn't changed since the
        last poll.  The caller is responsible for mapping net names
        to pqwave traces.
        """
        probe = self._get_ipc_probe()
        if probe is None or not probe.is_connected():
            return []

        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                GetSelection, SelectionResponse,
            )
            from kipy.proto.common.types import (
                ItemHeader, DocumentSpecifier, DocumentType,
            )

            doc = DocumentSpecifier()
            doc.type = DocumentType.DOCTYPE_SCHEMATIC
            hdr = ItemHeader()
            hdr.document.CopyFrom(doc)
            req = GetSelection()
            req.header.CopyFrom(hdr)
            resp = probe._kicad._client.send(req, SelectionResponse)

            current_ids = {item.value for item in resp.items
                          if hasattr(item, 'value')}
            if not current_ids or current_ids == self._last_sel_ids:
                self._last_sel_ids = current_ids
                return []

            self._last_sel_ids = current_ids
            sch = probe._kicad.get_schematic()
            netlist = sch.get_netlist()

            result = []
            for net in netlist:
                net_ids = set()
                for sheet in net.sheets:
                    for item in sheet.items:
                        net_ids.add(item.value)
                if net_ids & current_ids:
                    result.append(net.name)
            return result

        except (OSError, ConnectionError, TimeoutError):
            return []
        except Exception:
            import logging
            _log = logging.getLogger(__name__)
            _log.warning("KiCad selection poll failed", exc_info=True)
            return []

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
        return resolve_ngspice(self._ngspice)
