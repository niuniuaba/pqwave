"""TCP client for KiCad's built-in cross-probe server (port 4243)."""

import socket
from PyQt6.QtCore import QObject, pyqtSignal


class CrossProbeClient(QObject):
    """Sends cross-probe commands to KiCad's built-in TCP server.

    KiCad Eeschema listens on localhost:4243 (KICAD_SCH_PORT_SERVICE_NUMBER).
    Commands are plain-text, no framing::

        $NET: "net_name"
        $PART: "ref"
        $PART: "ref" $PAD: "pin"
        $CLEAR

    Signals:
        connected():       TCP connection established
        disconnected():    TCP connection closed
        error_occurred(str): connection or send error message
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, port: int = 4243, timeout: float = 2.0):
        super().__init__()
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None

    def is_connected(self) -> bool:
        return self._sock is not None

    def connect_to_kicad(self) -> bool:
        """Open TCP connection to localhost:port. Returns True on success."""
        try:
            self._sock = socket.create_connection(
                ("localhost", self._port), timeout=self._timeout
            )
            self.connected.emit()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self.error_occurred.emit(
                f"Cannot connect to KiCad on localhost:{self._port}: {e}"
            )
            return False

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            self.disconnected.emit()

    def send_command(self, text: str) -> bool:
        """Send a raw command string. Returns True on success."""
        if not self._sock:
            self.error_occurred.emit("Not connected to KiCad")
            return False
        try:
            msg = text.rstrip("\n") + "\n"
            self._sock.sendall(msg.encode("utf-8"))
            return True
        except OSError as e:
            self.error_occurred.emit(f"Send failed: {e}")
            self.disconnect()
            return False

    def probe_net(self, name: str) -> bool:
        """Highlight a net in the KiCad schematic."""
        return self.send_command(f'$NET: "{name}"')

    def probe_part(self, ref: str, pin: str | None = None) -> bool:
        """Highlight a component, or a specific pin on a component."""
        if pin:
            return self.send_command(f'$PART: "{ref}" $PAD: "{pin}"')
        return self.send_command(f'$PART: "{ref}"')

    def clear(self) -> bool:
        """Clear all cross-probe highlights."""
        return self.send_command("$CLEAR")
