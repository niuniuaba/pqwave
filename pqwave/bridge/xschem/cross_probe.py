"""TCP client for pqwave-server.tcl running inside xschem.

Auto-deploys the companion Tcl script on first use. Does NOT modify
xschem C source code — purely additive Tcl via xschemrc.
"""

import os
import shutil
import socket
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


# ---- Path helpers ----

def _get_package_tcl_path() -> str:
    """Return the path to pqwave-server.tcl inside the pqwave package."""
    pkg_dir = Path(__file__).resolve().parents[3]  # pqwave/bridge/xschem → pqwave/
    return str(pkg_dir / "share" / "pqwave-server.tcl")


def _get_xschem_config_dir() -> str:
    """Return the xschem user config directory (~/.config/xschem)."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(xdg_config, "xschem")


def _get_tcl_target_path() -> str:
    """Return the target path for pqwave-server.tcl in user config."""
    return os.path.join(_get_xschem_config_dir(), "pqwave-server.tcl")


def _get_xschemrc_path() -> str:
    """Return the path to the user xschemrc."""
    return os.path.join(os.path.expanduser("~"), ".xschem", "xschemrc")


def _extract_tcl_version(path: str) -> int:
    """Extract VERSION number from the Tcl script. Returns 0 if not found."""
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith("# VERSION:"):
                    return int(line.split(":")[1].strip())
    except (OSError, ValueError):
        pass
    return 0


# ---- Check / Deploy ----

def check_tcl_server() -> dict:
    """Check whether pqwave-server.tcl is installed and configured.

    Returns dict with keys:
        installed: bool
        server_script_ok: bool — the .tcl file exists
        xschemrc_configured: bool — xschemrc has the lappend line
        needs_deploy: bool — files need deployment
        target_path: str
        xschemrc_path: str
    """
    target_path = _get_tcl_target_path()
    xschemrc_path = _get_xschemrc_path()
    server_script_ok = os.path.exists(target_path)
    xschemrc_configured = False

    if os.path.exists(xschemrc_path):
        with open(xschemrc_path, "r") as f:
            content = f.read()
            xschemrc_configured = "pqwave-server.tcl" in content

    installed = server_script_ok and xschemrc_configured
    needs_deploy = not installed

    # Check if deployed script is outdated
    if server_script_ok:
        src_ver = _extract_tcl_version(_get_package_tcl_path())
        installed_ver = _extract_tcl_version(target_path)
        if installed_ver < src_ver:
            needs_deploy = True

    return {
        "installed": installed,
        "server_script_ok": server_script_ok,
        "xschemrc_configured": xschemrc_configured,
        "needs_deploy": needs_deploy,
        "target_path": target_path,
        "xschemrc_path": xschemrc_path,
    }


def deploy_tcl_server() -> dict:
    """Deploy pqwave-server.tcl to ~/.config/xschem/ and configure xschemrc.

    Returns {"status": "ok"} or {"status": "error", "message": str}.
    """
    try:
        config_dir = _get_xschem_config_dir()
        os.makedirs(config_dir, exist_ok=True)

        # Copy Tcl script
        src = _get_package_tcl_path()
        dst = _get_tcl_target_path()
        shutil.copy2(src, dst)

        # Ensure xschemrc exists and has the load line
        xschemrc = _get_xschemrc_path()
        os.makedirs(os.path.dirname(xschemrc), exist_ok=True)

        load_line = "lappend tcl_files ~/.config/xschem/pqwave-server.tcl\n"

        if os.path.exists(xschemrc):
            with open(xschemrc, "r") as f:
                content = f.read()
            if "pqwave-server.tcl" not in content:
                with open(xschemrc, "a") as f:
                    f.write(f"\n# pqwave cross-probe server\n{load_line}")
        else:
            with open(xschemrc, "w") as f:
                f.write(f"# xschemrc — created by pqwave\n{load_line}")

        return {"status": "ok", "target_path": dst, "xschemrc_path": xschemrc}
    except OSError as e:
        return {"status": "error", "message": str(e)}


# ---- Client ----

class XschemCrossProbeClient(QObject):
    """TCP client for pqwave-server.tcl running inside xschem.

    Sends cross-probe commands. Unlike the Lepton client, this does
    NOT support reverse cross-probe ($SELECTED:* events) because
    xschem's Alt+G push workflow uses the separate WaveReceiver channel.

    Signals:
        connected():          TCP connection established
        disconnected():       TCP connection closed
        error_occurred(str):  connection or send error message
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, port: int = 2021, timeout: float = 2.0):
        super().__init__()
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None
        self._running = False

    def is_connected(self) -> bool:
        return self._sock is not None

    def connect_to_server(self) -> bool:
        """Open TCP connection to localhost:port. Returns True on success."""
        try:
            self._sock = socket.create_connection(
                ("localhost", self._port), timeout=self._timeout
            )
            self._sock.settimeout(None)
            self._running = True
            self.connected.emit()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self.error_occurred.emit(
                f"xschem not running or pqwave server not active "
                f"on localhost:{self._port}: {e}"
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
        sock = self._sock
        if not sock:
            self.error_occurred.emit("Not connected to xschem")
            return False
        try:
            msg = text.rstrip("\n") + "\n"
            sock.sendall(msg.encode("utf-8"))
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
