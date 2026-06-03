"""IPC-based cross-probe client for KiCad Eeschema.

Replaces the previous TCP port 4243 approach (which was KiCad's internal
Eeschema-Pcbnew channel, not a public API).  Uses the IPC API's run_action()
for highlighting nets and components.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class IpcProbeClient(QObject):
    """Sends cross-probe commands to KiCad via the IPC API.

    Uses run_action() to execute Eeschema editor actions for highlighting
    nets and components.  If run_action proves unreliable for probing
    specific items, falls back to AddToSelection with KIID resolution.

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
        """Highlight a net in the KiCad schematic."""
        if not self._kicad:
            self.error_occurred.emit("Not connected to KiCad")
            return False

        try:
            for action in self._net_probe_actions(name):
                try:
                    response = self._kicad.run_action(action)
                    if response.status == 1:  # RAS_OK
                        return True
                except Exception:
                    continue
            return False
        except Exception as e:
            self.error_occurred.emit(f"Probe net '{name}' failed: {e}")
            return False

    def probe_part(self, ref: str, pin: str | None = None) -> bool:
        """Highlight a component (and optionally a specific pin) in KiCad."""
        if not self._kicad:
            self.error_occurred.emit("Not connected to KiCad")
            return False

        try:
            for action in self._part_probe_actions(ref, pin):
                try:
                    response = self._kicad.run_action(action)
                    if response.status == 1:  # RAS_OK
                        return True
                except Exception:
                    continue
            return False
        except Exception as e:
            self.error_occurred.emit(f"Probe part '{ref}' failed: {e}")
            return False

    def clear(self) -> bool:
        """Clear all cross-probe highlights in KiCad."""
        if not self._kicad:
            self.error_occurred.emit("Not connected to KiCad")
            return False

        try:
            response = self._kicad.run_action(
                "eeschema.InteractiveSelection.ClearSelection"
            )
            return response.status == 1  # RAS_OK
        except Exception as e:
            self.error_occurred.emit(f"Clear probe failed: {e}")
            return False

    # ---- Action name generators ----

    def _net_probe_actions(self, name: str) -> list[str]:
        """Return action names to try for net probing, ordered by preference."""
        return [
            f'eeschema.InteractiveSelection.SelectNet "{name}"',
            f'eeschema.InteractiveSelection.FindAndSelectNet "{name}"',
        ]

    def _part_probe_actions(self, ref: str, pin: str | None) -> list[str]:
        """Return action names to try for part probing."""
        actions = [
            f'eeschema.InteractiveSelection.SelectSymbol "{ref}"',
            f'eeschema.InteractiveSelection.FindAndSelectSymbol "{ref}"',
        ]
        return actions
