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


def _check_guile_cache_stale(scm_path: str) -> bool:
    """Return True if *scm_path* has no compiled ``.go`` cache or the
    ``.go`` is older than the ``.scm`` source.

    Guile auto-compiles ``.scm`` files to ``~/.cache/guile/ccache/...``
    on first load.  If the source is edited but lepton-schematic is not
    restarted, it keeps running the stale ``.go`` bytecode.
    """
    try:
        scm_mtime = os.path.getmtime(scm_path)
    except OSError:
        return False  # source doesn't exist — nothing to check

    cache_root = os.path.expanduser(
        "~/.cache/guile/ccache/3.0-LE-8-4.7")
    scm_abs = os.path.abspath(scm_path)
    go_path = os.path.join(cache_root, scm_abs.lstrip("/") + ".go")

    try:
        go_mtime = os.path.getmtime(go_path)
        return scm_mtime > go_mtime
    except OSError:
        # No .go file at all — source was never compiled, or cache was
        # cleared.  Not stale (will be compiled on next load).
        return False


def _extract_scm_version(path: str) -> int:
    """Extract VERSION number from a .scm file. Returns 0 if not found."""
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith(";; VERSION:"):
                    return int(line.split(":")[1].strip())
    except (OSError, ValueError):
        pass
    return 0


def check_scheme_server() -> dict:
    """Check whether pqwave menu additions and TCP server are installed.

    Returns a dict with keys:
        installed: bool
        additions_path: str  — path to pqwave-menus.scm in user config
        server_scm_path: str — path to pqwave-server.scm in user config
        menu_scm_path: str | None (None if lepton-eda not found)
        needs_update: bool  — True if files need (re)install or update
    """
    config_dir = _get_user_config_dir()
    additions_path = os.path.join(config_dir, "pqwave-menus.scm")
    server_scm_path = os.path.join(config_dir, "pqwave-server.scm")
    menu_scm_path = _find_lepton_menu_scm()
    if not menu_scm_path:
        return {
            "installed": False,
            "additions_path": additions_path,
            "server_scm_path": server_scm_path,
            "menu_scm_path": None,
            "needs_update": False,
        }
    if not os.path.exists(additions_path) or not os.path.exists(server_scm_path):
        return {
            "installed": False,
            "additions_path": additions_path,
            "server_scm_path": server_scm_path,
            "menu_scm_path": menu_scm_path,
            "needs_update": True,
        }
    # Check menu.scm for menu additions, gafrc for TCP server.
    # The server must only be loaded from ONE place (gafrc) to avoid
    # double-loading and spawning duplicate TCP server threads.
    gafrc_path = os.path.join(config_dir, "gafrc")
    with open(menu_scm_path, "r") as f:
        content = f.read()
        has_menus = "pqwave-menus.scm" in content
    has_server = False
    if os.path.exists(gafrc_path):
        with open(gafrc_path) as f:
            has_server = "pqwave-server.scm" in f.read()
    if not has_menus or not has_server:
        return {
            "installed": False,
            "additions_path": additions_path,
            "server_scm_path": server_scm_path,
            "menu_scm_path": menu_scm_path,
            "needs_update": True,
        }
    # Check if installed files are outdated vs current source.
    # Compare both files — update if either source is newer.
    pkg_dir = Path(__file__).resolve().parent
    src_menu_v = _extract_scm_version(str(pkg_dir / "menu-additions.scm"))
    src_server_v = _extract_scm_version(str(pkg_dir / "pqwave-server.scm"))
    installed_menu_v = _extract_scm_version(additions_path)
    installed_server_v = _extract_scm_version(server_scm_path)
    needs_update = (installed_menu_v < src_menu_v or
                    installed_server_v < src_server_v)
    guile_cache_stale = (
        _check_guile_cache_stale(server_scm_path)
        or _check_guile_cache_stale(additions_path)
    )
    return {
        "installed": True,
        "additions_path": additions_path,
        "server_scm_path": server_scm_path,
        "menu_scm_path": menu_scm_path,
        "needs_update": needs_update,
        "guile_cache_stale": guile_cache_stale,
    }


def install_scheme_server() -> dict:
    """Install pqwave menu additions and TCP server into lepton-eda's menu.scm.

    Copies menu-additions.scm and pqwave-server.scm to ~/.config/lepton-eda/
    and appends (load ...) lines to the installed menu.scm.

    Caller is responsible for obtaining user consent before calling.
    Returns {"status": "ok", "menu_scm_path": str, "additions_path": str,
             "server_scm_path": str}
         or {"status": "error", "message": str}.
    """
    try:
        config_dir = _get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)

        pkg_dir = Path(__file__).resolve().parent

        # Copy menu-additions.scm
        additions_src = str(pkg_dir / "menu-additions.scm")
        additions_dst = os.path.join(config_dir, "pqwave-menus.scm")
        shutil.copy2(additions_src, additions_dst)

        # Copy pqwave-server.scm
        server_src = str(pkg_dir / "pqwave-server.scm")
        server_dst = os.path.join(config_dir, "pqwave-server.scm")
        shutil.copy2(server_src, server_dst)

        # Find the installed lepton-eda menu.scm
        menu_scm_path = _find_lepton_menu_scm()
        if not menu_scm_path:
            return {"status": "error",
                    "message": "Could not find lepton-eda menu.scm. Is lepton-eda installed?"}

        with open(menu_scm_path, "r") as f:
            existing = f.read()

        # Only add menu additions to menu.scm.  The TCP server is loaded
        # exclusively from gafrc — loading it from menu.scm as well would
        # spawn duplicate server threads.
        lines_to_add = []
        if "pqwave-menus.scm" not in existing:
            lines_to_add.append(f'(load "{additions_dst}")')

        if lines_to_add:
            with open(menu_scm_path, "a") as f:
                f.write("\n" + "\n".join(lines_to_add) + "\n")

        # Write/update gafrc to load the TCP server on startup.
        # Menu additions are already loaded via menu.scm (above) —
        # loading them from gschemrc as well would insert duplicate menus.
        gafrc_path = os.path.join(config_dir, "gafrc")
        server_line = f'(load "{server_dst}")\n'
        _already_configured = False
        if os.path.exists(gafrc_path):
            with open(gafrc_path) as f:
                _already_configured = "pqwave-server.scm" in f.read()
        if not _already_configured:
            with open(gafrc_path, "a") as f:
                f.write("\n;; pqwave bridge\n" + server_line)

        return {"status": "ok", "menu_scm_path": menu_scm_path,
                "additions_path": additions_dst, "server_scm_path": server_dst}
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

    Deployment: menu-additions.scm and pqwave-server.scm are copied to
    ~/.config/lepton-eda/ and loaded via (load ...) lines appended to
    lepton-eda's installed menu.scm.

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
    schematic_path = pyqtSignal(str)

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
            # Disable timeout after connect — the reader thread blocks on recv
            # indefinitely waiting for reverse cross-probe events from the server.
            self._sock.settimeout(None)
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
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

    def send_command(self, text: str) -> bool:
        sock = self._sock  # snapshot to avoid TOCTOU with _read_loop
        if not sock:
            self.error_occurred.emit("Not connected to lepton-schematic")
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

    def _read_loop(self):
        buf = b""
        while self._running:
            sock = self._sock  # snapshot to avoid TOCTOU with disconnect()
            if not sock:
                break
            try:
                data = sock.recv(4096)
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
        elif msg.startswith("$SCHEMATIC:"):
            self.schematic_path.emit(msg[11:].strip())
        else:
            self.error_occurred.emit(f"Unknown message from server: {msg[:80]}")
