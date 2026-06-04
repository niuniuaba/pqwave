"""IPC-based cross-probe client for KiCad Eeschema.

Uses the KiCad IPC API's AddToSelection and ClearSelection handlers
to highlight nets and components by resolving names to KIIDs via
get_netlist() and get_symbols().
"""

from PyQt6.QtCore import QObject, pyqtSignal


class IpcProbeClient(QObject):
    """Sends cross-probe commands to KiCad via the IPC API.

    Resolves net names to KIIDs via get_netlist() and component
    reference designators to KIIDs via get_symbols(), then uses
    ClearSelection + AddToSelection to highlight items.

    Requires the Eeschema selection IPC handlers (GetSelection,
    AddToSelection, ClearSelection) added in our KiCad build.

    Signals:
        connected():       IPC connection active
        disconnected():    IPC connection closed
        error_occurred(str): probe or connection error message
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._kicad = None  # kipy.KiCad instance, set by caller
        self._doc_spec = None  # DocumentSpecifier with project info
        self._annotation_map: dict[str, str] = {}  # netname → KIID

    def set_kicad(self, kicad) -> None:
        """Set the kipy.KiCad instance to use for probing.

        Call this after a successful ensure_ipc() on the KiCadBridge.
        Extracts the schematic's DocumentSpecifier (with project info)
        for use in subsequent IPC requests.
        """
        self._kicad = kicad
        try:
            sch = kicad.get_schematic()
            self._doc_spec = sch.document
        except Exception:
            # Fallback: create a minimal spec (will fail validation)
            from kipy.proto.common.types import DocumentSpecifier, DocumentType
            self._doc_spec = DocumentSpecifier()
            self._doc_spec.type = DocumentType.DOCTYPE_SCHEMATIC
        self.connected.emit()

    def is_connected(self) -> bool:
        return self._kicad is not None

    def disconnect(self) -> None:
        """Release the KiCad reference."""
        self._kicad = None
        self._doc_spec = None
        self.disconnected.emit()

    # ---- Probe operations ----

    def _find_net(self, netlist, name: str):
        """Find a net in *netlist* by case-insensitive name match.

        Tries exact match first, then prefix match at word boundary
        (e.g. 'R1' matches 'R1' but not 'R10').

        Returns the net object or None.
        """
        name_lower = name.lower()
        # Exact match
        for net in netlist:
            if net.name.lower() == name_lower:
                return net
        # Prefix match at word boundary
        for net in netlist:
            n = net.name.lower()
            if n.startswith(name_lower):
                if len(n) == len(name_lower) or not n[len(name_lower)].isalnum():
                    return net
        return None

    def probe_net(self, name: str) -> bool:
        """Highlight a net in KiCad Eeschema by resolving net name → KIIDs.

        Calls get_netlist() to find KIIDs for the named net, then
        ClearSelection + AddToSelection to highlight them.
        """
        if not self._kicad:
            self.error_occurred.emit("Not connected to KiCad")
            return False

        try:
            schematic = self._kicad.get_schematic()
            netlist = schematic.get_netlist()

            target = self._find_net(netlist, name)
            if target is None:
                self.error_occurred.emit(
                    f"Net '{name}' not found in schematic")
                return False

            # Collect KIIDs from all sheets
            kiids = []
            for sheet in target.sheets:
                kiids.extend(list(sheet.items))

            if not kiids:
                self.error_occurred.emit(
                    f"Net '{name}' has no items to select")
                return False

            return self._select_items(kiids)

        except Exception as e:
            self.error_occurred.emit(f"Probe net '{name}' failed: {e}")
            return False

    def probe_part(self, ref: str, pin: str | None = None) -> bool:
        """Highlight a component in KiCad Eeschema by resolving refdes → KIID.

        Note: pin-level selection is not supported by the current
        Eeschema IPC API. The pin parameter is accepted for API
        compatibility with SchematicBridge but is not used.
        """
        if not self._kicad:
            self.error_occurred.emit("Not connected to KiCad")
            return False

        try:
            schematic = self._kicad.get_schematic()
            symbols = schematic.get_symbols()

            target_id = None
            for sym in symbols:
                if (sym.reference_field
                        and sym.reference_field.text == ref):
                    target_id = sym.id
                    break

            if target_id is None:
                self.error_occurred.emit(
                    f"Symbol '{ref}' not found in schematic")
                return False

            return self._select_items([target_id])

        except Exception as e:
            self.error_occurred.emit(f"Probe part '{ref}' failed: {e}")
            return False

    def clear(self) -> bool:
        """Clear all cross-probe highlights in KiCad Eeschema."""
        if not self._kicad:
            self.error_occurred.emit("Not connected to KiCad")
            return False

        try:
            self._send_clear_selection()
            self.clear_annotations()
            return True
        except Exception as e:
            self.error_occurred.emit(f"Clear probe failed: {e}")
            return False

    # ---- Back-annotation: show trace values in Eeschema ----

    def annotate_values(self, net_values: dict) -> None:
        """Create or update text annotations in Eeschema showing trace values.

        Tracks annotation items by net name.  Existing items are updated
        in-place via UpdateItems (preserving user position/rotation).
        New nets get CreateItems.  Stale nets (previously annotated but
        not in this update) get deleted.
        """
        if not self._kicad or not net_values:
            return

        try:
            updated_nets = set(net_values.keys())
            existing_nets = set(self._annotation_map.keys())

            # 1. Update existing items in-place
            for net in updated_nets & existing_nets:
                kiid = self._annotation_map[net]
                value_str = net_values[net]
                self._update_text_item(kiid, f"{net}={value_str}")

            # 2. Create new items for previously unseen nets
            if updated_nets - existing_nets:
                schematic = self._kicad.get_schematic()
                netlist = schematic.get_netlist()
                text_items = []
                new_net_names = []

                for net_name in updated_nets - existing_nets:
                    target_net = self._find_net(netlist, net_name)
                    if target_net is None:
                        continue
                    net_kiids = []
                    for sheet in target_net.sheets:
                        net_kiids.extend(list(sheet.items))
                    if not net_kiids:
                        continue
                    bbox = self._get_items_bbox(net_kiids)
                    if bbox is None:
                        continue
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2
                    value_str = net_values[net_name]
                    text = f"{net_name}={value_str}"
                    sch_text = self._build_schematic_text(text, int(cx), int(cy))
                    if sch_text:
                        text_items.append(sch_text)
                        new_net_names.append(net_name)

                if text_items:
                    created_kiids = self._create_text_items_batch(text_items)
                    for i, net_name in enumerate(new_net_names):
                        if i < len(created_kiids):
                            self._annotation_map[net_name] = created_kiids[i]

            # 3. Remove stale items for nets no longer in the update
            for net in existing_nets - updated_nets:
                kiid = self._annotation_map[net]
                self._delete_single_item(kiid)
                del self._annotation_map[net]

        except Exception as e:
            self.error_occurred.emit(f"Back-annotation failed: {e}")

    def clear_annotations(self) -> None:
        """Delete all back-annotation text items from Eeschema."""
        if not self._kicad:
            return
        self._delete_annotations()

    def _delete_annotations(self) -> None:
        """Delete all tracked annotation items."""
        if not self._annotation_map or not self._kicad:
            return
        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                DeleteItems, DeleteItemsResponse,
            )
            from kipy.proto.common.types import ItemHeader, KIID

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._doc_spec)
            req = DeleteItems()
            req.header.CopyFrom(hdr)
            for kid_str in self._annotation_map.values():
                kiid = KIID()
                kiid.value = kid_str
                req.item_ids.append(kiid)
            self._kicad._client.send(req, DeleteItemsResponse)
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Failed to delete annotation items", exc_info=True)
            return
        self._annotation_map.clear()

    def _update_text_item(self, kiid: str, new_text: str) -> None:
        """Update the text content of an existing SchematicText item via IPC."""
        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                UpdateItems, UpdateItemsResponse,
            )
            from kipy.proto.schematic.schematic_types_pb2 import SchematicText
            from kipy.proto.common.types import ItemHeader, KIID

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._doc_spec)

            item = SchematicText()
            kid = KIID()
            kid.value = kiid
            item.id.CopyFrom(kid)
            item.text = new_text

            req = UpdateItems()
            req.header.CopyFrom(hdr)
            req.items.append(item)

            self._kicad._client.send(req, UpdateItemsResponse)
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Failed to update annotation item %s", kiid, exc_info=True)

    def _delete_single_item(self, kiid: str) -> None:
        """Delete a single SchematicText item by KIID."""
        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                DeleteItems, DeleteItemsResponse,
            )
            from kipy.proto.common.types import ItemHeader, KIID

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._doc_spec)
            req = DeleteItems()
            req.header.CopyFrom(hdr)
            kid = KIID()
            kid.value = kiid
            req.item_ids.append(kid)
            self._kicad._client.send(req, DeleteItemsResponse)
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Failed to delete annotation item %s", kiid, exc_info=True)

    def _get_items_bbox(self, kiids: list) -> tuple | None:
        """Get the bounding box of a set of items by their KIIDs."""
        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                GetBoundingBox, GetBoundingBoxResponse,
            )
            from kipy.proto.common.types import ItemHeader, KIID

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._doc_spec)

            req = GetBoundingBox()
            req.header.CopyFrom(hdr)
            for kid in kiids[:20]:  # limit to avoid oversized request
                kiid = KIID()
                kiid.value = kid.value
                req.items.append(kiid)

            resp = self._kicad._client.send(req, GetBoundingBoxResponse)

            if not resp.boxes:
                return None

            # Compute union of all boxes (Box2 uses position + size, Vector2 uses x_nm/y_nm)
            boxes = [(b.position.x_nm, b.position.y_nm,
                      b.position.x_nm + b.size.x_nm, b.position.y_nm + b.size.y_nm)
                     for b in resp.boxes]
            x1 = min(b[0] for b in boxes)
            y1 = min(b[1] for b in boxes)
            x2 = max(b[2] for b in boxes)
            y2 = max(b[3] for b in boxes)
            return (x1, y1, x2, y2)

        except Exception:
            return None

    @staticmethod
    def _build_schematic_text(text: str, x_nm: int, y_nm: int):
        """Build a SchematicText protobuf message at the given position.

        Returns a SchematicText ready to be packed into a CreateItems
        request, or None on error.
        """
        try:
            from kipy.proto.schematic.schematic_types_pb2 import SchematicText
            from kipy.proto.common.types import Text, TextAttributes

            attrs = TextAttributes()
            attrs.horizontal_alignment = 1  # HA_LEFT
            attrs.vertical_alignment = 2    # VA_CENTER
            attrs.size.x_nm = 1_270_000     # 50 mil text height in nm
            attrs.size.y_nm = 1_270_000
            attrs.stroke_width.value_nm = 127_000  # 5 mil

            txt = Text()
            txt.position.x_nm = x_nm
            txt.position.y_nm = y_nm
            txt.text = text
            txt.attributes.CopyFrom(attrs)

            sch_text = SchematicText()
            sch_text.text.CopyFrom(txt)
            sch_text.locked = 2  # LS_UNLOCKED
            sch_text.exclude_from_sim = True
            return sch_text
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Failed to build SchematicText", exc_info=True)
            return None

    def _create_text_items_batch(self, text_items: list) -> list[str]:
        """Create multiple SchematicText items in a single CreateItems IPC request.

        Returns a list of KIID strings for the created items.
        """
        try:
            from kipy.proto.common.commands.editor_commands_pb2 import (
                CreateItems, CreateItemsResponse,
            )
            from kipy.proto.common.types import ItemHeader
            from kipy.proto.schematic.schematic_types_pb2 import SchematicText
            from google.protobuf.any_pb2 import Any

            hdr = ItemHeader()
            hdr.document.CopyFrom(self._doc_spec)

            req = CreateItems()
            req.header.CopyFrom(hdr)
            for sch_text in text_items:
                any_item = Any()
                any_item.Pack(sch_text)
                req.items.append(any_item)

            resp = self._kicad._client.send(req, CreateItemsResponse)

            created_kiids = []
            for result in resp.created_items:
                created = SchematicText()
                if result.item.Unpack(created) and created.id.value:
                    created_kiids.append(created.id.value)
            return created_kiids

        except Exception as e:
            self.error_occurred.emit(f"Create text annotations failed: {e}")
            return []

    # ---- Internal helpers ----

    def _select_items(self, kiids: list) -> bool:
        """Clear previous selection, then add *kiids* to selection.

        Returns True if both IPC calls succeeded.
        """
        try:
            self._send_clear_selection()
            self._send_add_to_selection(kiids)
            return True
        except Exception as e:
            self.error_occurred.emit(f"Selection IPC failed: {e}")
            return False

    def _send_clear_selection(self) -> None:
        """Send a ClearSelection IPC command.

        kipy's client.send() raises ApiError on failure, so no
        explicit return value check is needed — exceptions are
        caught by _select_items.
        """
        from kipy.proto.common.commands.editor_commands_pb2 import (
            ClearSelection,
        )
        from kipy.proto.common.types import ItemHeader
        from google.protobuf.empty_pb2 import Empty

        hdr = ItemHeader()
        hdr.document.CopyFrom(self._doc_spec)

        req = ClearSelection()
        req.header.CopyFrom(hdr)
        self._kicad._client.send(req, Empty)

    def _send_add_to_selection(self, kiids: list) -> None:
        """Send an AddToSelection IPC command with the given KIIDs."""
        from kipy.proto.common.commands.editor_commands_pb2 import (
            AddToSelection, SelectionResponse,
        )
        from kipy.proto.common.types import ItemHeader

        hdr = ItemHeader()
        hdr.document.CopyFrom(self._doc_spec)

        req = AddToSelection()
        req.header.CopyFrom(hdr)
        for kiid in kiids:
            req.items.append(kiid)
        self._kicad._client.send(req, SelectionResponse)
