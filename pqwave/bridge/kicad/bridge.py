"""KiCad-specific SchematicBridge implementation — Level 1 (no cross-probe).

Uses kicad-cli for netlist export and ngspice for simulation.
Back-annotation via KiCad IPC API (CreateItems/UpdateItems/DeleteItems)
when kicad-python (kipy) is installed and KiCad IPC API is enabled.

Cross-probe (highlight net/component in Eeschema) is NOT supported
at this level — it requires selection API handlers
(GetSelection/AddToSelection/ClearSelection) that are not yet
registered in KiCad's upstream eeschema API handler.
"""

import logging
import os
import re
import shutil
import subprocess
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix, resolve_ngspice
from pqwave.bridge.kicad.fixes import (
    StripSlashes, FixDiodePins, FixBJTPins, MoveControlBlock,
)
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState

_log = logging.getLogger(__name__)


class KiCadBridge(SchematicBridge):
    """SchematicBridge for KiCad Eeschema — Level 1.

    Simulation pipeline:
      1. Export SPICE netlist via kicad-cli
      2. Post-process (slash stripping, diode/BJT pin fixes, control block)
      3. Run ngspice -b -r output.raw
      4. Load .raw results

    Back-annotation (requires KiCad 10+ with IPC API enabled):
      - annotate_dc(): stamp DC operating-point values as SchematicText
      - clear_annotations(): remove annotation text items

    Cross-probe is NOT available — probe_net/probe_part/clear_probe
    log a message and return silently.
    """

    def __init__(self, kicad_cli_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._kicad_cli = kicad_cli_path
        self._ngspice = ngspice_path
        self._connected_path: str | None = None

        # IPC back-annotation state (lazy-initialised)
        self._kipy_kicad = None       # kipy.KiCad instance
        self._kipy_client = None      # cached API client
        self._cached_document = None  # DocumentSpecifier from get_schematic()
        self._last_ipc_error: str | None = None  # diagnostic for last IPC failure
        self._last_ipc_fail_time: float | None = None  # rate-limit reconnects
        self._dc_ids: dict[str, str] = {}  # net_name → KIID (DC annotate)
        self._cursor_ids: dict[str, tuple[str | None, int, int]] = {}  # lower → (KIID|None, x, y)
        self._net_positions_cache: dict[str, tuple[int, int]] | None = None

    # ---- SchematicBridge implementation ----

    def _sim_dir(self, sch_path: str) -> str:
        """Return the simulation output directory (next to the schematic)."""
        sch_dir = os.path.dirname(os.path.abspath(sch_path))
        sim_dir = os.path.join(sch_dir, "simulation")
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir

    def _sch_basename(self, sch_path: str) -> str:
        return os.path.splitext(os.path.basename(sch_path))[0]

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .kicad_sch file via kicad-cli."""
        kicad_cli = self._resolve_kicad_cli()
        sim_dir = self._sim_dir(sch_path)
        basename = self._sch_basename(sch_path)
        cir_path = os.path.join(sim_dir, f"{basename}.cir")

        result = subprocess.run(
            [kicad_cli, "sch", "export", "netlist", "--format", "spice",
             "-o", cir_path, sch_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"kicad-cli failed with code {result.returncode}: {result.stderr}"
            )
        if not os.path.isfile(cir_path):
            raise RuntimeError(
                f"kicad-cli exited 0 but no output at {cir_path}: {result.stderr}"
            )
        with open(cir_path, "r") as f:
            return f.read()

    def get_netlist_fixes(self) -> list[NetlistFix]:
        """Return KiCad-specific fixes in the correct order."""
        return [StripSlashes(), FixDiodePins(), FixBJTPins(), MoveControlBlock()]

    def probe_net(self, net_name: str) -> None:
        """Cross-probe not available at Level 1.

        Requires GetSelection/AddToSelection/ClearSelection handlers
        not yet in upstream KiCad's eeschema API handler.
        """
        _log.debug("KiCad probe_net(%r): not available (Level 1)", net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        """Cross-probe not available at Level 1."""
        _log.debug("KiCad probe_part(%r): not available (Level 1)", ref)

    def clear_probe(self) -> None:
        """Cross-probe not available at Level 1."""
        _log.debug("KiCad clear_probe: not available (Level 1)")

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

    # ---- Connection state ----

    @property
    def connected_path(self) -> Optional[str]:
        return self._connected_path

    def get_status(self) -> dict:
        """Return current connection state for the control bar."""
        return {
            "connected": self._connected_path is not None,
            "path": self._connected_path,
            "kicad_cli": shutil.which("kicad-cli") or "",
            "has_ipc": self._has_ipc(),
        }

    def connect(self, sch_path: str = "") -> bool:
        """Connect to KiCad Eeschema via IPC and detect the open schematic.

        If *sch_path* is given, uses it directly.  Otherwise queries
        ``GetOpenDocuments`` to find the schematic currently open in
        Eeschema.  Verifies kicad-cli is available for simulation.
        """
        if sch_path:
            if not os.path.isfile(sch_path):
                _log.error("Schematic not found: %s", sch_path)
                return False
        else:
            # Auto-detect from running Eeschema
            client = self._get_ipc_client()
            if client is not None:
                try:
                    from kipy.proto.common.commands.editor_commands_pb2 import (
                        GetOpenDocuments, GetOpenDocumentsResponse,
                    )
                    from kipy.proto.common.types import DocumentType
                    req = GetOpenDocuments()
                    req.type = DocumentType.DOCTYPE_SCHEMATIC
                    resp = client.send(req, GetOpenDocumentsResponse)
                    if resp.documents:
                        doc = resp.documents[0]
                        sch_path = os.path.join(
                            doc.project.path,
                            doc.project.name + ".kicad_sch",
                        )
                        _log.info("Auto-detected schematic: %s", sch_path)
                except Exception as e:
                    _log.warning("Could not auto-detect schematic: %s", e)

            if not sch_path or not os.path.isfile(sch_path):
                _log.error(
                    "No schematic given and could not auto-detect from Eeschema. "
                    "Open a schematic in KiCad Eeschema first, or pass a path."
                )
                return False

        try:
            self._resolve_kicad_cli()
        except FileNotFoundError:
            _log.error("kicad-cli not found")
            return False
        self._connected_path = os.path.abspath(sch_path)
        return True

    def disconnect(self) -> bool:
        """Clear connection state and cursor annotation texts (full forget)."""
        self.clear_cursor_annotations(forget_positions=True)
        self._disconnect_ipc()
        self._connected_path = None
        return True

    # ---- Simulation pipeline ----

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        """Run the full pipeline: export → post-process → ngspice → .raw.

        Output files go into a ``simulation/`` subdirectory next to the
        schematic (matching xschem's local-netlist-dir convention).
        """
        sim_dir = self._sim_dir(sch_path)
        basename = self._sch_basename(sch_path)

        netlist = self.export_netlist(sch_path)
        context = self._build_context(sch_path)

        processor = NetlistPostProcessor(self.get_netlist_fixes())
        fix_info = [
            entry["detail"]
            for entry in processor.dry_run(netlist, context)
        ]
        fixed = processor.process(netlist, context)

        # Write the post-processed netlist into simulation/ dir
        cir_path = os.path.join(sim_dir, f"{basename}.cir")
        with open(cir_path, "w") as f:
            f.write(fixed)

        if raw_output is None:
            raw_output = os.path.join(sim_dir, f"{basename}.raw")

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

    # ---- IPC back-annotation (KiCad 10+ with IPC API enabled) ----

    def _has_ipc(self) -> bool:
        """Check whether the KiCad IPC API is reachable."""
        return self._get_ipc_client() is not None

    def _get_ipc_client(self):
        """Get or create a kipy client connected to KiCad's IPC API.

        Uses the KICAD_API_SOCKET environment variable if set,
        otherwise defaults to /tmp/kicad/api.sock.

        Stores the last error in ``self._last_ipc_error`` for diagnostics.
        Rate-limits reconnection attempts to once per 30 seconds after failure.
        """
        if self._kipy_client is not None:
            return self._kipy_client

        # Rate-limit reconnection: don't hammer the socket if KiCad is down
        import time as _time
        now = _time.monotonic()
        if self._last_ipc_fail_time and (now - self._last_ipc_fail_time) < 30:
            return None
        self._last_ipc_fail_time = None

        self._last_ipc_error = None

        try:
            import kipy
        except ImportError as e:
            self._last_ipc_error = f"kipy import failed: {e}"
            self._last_ipc_fail_time = _time.monotonic()
            _log.info("%s", self._last_ipc_error)
            return None

        socket_path = os.environ.get("KICAD_API_SOCKET", "/tmp/kicad/api.sock")
        if not socket_path.startswith("ipc://"):
            socket_path = f"ipc://{socket_path}"

        try:
            self._kipy_kicad = kipy.KiCad(
                socket_path=socket_path, timeout_ms=3000
            )
            self._kipy_client = self._kipy_kicad._client

            # Cache the DocumentSpecifier from the open schematic
            # (needed for all CreateItems/UpdateItems/DeleteItems calls)
            try:
                sch = self._kipy_kicad.get_schematic()
                self._cached_document = sch.document
                _log.info("Got schematic document: %s", self._cached_document)
            except Exception as e:
                self._last_ipc_error = f"get_schematic() failed: {e}"
                self._last_ipc_fail_time = _time.monotonic()
                _log.warning("%s", self._last_ipc_error)
                self._kipy_client = None
                self._kipy_kicad = None
                return None

            self._last_ipc_fail_time = None
            _log.info("Connected to KiCad IPC at %s", socket_path)
            return self._kipy_client
        except Exception as e:
            self._last_ipc_error = f"IPC connect to {socket_path} failed: {e}"
            self._last_ipc_fail_time = _time.monotonic()
            _log.warning("%s", self._last_ipc_error)
            return None

    def _invalidate_ipc(self) -> None:
        """Drop the cached IPC client so the next call reconnects."""
        self._kipy_client = None
        self._kipy_kicad = None
        self._cached_document = None
        self._net_positions_cache = None

    def _disconnect_ipc(self):
        """Release IPC connection and close underlying socket."""
        if self._kipy_kicad is not None:
            try:
                if hasattr(self._kipy_kicad, 'close'):
                    self._kipy_kicad.close()
            except Exception as e:
                _log.debug("IPC close error: %s", e)
        if self._kipy_client is not None:
            try:
                if hasattr(self._kipy_client, 'close'):
                    self._kipy_client.close()
            except Exception as e:
                _log.debug("IPC client close error: %s", e)
        self._invalidate_ipc()

    def _get_net_positions(self, net_names: list[str]) -> dict[str, tuple[int, int]]:
        """Get (x_nm, y_nm) positions for annotation text placement.

        Uses the net's global/hierarchical label position (the visual
        anchor, matching xschem's lab_pin approach), falling back to
        the bounding-box centre of wire/junction items.

        Results are cached — label positions are static during a session.
        Cache is cleared on disconnect.
        """
        client = self._get_ipc_client()
        if client is None or self._kipy_kicad is None:
            return {}

        # Return cached positions for known nets; only query new ones
        # Cache keys are always lowercase
        cached: dict[str, tuple[int, int]] = {}
        if self._net_positions_cache is not None:
            to_query = []
            for name in net_names:
                lower = name.lower()
                if lower in self._net_positions_cache:
                    cached[name] = self._net_positions_cache[lower]
                else:
                    to_query.append(name)
            if not to_query:
                return cached
            net_names = to_query
        else:
            self._net_positions_cache = {}

        positions: dict[str, tuple[int, int]] = {}
        target_lower = {n.lower(): n for n in net_names}

        # ---- Pass 1: label positions (visual anchor, like xschem lab_pin) ----
        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                GetItems, GetItemsResponse,
            )
            from kipy.proto.common.types import (  # noqa: F401
                ItemHeader, KOT_SCH_GLOBAL_LABEL,
                KOT_SCH_HIER_LABEL, KOT_SCH_LABEL,
            )

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._cached_document)
            req = GetItems()
            req.header.CopyFrom(hdr)
            for label_type in [KOT_SCH_GLOBAL_LABEL, KOT_SCH_HIER_LABEL, KOT_SCH_LABEL]:
                req.types.append(label_type)

            resp = client.send(req, GetItemsResponse)

            from kipy.proto.schematic.schematic_types_pb2 import (
                GlobalLabel, HierarchicalLabel, LocalLabel,
            )
            for item_any in resp.items:
                for label_cls in [GlobalLabel, HierarchicalLabel, LocalLabel]:
                    label = label_cls()
                    if item_any.Unpack(label):
                        text = label.text.text.strip()
                        lower = text.lower()
                        if lower in target_lower:
                            x = label.position.x_nm
                            y = label.position.y_nm
                            positions[target_lower[lower]] = (x, y)
                        break
        except Exception as e:
            _log.warning("Label lookup failed: %s", e)

        # ---- Pass 2: wire/junction bbox for nets without labels ----
        missing = [n for n in net_names if n not in positions]
        if not missing:
            return positions

        try:
            sch = self._kipy_kicad.get_schematic()
            netlist = sch.get_netlist()
        except Exception as e:
            _log.warning("get_netlist failed: %s", e)
            return positions

        net_kiids: dict[str, list[str]] = {}
        missing_lower = {n.lower() for n in missing}
        for net in netlist:
            if net.name.lower() in missing_lower:
                kiids = []
                for sheet in net.sheets:
                    for kiid in sheet.items:
                        kiids.append(str(kiid.value))
                        if len(kiids) >= 6:
                            break
                    if len(kiids) >= 6:
                        break
                if kiids:
                    net_kiids[net.name.lower()] = kiids

        if net_kiids:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                GetItemsById as GIBI, GetItemsResponse as GIR,
            )

            hdr2 = ItemHeader()
            hdr2.document.CopyFrom(self._cached_document)
            req2 = GIBI()
            req2.header.CopyFrom(hdr2)
            all_kiids: list[str] = []
            rev_map: dict[str, str] = {}
            for net_lower, kiids in net_kiids.items():
                for k in kiids:
                    kiid = req2.items.add()
                    kiid.value = k
                    all_kiids.append(k)
                    rev_map[k] = net_lower

            try:
                resp2 = client.send(req2, GIR)
            except Exception as e:
                _log.warning("GetItemsById failed: %s", e)
                return positions

            from kipy.proto.schematic.schematic_types_pb2 import (
                SchematicLine, Junction, BusEntry,
            )
            all_pts: dict[str, list[tuple[int, int]]] = {}
            for i, item_any in enumerate(resp2.items):
                if i >= len(all_kiids):
                    break
                net_lower = rev_map.get(all_kiids[i])
                if net_lower is None:
                    continue
                for msg_type in [Junction, BusEntry, SchematicLine]:
                    item = msg_type()
                    if item_any.Unpack(item):
                        if hasattr(item, 'position'):
                            x, y = item.position.x_nm, item.position.y_nm
                        elif hasattr(item, 'start'):
                            x, y = item.start.x_nm, item.start.y_nm
                        else:
                            break
                        all_pts.setdefault(net_lower, []).append((x, y))
                        break

            for net_lower, pts in all_pts.items():
                if pts and net_lower not in positions:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    positions[net_lower] = (
                        (min(xs) + max(xs)) // 2,
                        (min(ys) + max(ys)) // 2,
                    )

        _log.info("Got positions for %d/%d nets", len(positions), len(net_names))
        # Store in cache (lowercase keys) and merge with previously cached results
        if self._net_positions_cache is not None:
            for pos_name, pos_val in positions.items():
                self._net_positions_cache[pos_name.lower()] = pos_val
            positions.update(cached)
        return positions

    def annotate_cursor_values(self, voltages: dict[str, float]) -> bool:
        """Stamp cursor trace values near net labels, updating in-place.

        Matches the xschem pattern: existing cursor texts are updated via
        UpdateItems (preserving user repositioning).  New nets get texts
        created via CreateItems at the net label position.  Nets no longer
        in the values dict have their cursor texts deleted.

        Uses a separate ``_cursor_ids`` dict from DC annotations so the
        two modes don't interfere.
        """
        client = self._get_ipc_client()
        if client is None:
            _log.debug("annotate_cursor_values: no IPC client")
            return False

        _log.debug("annotate_cursor_values: %d nets, existing cursor_ids=%s",
                   len(voltages), list(self._cursor_ids.keys()))

        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                CreateItems, CreateItemsResponse,
                UpdateItems, UpdateItemsResponse,
                DeleteItems, DeleteItemsResponse,
            )
            from kipy.proto.common.types import (  # noqa: F401
                ItemHeader, KIID,
            )
            from kipy.proto.schematic.schematic_types_pb2 import SchematicText

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._cached_document)
            net_positions = self._get_net_positions(list(voltages.keys()))
            net_lower_map = {n.lower(): n for n in voltages}

            to_update: dict[str, str] = {}  # lowercase net → new text
            to_create: dict[str, tuple[int, int, str]] = {}  # lower → (x, y, text)
            to_delete: list[str] = []  # KIIDs to delete

            # Separate nets into update / create / delete
            for net_name, voltage in voltages.items():
                text_value = f"{voltage:.4g}V"
                lower = net_name.lower()
                entry = self._cursor_ids.get(lower)
                if entry is not None and entry[0] is not None:
                    # Has valid KIID → update in-place
                    to_update[lower] = text_value
                elif entry is not None:
                    # Was cleared (KIID is None) → re-create at remembered position
                    _kiid, px, py = entry
                    to_create[lower] = (px, py, text_value)
                else:
                    pos = net_positions.get(lower)
                    if pos:
                        to_create[lower] = (pos[0], pos[1] - 2_540_000, text_value)
                    else:
                        to_create[lower] = (10_000_000, 10_000_000, text_value)

            _log.debug("annotate_cursor_values: to_update=%s to_create=%s",
                       list(to_update.keys()), list(to_create.keys()))
            for lower, (kiid, _x, _y) in list(self._cursor_ids.items()):
                if lower not in net_lower_map:
                    if kiid is not None:
                        to_delete.append(kiid)
                    del self._cursor_ids[lower]
            _log.debug("annotate_cursor_values: to_delete=%s", to_delete)

            # 1. Delete texts for nets no longer visible
            if to_delete:
                del_req = DeleteItems()
                del_req.header.CopyFrom(hdr)
                for kiid_str in to_delete:
                    kiid = del_req.item_ids.add()
                    kiid.value = kiid_str
                try:
                    client.send(del_req, DeleteItemsResponse)
                except Exception:
                    self._invalidate_ipc()
                    _log.warning("Cursor delete failed", exc_info=True)

            # 2. Read current positions from KiCad (preserves user drag-and-place)
            current_positions: dict[str, tuple[int, int]] = {}
            if to_update:
                client = self._get_ipc_client() or client
                try:
                    from kipy.proto.common.commands.editor_commands_pb2 import (
                        GetItemsById as GIBI, GetItemsResponse as GIR,
                    )
                    pos_req = GIBI()
                    pos_req.header.CopyFrom(hdr)
                    pos_order: list[str] = []
                    for lower in to_update:
                        kiid_str = self._cursor_ids[lower][0]
                        k = pos_req.items.add()
                        k.value = kiid_str
                        pos_order.append(lower)
                    pos_resp = client.send(pos_req, GIR)
                    for i, item_any in enumerate(pos_resp.items):
                        if i >= len(pos_order):
                            break
                        st = SchematicText()
                        if item_any.Unpack(st):
                            current_positions[pos_order[i]] = (
                                st.text.position.x_nm, st.text.position.y_nm)
                except Exception:
                    _log.debug("Failed to read current positions, using stored", exc_info=True)

            # 3. Update existing texts in-place (preserve user position)
            if to_update:
                client = self._get_ipc_client() or client
                upd_req = UpdateItems()
                upd_req.header.CopyFrom(hdr)
                for lower, text_value in to_update.items():
                    kiid_str = self._cursor_ids[lower][0]
                    px, py = current_positions.get(
                        lower, (self._cursor_ids[lower][1], self._cursor_ids[lower][2]))
                    # Update stored position in case user moved it
                    self._cursor_ids[lower] = (kiid_str, px, py)

                    sch_text = SchematicText()
                    kiid = KIID()
                    kiid.value = kiid_str
                    sch_text.id.CopyFrom(kiid)
                    sch_text.locked = 1
                    sch_text.exclude_from_sim = True
                    sch_text.text.text = text_value
                    sch_text.text.position.x_nm = px
                    sch_text.text.position.y_nm = py
                    any_item = upd_req.items.add()
                    any_item.Pack(sch_text)
                try:
                    client.send(upd_req, UpdateItemsResponse)
                except Exception:
                    self._invalidate_ipc()
                    _log.warning("Cursor update failed", exc_info=True)

            # 4. Create new texts for previously unseen nets
            if to_create:
                client = self._get_ipc_client() or client
                cre_req = CreateItems()
                cre_req.header.CopyFrom(hdr)
                for lower, (x, y, text_value) in to_create.items():
                    _log.debug("annotate_cursor_values: CREATE %s at (%d, %d) nm = (%.2f, %.2f) mm text=%r",
                               lower, x, y, x/1e6, y/1e6, text_value)
                    sch_text = SchematicText()
                    sch_text.locked = 1  # LS_UNLOCKED
                    sch_text.exclude_from_sim = True
                    sch_text.text.text = text_value
                    sch_text.text.position.x_nm = x
                    sch_text.text.position.y_nm = y
                    sch_text.text.attributes.size.x_nm = 1_270_000
                    sch_text.text.attributes.size.y_nm = 1_270_000
                    sch_text.text.attributes.stroke_width.value_nm = 127_000
                    sch_text.text.attributes.horizontal_alignment = 1
                    sch_text.text.attributes.vertical_alignment = 2
                    any_item = cre_req.items.add()
                    any_item.Pack(sch_text)
                try:
                    resp = client.send(cre_req, CreateItemsResponse)
                    create_names = list(to_create.keys())
                    for i, item_result in enumerate(resp.created_items):
                        if i >= len(create_names):
                            break
                        lower = create_names[i]
                        if item_result.status.code == 1:
                            unpacked = SchematicText()
                            if item_result.item.Unpack(unpacked) and unpacked.id.value:
                                # Store (KIID, x, y) — position for future updates
                                cx, cy, _ = to_create[lower]
                                self._cursor_ids[lower] = (unpacked.id.value, cx, cy)
                except Exception as e:
                    self._invalidate_ipc()
                    _log.warning("Cursor create failed: %s", e)

            return True

        except Exception as e:
            self._last_ipc_error = f"annotate_cursor_values: {e}"
            _log.debug("Cursor annotation failed: %s", e)
            return False

    def annotate_dc(self, voltages: dict[str, float]) -> bool:
        """Stamp DC operating-point values onto the schematic as text items.

        Uses the KiCad IPC API to create SchematicText items with net
        name and voltage value.  Tracked KIIDs are stored for later
        update or clear operations.

        Requires KiCad 10+ with IPC API enabled and kicad-python installed.

        Returns True on success, False if IPC is unavailable or fails.
        """
        client = self._get_ipc_client()
        if client is None:
            _log.info("KiCad IPC API not available — skipping back-annotation")
            return False

        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                CreateItems, CreateItemsResponse, DeleteItems, DeleteItemsResponse,
            )
            from kipy.proto.common.types import (  # noqa: F401
                ItemHeader, DocumentSpecifier, DocumentType,
                Text, Vector2, Distance, TextAttributes, KIID,
            )
            from kipy.proto.schematic.schematic_types_pb2 import SchematicText

            # 1. Delete old annotations (use DeleteItems for tracked KIIDs)
            if self._dc_ids:
                del_req = DeleteItems()
                hdr = ItemHeader()
                hdr.document.CopyFrom(self._cached_document)
                del_req.header.CopyFrom(hdr)
                for kiid_str in self._dc_ids.values():
                    kiid = del_req.item_ids.add()
                    kiid.value = kiid_str
                try:
                    client.send(del_req, DeleteItemsResponse)
                except Exception:
                    _log.warning("Failed to delete old annotations", exc_info=True)
                self._dc_ids.clear()

            # 2. Get net positions for placement
            net_positions = self._get_net_positions(list(voltages.keys()))

            # 3. Create new annotation text items
            req = CreateItems()
            hdr = ItemHeader()
            hdr.document.CopyFrom(self._cached_document)
            req.header.CopyFrom(hdr)

            for idx, (net_name, voltage) in enumerate(voltages.items()):
                text_value = f"{voltage:.4g}V"

                sch_text = SchematicText()
                sch_text.locked = 1  # LS_UNLOCKED
                sch_text.exclude_from_sim = True

                txt = sch_text.text
                # Position near the net if possible, otherwise stack at a default
                pos = net_positions.get(net_name.lower())
                if pos:
                    txt.position.x_nm = pos[0]
                    txt.position.y_nm = pos[1] - 2_540_000  # offset below net (Y-up)
                else:
                    txt.position.x_nm = 10_000_000
                    txt.position.y_nm = -(10_000_000 + idx * 2_540_000)
                txt.text = text_value

                # Text size: 1.27mm (50 mils)
                txt.attributes.size.x_nm = 1_270_000
                txt.attributes.size.y_nm = 1_270_000
                txt.attributes.stroke_width.value_nm = 127_000  # 5 mils
                txt.attributes.horizontal_alignment = 1  # HA_LEFT
                txt.attributes.vertical_alignment = 2  # VA_CENTER

                any_item = req.items.add()
                any_item.Pack(sch_text)

            if not req.items:
                return True  # nothing to create

            resp = client.send(req, CreateItemsResponse)

            # 3. Track created KIIDs (unpack Any into SchematicText)
            for i, item_result in enumerate(resp.created_items):
                net_names = list(voltages.keys())
                if i >= len(net_names):
                    break
                net_name = net_names[i]
                if item_result.status.code == 1:  # ISC_OK
                    unpacked = SchematicText()
                    if item_result.item.Unpack(unpacked) and unpacked.id.value:
                        kiid_str = unpacked.id.value
                        self._dc_ids[net_name] = kiid_str
                        _log.debug("Tracked KIID %s for net %s", kiid_str, net_name)
                    else:
                        _log.warning("Created item %d: unpack/id failed", i)
                else:
                    _log.warning(
                        "CreateItems status for %s: code=%d msg=%s",
                        net_name, item_result.status.code,
                        item_result.status.error_message)

            _log.info(
                "Annotated %d DC values on schematic, tracked %d KIIDs",
                len(req.items), len(self._dc_ids))
            return True

        except Exception as e:
            self._invalidate_ipc()
            self._last_ipc_error = f"annotate_dc: {e}"
            _log.warning("Back-annotation failed: %s", e)
            return False

    def clear_cursor_annotations(self, forget_positions: bool = False) -> bool:
        """Remove cursor texts from schematic.

        By default, remembers positions so texts can be re-created at
        the same spot when the cursor is turned back on.  Pass
        ``forget_positions=True`` to fully clear (disconnect/exit).
        """
        client = self._get_ipc_client()
        if client is None:
            # IPC down — still clear local state on full forget
            if forget_positions:
                self._cursor_ids.clear()
            return False
        if not self._cursor_ids:
            return True  # nothing to clear

        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                DeleteItems, DeleteItemsResponse,
            )
            from kipy.proto.common.types import ItemHeader  # noqa: F401

            req = DeleteItems()
            hdr = ItemHeader()
            hdr.document.CopyFrom(self._cached_document)
            req.header.CopyFrom(hdr)
            for kiid_str, _x, _y in self._cursor_ids.values():
                if kiid_str is not None:
                    kiid = req.item_ids.add()
                    kiid.value = kiid_str
            if req.item_ids:
                client.send(req, DeleteItemsResponse)

            if forget_positions:
                self._cursor_ids.clear()
            else:
                # Keep positions, clear KIIDs only
                self._cursor_ids = {
                    k: (None, x, y) for k, (_kiid, x, y) in self._cursor_ids.items()
                }
            return True
        except Exception as e:
            self._invalidate_ipc()
            self._last_ipc_error = f"clear_cursor_annotations: {e}"
            _log.warning("Clear cursor annotations failed: %s", e)
            return False

    def clear_dc_annotations(self) -> bool:
        """Remove DC annotation text from the schematic (``_dc_ids`` only).

        Cursor back-annotation texts are NOT affected — they follow
        their own lifecycle (cleared on cursor-off / disconnect / exit).
        """
        client = self._get_ipc_client()
        if client is None:
            _log.info("KiCad IPC API not available — skipping clear")
            return False

        if not self._dc_ids:
            return True  # nothing to clear

        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                DeleteItems, DeleteItemsResponse,
            )
            from kipy.proto.common.types import (  # noqa: F401
                ItemHeader, DocumentSpecifier, DocumentType, KIID,
            )

            req = DeleteItems()
            hdr = ItemHeader()
            hdr.document.CopyFrom(self._cached_document)
            req.header.CopyFrom(hdr)

            for kiid_str in self._dc_ids.values():
                kiid = req.item_ids.add()
                kiid.value = kiid_str

            client.send(req, DeleteItemsResponse)
            self._dc_ids.clear()
            _log.info("Cleared %d annotations from schematic",
                      len(req.item_ids))
            return True

        except Exception as e:
            self._invalidate_ipc()
            self._last_ipc_error = f"clear_dc_annotations: {e}"
            _log.warning("Clear DC annotations failed: %s", e)
            # Preserve IDs for retry on next annotate
            return False
