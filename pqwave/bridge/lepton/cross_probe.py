# pqwave/bridge/lepton/cross_probe.py
"""TCP client for pqwave-server.scm running inside lepton-schematic.

Does NOT silently install the Scheme server. The caller must explicitly
call install_scheme_server() after obtaining user consent.
"""

import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


def _get_package_scm_path() -> str:
    """Return the path to pqwave-server.scm inside the pqwave package."""
    return str(Path(__file__).resolve().parent / "pqwave-server.scm")


def _get_user_config_dir() -> str:
    """Return the lepton-eda user config directory (~/.config/lepton-eda)."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(xdg_config, "lepton-eda")


def _get_scm_target_path() -> str:
    """Return the target path for pqwave-server.scm in the user config dir."""
    return os.path.join(_get_user_config_dir(), "pqwave-server.scm")


def _get_gafrc_path() -> str:
    """Return the path to the user gafrc file."""
    return os.path.join(_get_user_config_dir(), "gafrc")


def check_scheme_server() -> dict:
    """Check whether pqwave menu additions are installed.

    The install adds menu-additions.scm to ~/.config/lepton-eda/ and
    appends a (load ...) line to lepton-eda's installed menu.scm.
    Returns a dict with keys:
        installed: bool
        additions_path: str
        menu_scm_path: str | None (None if lepton-eda not found)
        needs_update: bool
    """
    additions_path = os.path.join(_get_user_config_dir(), "pqwave-menus.scm")
    menu_scm_path = _find_lepton_menu_scm()
    if not menu_scm_path:
        return {
            "installed": False,
            "additions_path": additions_path,
            "menu_scm_path": None,
            "needs_update": False,
        }
    if not os.path.exists(additions_path):
        return {
            "installed": False,
            "additions_path": additions_path,
            "menu_scm_path": menu_scm_path,
            "needs_update": True,
        }
    # Check if menu.scm has the load line
    with open(menu_scm_path, "r") as f:
        has_load = "pqwave-menus.scm" in f.read()
    return {
        "installed": has_load,
        "additions_path": additions_path,
        "menu_scm_path": menu_scm_path,
        "needs_update": not has_load,
    }


def install_scheme_server() -> dict:
    """Install pqwave menu additions into lepton-eda's menu.scm.

    Copies menu-additions.scm to ~/.config/lepton-eda/ and appends a
    (load ...) line to the installed lepton-eda menu.scm. This is the
    same pattern as the built-in allegro backend: plain (define ...)
    functions referenced by symbol in add-menu.

    Caller is responsible for obtaining user consent before calling.
    Returns {"status": "ok", "menu_scm_path": str, "additions_path": str}
         or {"status": "error", "message": str}.
    """
    try:
        config_dir = _get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)

        # Copy menu-additions.scm to user config dir
        pkg_dir = Path(__file__).resolve().parent
        additions_src = str(pkg_dir / "menu-additions.scm")
        additions_dst = os.path.join(config_dir, "pqwave-menus.scm")
        shutil.copy2(additions_src, additions_dst)

        # Find the installed lepton-eda menu.scm
        menu_scm_path = _find_lepton_menu_scm()
        if not menu_scm_path:
            return {"status": "error",
                    "message": "Could not find lepton-eda menu.scm. Is lepton-eda installed?"}

        # Append load line if not already present
        load_line = f'(load "{additions_dst}")\n'
        with open(menu_scm_path, "r") as f:
            existing = f.read()
        if "pqwave-menus.scm" not in existing:
            with open(menu_scm_path, "a") as f:
                f.write("\n" + load_line)

        return {"status": "ok", "menu_scm_path": menu_scm_path,
                "additions_path": additions_dst}
    except OSError as e:
        return {"status": "error", "message": str(e)}


def _find_lepton_menu_scm() -> str | None:
    """Find the installed lepton-eda menu.scm file.

    Tries: 1) lepton-cli to query data dirs, 2) relative to
    lepton-schematic binary, 3) common install prefixes.
    """
    # Try via lepton-cli first
    for cli_name in ("lepton-cli",):
        cli_path = shutil.which(cli_name)
        if not cli_path:
            continue
        try:
            result = subprocess.run(
                [cli_path, "shell"],
                input='(display (lookup-sys-data-path "scheme/conf/schematic/menu.scm"))(force-output)\n',
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("/") and line.endswith("menu.scm"):
                    return line
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # Fallback: relative to lepton-schematic binary (<prefix>/bin/lepton-schematic
    # → <prefix>/share/lepton-eda/scheme/conf/schematic/menu.scm)
    schematic_bin = shutil.which("lepton-schematic")
    if schematic_bin:
        prefix = os.path.dirname(os.path.dirname(schematic_bin))
        candidate = os.path.join(prefix, "share", "lepton-eda",
                                 "scheme", "conf", "schematic", "menu.scm")
        if os.path.exists(candidate):
            return candidate

    # Common install locations
    for prefix in ("/usr", "/usr/local", os.path.expanduser("~/Apps/lepton-eda")):
        candidate = os.path.join(prefix, "share", "lepton-eda",
                                 "scheme", "conf", "schematic", "menu.scm")
        if os.path.exists(candidate):
            return candidate

    return None


class LeptonCrossProbeClient(QObject):
    """TCP client for pqwave-server.scm running inside lepton-schematic.

    Sends cross-probe and back-annotation commands. Receives reverse
    cross-probe events ($SELECTED:net / $SELECTED:part).

    Deployment: The companion script is copied to ~/.config/lepton-eda/
    and loaded via the user gafrc. This is lepton-eda's standard user
    extension mechanism (the system autoload at /usr/share/lepton-eda/
    scheme/autoload/ is for system-wide extensions only).

    Does NOT install automatically. The caller must check
    check_scheme_server() and call install_scheme_server() explicitly.

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
