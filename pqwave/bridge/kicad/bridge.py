"""KiCad-specific SchematicBridge implementation."""

import logging
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

_log = logging.getLogger(__name__)

_kipy_available = None  # None = unchecked, True/False = result


def _check_kipy_functionality() -> tuple[bool, str]:
    """Check if kipy has the APIs we need. Returns (ok, error_message)."""
    global _kipy_available
    try:
        import kipy
    except ImportError:
        _kipy_available = False
        return False, (
            "kicad-python is required for KiCad IPC API integration.\n"
            "Install it with:\n"
            "  pip install git+https://gitlab.com/kicad/code/kicad-python.git\n"
            "See: https://pypi.org/project/kicad-python/"
        )

    if not hasattr(kipy.KiCad, "get_schematic"):
        _kipy_available = False
        return False, (
            "Installed kicad-python lacks get_schematic().\n"
            "Install the latest version from Git:\n"
            "  pip install git+https://gitlab.com/kicad/code/kicad-python.git"
        )

    _kipy_available = True
    return True, ""


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

        # IPC API state (lazy-initialized)
        self._kipy_kicad = None       # kipy.KiCad instance
        self._ipc_failed = False      # True if IPC connection was attempted and failed
        self._ipc_available = None    # None = unchecked, True/False = result
        self._ipc_probe_client = None  # IpcProbeClient, lazy-initialized

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .kicad_sch file.

        Primary path: IPC API schematic.export_netlist(SNF_SPICE).
        Fallback path: kicad-cli sch export netlist --format spice.
        """
        # Try IPC path first
        try:
            if self._ensure_ipc():
                return self._export_netlist_via_ipc()
        except Exception as e:
            # Any IPC failure (kicad-python missing, connection dropped,
            # export failed, etc.) — fall through to kicad-cli
            _log.info("IPC API not available, using kicad-cli fallback: %s", e)

        # Fallback: kicad-cli subprocess
        return self._export_netlist_via_kicad_cli(sch_path)

    def _export_netlist_via_ipc(self) -> str:
        """Export netlist via IPC API schematic.export_netlist(SNF_SPICE)."""
        from kipy.proto.schematic import schematic_jobs_pb2

        fd, tmp_path = tempfile.mkstemp(suffix=".cir", prefix="pqwave_kicad_ipc_")
        os.close(fd)
        try:
            schematic = self._kipy_kicad.get_schematic()
            result = schematic.export_netlist(
                tmp_path, format=schematic_jobs_pb2.SNF_SPICE
            )
            if not result.succeeded:
                raise RuntimeError(f"IPC netlist export failed: {result}")

            # Read back the exported file
            output_path = result.output_path[0] if result.output_path else tmp_path
            with open(output_path, "r") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _export_netlist_via_kicad_cli(self, sch_path: str) -> str:
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
        """Cross-probe: highlight a net in the KiCad schematic via IPC API."""
        if not self._ensure_ipc():
            _log.warning(
                "Cross-probe unavailable — requires KiCad 10+ with IPC API enabled"
            )
            return
        self._ensure_ipc_probe_client().probe_net(net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        """Cross-probe: highlight a component or pin in the KiCad schematic."""
        if not self._ensure_ipc():
            _log.warning(
                "Cross-probe unavailable — requires KiCad 10+ with IPC API enabled"
            )
            return
        self._ensure_ipc_probe_client().probe_part(ref, pin)

    def clear_probe(self) -> None:
        """Clear all cross-probe highlights via IPC API."""
        if self._ipc_available:
            client = getattr(self, "_ipc_probe_client", None)
            if client:
                client.clear()
        else:
            _log.debug("No active IPC connection; nothing to clear")

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
        """Parse Sim.Pins from the schematic.

        Primary path: IPC API schematic.get_symbols() — structured objects.
        Fallback path: S-expression regex parsing of .kicad_sch file.
        """
        try:
            if self._ensure_ipc():
                return self._extract_sim_pins_ipc()
        except RuntimeError:
            _log.info("IPC not available for Sim.Pins, using regex fallback")

        return self._extract_sim_pins_regex(sch_path)

    def _extract_sim_pins_ipc(self) -> dict[str, dict[str, str]]:
        """Extract Sim.Pins from all symbols via IPC API.

        Returns a dict mapping reference designator → {pin_number: pin_name, ...}.
        Example: {"Q1": {"1": "E", "2": "B", "3": "C"}, "D1": {"1": "K", "2": "A"}}
        """
        schematic = self._kipy_kicad.get_schematic()
        symbols = schematic.get_symbols()

        result: dict[str, dict[str, str]] = {}
        for sym in symbols:
            # Get reference designator
            ref = None
            if sym.reference_field and sym.reference_field.text:
                ref = sym.reference_field.text

            if not ref:
                continue

            pin_map: dict[str, str] = {}
            if sym.definition:
                for child in sym.definition.items:
                    item = getattr(child, "item", None)
                    if item is None:
                        continue
                    number = getattr(item, "number", None)
                    name = getattr(item, "name", None)
                    if number is not None and name is not None:
                        pin_map[str(number)] = str(name)

            if pin_map:
                result[ref] = pin_map

        return result

    def _extract_sim_pins_regex(self, sch_path: str) -> dict[str, dict[str, str]]:
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

    def _ensure_ipc_probe_client(self):
        """Lazy-initialize the IpcProbeClient with the current KiCad instance.

        Lesson learned #6: disconnect old client before creating new one.
        """
        from pqwave.bridge.kicad.cross_probe import IpcProbeClient

        old = getattr(self, "_ipc_probe_client", None)
        if old is not None:
            old.disconnect()

        client = IpcProbeClient()
        client.set_kicad(self._kipy_kicad)
        self._ipc_probe_client = client
        return client

    # ---- IPC API connection ----

    def _ensure_ipc(self) -> bool:
        """Establish IPC connection to KiCad if not already connected.

        Returns True if IPC is available and connected.
        Returns False if IPC is unavailable (kicad-python missing, KiCad
        not running, API disabled, or required APIs absent).
        Caches the connection for reuse; reconnects if dropped.
        """
        # Already connected — verify liveness before reuse
        if self._kipy_kicad is not None and self._ipc_available:
            try:
                self._kipy_kicad.ping()
                return True
            except Exception:
                _log.debug("IPC connection lost, reconnecting...")
                self._kipy_kicad = None
                self._ipc_available = None
                # Fall through to reconnect logic below

        # Already tried and failed — don't retry in same session
        if self._ipc_failed:
            return False

        # Check kicad-python functionality
        global _kipy_available
        if _kipy_available is None:
            ok, msg = _check_kipy_functionality()
            if not ok:
                self._ipc_failed = True
                self._ipc_available = False
                raise RuntimeError(msg)

        if not _kipy_available:
            self._ipc_failed = True
            self._ipc_available = False
            raise RuntimeError(
                "kicad-python is not available for KiCad IPC API integration."
            )

        # Connect
        import kipy

        socket_path = os.environ.get("KICAD_API_SOCKET")
        if not socket_path:
            socket_path = os.path.join(tempfile.gettempdir(), "kicad", "api.sock")
        if not socket_path.startswith("ipc://"):
            socket_path = f"ipc://{socket_path}"

        try:
            self._kipy_kicad = kipy.KiCad(socket_path=socket_path, timeout_ms=5000)
            # Verify the API server is serving schematic data (confirms we're
            # connected to Eeschema, not just any KiCad instance)
            self._kipy_kicad.get_schematic()
            self._ipc_available = True
            self._ipc_failed = False
            return True
        except Exception as e:
            self._ipc_failed = True
            self._ipc_available = False
            self._kipy_kicad = None
            _log.warning(
                "KiCad IPC API connection failed: %s. Falling back to kicad-cli.", e
            )
            return False

    def _disconnect_ipc(self) -> None:
        """Close the IPC connection and reset state."""
        if self._kipy_kicad is not None:
            try:
                self._kipy_kicad.close()
            except Exception:
                pass
            self._kipy_kicad = None
        self._ipc_available = None
        self._ipc_failed = False
