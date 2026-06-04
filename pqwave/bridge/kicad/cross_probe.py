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

    def set_kicad(self, kicad) -> None:
        """Set the kipy.KiCad instance to use for probing.

        Call this after a successful _ensure_ipc() on the KiCadBridge.
        """
        self._kicad = kicad
        self.connected.emit()

    def is_connected(self) -> bool:
        return self._kicad is not None

    def disconnect(self) -> None:
        """Release the KiCad reference."""
        self._kicad = None
        self.disconnected.emit()

    # ---- Probe operations ----

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

            # Case-insensitive exact match first, then substring
            target = None
            name_lower = name.lower()
            for net in netlist:
                if net.name.lower() == name_lower:
                    target = net
                    break
            if target is None:
                # Fallback: prefix match at word boundary (avoids R1 matching R10)
                for net in netlist:
                    n = net.name.lower()
                    if n.startswith(name_lower):
                        # Check boundary: next char is not alphanumeric
                        if len(n) == len(name_lower) or not n[len(name_lower)].isalnum():
                            target = net
                            break

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
            return True
        except Exception as e:
            self.error_occurred.emit(f"Clear probe failed: {e}")
            return False

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
        from kipy.proto.common.types import (
            ItemHeader, DocumentSpecifier, DocumentType,
        )
        from google.protobuf.empty_pb2 import Empty

        doc = DocumentSpecifier()
        doc.type = DocumentType.DOCTYPE_SCHEMATIC
        hdr = ItemHeader()
        hdr.document.CopyFrom(doc)

        req = ClearSelection()
        req.header.CopyFrom(hdr)
        self._kicad._client.send(req, Empty)

    def _send_add_to_selection(self, kiids: list) -> None:
        """Send an AddToSelection IPC command with the given KIIDs."""
        from kipy.proto.common.commands.editor_commands_pb2 import (
            AddToSelection, SelectionResponse,
        )
        from kipy.proto.common.types import (
            ItemHeader, DocumentSpecifier, DocumentType,
        )

        doc = DocumentSpecifier()
        doc.type = DocumentType.DOCTYPE_SCHEMATIC
        hdr = ItemHeader()
        hdr.document.CopyFrom(doc)

        req = AddToSelection()
        req.header.CopyFrom(hdr)
        for kiid in kiids:
            req.items.append(kiid)
        self._kicad._client.send(req, SelectionResponse)
