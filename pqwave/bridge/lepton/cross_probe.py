# pqwave/bridge/lepton/cross_probe.py
"""TCP client for pqwave-server.scm running inside lepton-schematic.

Does NOT silently install the Scheme server. The caller must explicitly
call install_scheme_server() after obtaining user consent.
"""

import os
import shutil
import socket
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


def _get_package_scm_path() -> str:
    """Return the path to pqwave-server.scm inside the pqwave package."""
    return str(Path(__file__).resolve().parent / "pqwave-server.scm")


def _get_autoload_dir() -> str:
    """Return the lepton-eda autoload directory path."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(xdg_config, "lepton-eda", "scheme", "autoload")


def _get_target_path() -> str:
    return os.path.join(_get_autoload_dir(), "pqwave-server.scm")


def check_scheme_server() -> dict:
    """Check whether pqwave-server.scm is installed in the autoload directory.

    Returns a dict with keys:
        installed: bool
        target_path: str
        current_version_mtime: float | None
        bundled_version_mtime: float
        needs_update: bool
    """
    bundled = _get_package_scm_path()
    target = _get_target_path()
    bundled_mtime = os.path.getmtime(bundled)

    if not os.path.exists(target):
        return {
            "installed": False,
            "target_path": target,
            "current_version_mtime": None,
            "bundled_version_mtime": bundled_mtime,
            "needs_update": True,
        }
    installed_mtime = os.path.getmtime(target)
    return {
        "installed": True,
        "target_path": target,
        "current_version_mtime": installed_mtime,
        "bundled_version_mtime": bundled_mtime,
        "needs_update": bundled_mtime > installed_mtime,
    }


def install_scheme_server() -> dict:
    """Copy pqwave-server.scm to the lepton-eda autoload directory.

    Caller is responsible for obtaining user consent before calling.
    Returns {"status": "ok", "target_path": str}
         or {"status": "error", "message": str}.
    """
    try:
        os.makedirs(_get_autoload_dir(), exist_ok=True)
        shutil.copy2(_get_package_scm_path(), _get_target_path())
        return {"status": "ok", "target_path": _get_target_path()}
    except OSError as e:
        return {"status": "error", "message": str(e)}


class LeptonCrossProbeClient(QObject):
    """TCP client for pqwave-server.scm running inside lepton-schematic.

    Sends cross-probe and back-annotation commands. Receives reverse
    cross-probe events ($SELECTED:net / $SELECTED:part).

    Does NOT install the Scheme server automatically. The caller must
    check check_scheme_server() and call install_scheme_server() explicitly.

    Signals:
        connected():          TCP connection established
        disconnected():       TCP connection closed
        error_occurred(str):  connection or send error message
        net_selected(str):    user clicked a net in lepton-schematic
        part_selected(str):   user clicked a component in lepton-schematic
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    net_selected = pyqtSignal(str)
    part_selected = pyqtSignal(str)

    def __init__(self, port: int = 9424, timeout: float = 2.0):
        super().__init__()
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None
        self._reader_thread: threading.Thread | None = None
        self._running = False

    def is_connected(self) -> bool:
        return self._sock is not None

    def connect_to_server(self) -> bool:
        """Open TCP connection to localhost:port. Returns True on success.

        The Scheme server must already be installed and lepton-schematic
        must be running with pqwave-server.scm loaded.
        """
        try:
            self._sock = socket.create_connection(
                ("localhost", self._port), timeout=self._timeout
            )
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            self.connected.emit()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self.error_occurred.emit(
                f"Cannot connect to lepton-schematic on localhost:{self._port}: {e}"
            )
            return False

    def disconnect(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            self.disconnected.emit()

    def send_command(self, text: str) -> bool:
        if not self._sock:
            self.error_occurred.emit("Not connected to lepton-schematic")
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
        return self.send_command(f'$NET: "{name}"')

    def probe_part(self, ref: str, pin: str | None = None) -> bool:
        if pin:
            return self.send_command(f'$PART: "{ref}" $PAD: "{pin}"')
        return self.send_command(f'$PART: "{ref}"')

    def clear(self) -> bool:
        return self.send_command("$CLEAR")

    def _read_loop(self):
        buf = b""
        while self._running and self._sock:
            try:
                data = self._sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = line.decode("utf-8").strip()
                        self._handle_message(msg)
                    except UnicodeDecodeError as e:
                        self.error_occurred.emit(f"Decode error: {e}")
            except OSError:
                break
        if self._running:
            self._running = False
            self._sock = None
            self.disconnected.emit()

    def _handle_message(self, msg: str):
        if msg.startswith("$SELECTED:net "):
            self.net_selected.emit(msg[14:].strip())
        elif msg.startswith("$SELECTED:part "):
            self.part_selected.emit(msg[15:].strip())
        else:
            self.error_occurred.emit(f"Unknown message from server: {msg[:80]}")
