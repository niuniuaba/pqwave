"""TCP client for pqwave-server.tcl running inside xschem.

Auto-deploys companion Tcl scripts on first use.  Does NOT modify
xschem C source code — purely additive Tcl via xschemrc.
"""

import os
import re
import shutil
import socket
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal


# ---- Path helpers ----

_THIS_DIR = Path(__file__).parent  # non-resolving: matches pip-installed layout


def _get_package_tcl_path(name: str = "pqwave-server.tcl") -> str:
    """Return the path to a Tcl script alongside this module."""
    return str(_THIS_DIR / name)


def _get_xschem_config_dir() -> str:
    """Return the xschem user config directory (~/.xschem)."""
    return os.path.join(os.path.expanduser("~"), ".xschem")


def _get_tcl_target_path(name: str = "pqwave-server.tcl") -> str:
    """Return the target path for a Tcl script in user config."""
    return os.path.join(_get_xschem_config_dir(), name)


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


# ---- Tcl scripts deployed to ~/.xschem/ ----

_TCL_SCRIPTS = [
    {
        "name": "pqwave-server.tcl",
        "description": "cross-probe server",
        # Match the actual lappend line, not just a substring mention.
        "xschemrc_re": re.compile(
            r"^\s*lappend\s+tcl_files\s+.*pqwave-server\.tcl", re.MULTILINE
        ),
        "xschemrc_line": "lappend tcl_files ~/.xschem/pqwave-server.tcl\n",
    },
    {
        "name": "pqwave_override.tcl",
        "description": "Alt+G wave push override",
        # Match a user_startup_commands or source line referencing this file.
        "xschemrc_re": re.compile(
            r"(?:user_startup_commands|source\b).*pqwave_override\.tcl",
            re.MULTILINE,
        ),
        "xschemrc_line": (
            "set user_startup_commands"
            ' { source $env(HOME)/.xschem/pqwave_override.tcl }\n'
        ),
    },
]


# ---- Check / Deploy ----

def check_tcl_server() -> dict:
    """Check whether pqwave Tcl scripts are installed in ~/.xschem/.

    Returns dict with keys:
        installed: bool
        needs_deploy: bool — files missing or outdated
        missing: list[str] — names of scripts that need deployment
    """
    xschemrc_path = _get_xschemrc_path()
    xschemrc_content = ""
    if os.path.exists(xschemrc_path):
        with open(xschemrc_path, "r") as f:
            xschemrc_content = f.read()

    missing = []
    for script in _TCL_SCRIPTS:
        target = _get_tcl_target_path(script["name"])
        file_ok = os.path.exists(target)
        rc_ok = bool(script["xschemrc_re"].search(xschemrc_content))

        if not file_ok or not rc_ok:
            missing.append(script["name"])
            continue

        # Check version — redeploy if bundled is newer
        src_ver = _extract_tcl_version(_get_package_tcl_path(script["name"]))
        installed_ver = _extract_tcl_version(target)
        if installed_ver < src_ver:
            missing.append(script["name"])

    return {
        "installed": len(missing) == 0,
        "needs_deploy": len(missing) > 0,
        "missing": missing,
        "xschemrc_path": xschemrc_path,
    }


def deploy_tcl_server() -> dict:
    """Deploy Tcl scripts to ~/.xschem/ and configure xschemrc.

    Copies both pqwave-server.tcl and pqwave_override.tcl from
    pqwave/bridge/xschem/ to ~/.xschem/, then ensures xschemrc
    has the required load lines.

    Returns {"status": "ok"} or {"status": "error", "message": str}.
    """
    try:
        config_dir = _get_xschem_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        xschemrc = _get_xschemrc_path()
        os.makedirs(os.path.dirname(xschemrc), exist_ok=True)

        # Read existing xschemrc content
        xschemrc_content = ""
        if os.path.exists(xschemrc):
            with open(xschemrc, "r") as f:
                xschemrc_content = f.read()

        deployed = []
        for script in _TCL_SCRIPTS:
            # Copy the Tcl script
            src = _get_package_tcl_path(script["name"])
            dst = _get_tcl_target_path(script["name"])
            shutil.copy2(src, dst)
            deployed.append(dst)

            # Ensure xschemrc has the load line
            if not script["xschemrc_re"].search(xschemrc_content):
                with open(xschemrc, "a") as f:
                    f.write(f"\n# pqwave {script['description']}\n"
                            f"{script['xschemrc_line']}")
                xschemrc_content += script["xschemrc_line"]

        return {"status": "ok", "deployed": deployed, "xschemrc_path": xschemrc}
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
