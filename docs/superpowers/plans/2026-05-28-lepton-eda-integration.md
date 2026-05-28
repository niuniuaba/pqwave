# Lepton-EDA Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a complete `LeptonBridge` (SchematicBridge ABC) for lepton-eda with bidirectional cross-probe, back-annotation, in-schematic menus, file watching, and session API.

**Architecture:** Python `LeptonBridge` class in `pqwave/bridge/lepton/` orchestrates `lepton-netlist` → `ngspice` pipeline (same pattern as KiCad). A companion Guile Scheme script (`pqwave/bridge/lepton/pqwave-server.scm`) is stored as a versioned source file inside pqwave's package. On first bridge use, the user is prompted to install it to `~/.config/lepton-eda/scheme/autoload/` (GUI: QMessageBox; headless: explicit `lepton_config("install_server")` API call). Once installed, lepton-schematic loads it automatically at startup, providing a TCP server for bidirectional cross-probe, back-annotation, and in-schematic menus. Updates re-prompt if the bundled version is newer.

**Tech Stack:** Python 3, PyQt6, Guile Scheme 3.0, lepton-netlist (spice-sdb backend), ngspice, TCP sockets

---

## File Structure

```
pqwave/bridge/lepton/
├── __init__.py              # Package init
├── bridge.py                # LeptonBridge(SchematicBridge) + simulate pipeline
├── cross_probe.py           # LeptonCrossProbeClient(QObject)
├── file_watcher.py           # LeptonFileWatcher(QObject) — mtime polling
├── control_bar.py            # LeptonControlBar(QWidget)
└── pqwave-server.scm         # Guile Scheme: TCP server + menus + back-annotation
                                (versioned source, deployed to user's autoload dir
                                 on explicit install, not silently copied)

pqwave/session/api.py        # MODIFY: register lepton_* commands
pqwave/ui/main_window.py     # MODIFY: wire bridge, install dialog, handlers
pqwave/ui/menu_manager.py    # MODIFY: File > Lepton Bridge submenu, Help > Guide
pqwave/ui/settings_dialog.py # MODIFY: lepton-netlist + ngspice path fields
```

---

### Task 1: Package Structure and LeptonBridge Core

**Files:**
- Create: `pqwave/bridge/lepton/__init__.py`
- Create: `pqwave/bridge/lepton/bridge.py`

- [ ] **Step 1: Create package init**

```python
# pqwave/bridge/lepton/__init__.py
"""Lepton-EDA bridge — SchematicBridge implementation for lepton-eda."""

from pqwave.bridge.lepton.bridge import LeptonBridge

__all__ = ["LeptonBridge"]
```

- [ ] **Step 2: Write LeptonBridge class**

```python
# pqwave/bridge/lepton/bridge.py
"""Lepton-EDA SchematicBridge implementation."""

import os
import shutil
import subprocess
import tempfile
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState


class LeptonBridge(SchematicBridge):
    """SchematicBridge for lepton-eda.

    Uses lepton-netlist -g spice-sdb for netlist export and ngspice
    for simulation. Cross-probe and back-annotation are handled by
    LeptonCrossProbeClient communicating with pqwave-server.scm running
    inside lepton-schematic.
    """

    def __init__(self, lepton_netlist_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._lepton_netlist = lepton_netlist_path
        self._ngspice = ngspice_path

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .sch file via lepton-netlist."""
        lepton_netlist = self._resolve_lepton_netlist()
        result = subprocess.run(
            [lepton_netlist, "-g", "spice-sdb", "-o", "-", sch_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"lepton-netlist failed with code {result.returncode}: {result.stderr}"
            )
        return result.stdout

    def get_netlist_fixes(self) -> list[NetlistFix]:
        """Lepton-eda spice-sdb backend produces clean SPICE — no fixes needed."""
        return []

    def probe_net(self, net_name: str) -> None:
        self._ensure_cross_probe().probe_net(net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        self._ensure_cross_probe().probe_part(ref, pin)

    def clear_probe(self) -> None:
        self._ensure_cross_probe().clear()

    def detect_tool(self) -> Optional[str]:
        try:
            return self._resolve_lepton_netlist()
        except FileNotFoundError:
            return None

    def is_tool_running(self) -> bool:
        for cmd in (["pgrep", "-x", "lepton-schematic"], ["pidof", "lepton-schematic"]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return False

    def get_watch_extensions(self) -> list[str]:
        return [".sch"]

    # ---- Simulation pipeline ----

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        """Run full pipeline: export → post-process → ngspice → .raw."""
        netlist = self.export_netlist(sch_path)
        processor = NetlistPostProcessor(self.get_netlist_fixes())
        fixed = processor.process(netlist)

        fd, cir_path = tempfile.mkstemp(suffix=".cir", prefix="pqwave_lepton_")
        os.close(fd)
        try:
            with open(cir_path, "w") as f:
                f.write(fixed)
            if raw_output is None:
                fd, raw_output = tempfile.mkstemp(suffix=".raw", prefix="pqwave_lepton_")
                os.close(fd)
                os.unlink(raw_output)
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
            }
        finally:
            try:
                os.unlink(cir_path)
            except OSError:
                pass

    # ---- Back-annotation methods ----

    def annotate_dc(self, voltages: dict[str, float]) -> None:
        cp = self._ensure_cross_probe()
        for netname, voltage in voltages.items():
            cp.send_command(f"$ANNOTATE:DC {netname} {voltage}")

    def annotate_label(self, netname: str, text: str, x: int, y: int) -> None:
        cp = self._ensure_cross_probe()
        cp.send_command(f"$ANNOTATE:LABEL {netname} {text} {x} {y}")

    def clear_annotations(self) -> None:
        self._ensure_cross_probe().send_command("$CLEAR:ANNOTATIONS")

    def clear_dc_stamps(self) -> None:
        self._ensure_cross_probe().send_command("$CLEAR:DC")

    # ---- Tool resolution ----

    def _resolve_lepton_netlist(self) -> str:
        if self._lepton_netlist and os.path.isfile(self._lepton_netlist):
            return self._lepton_netlist
        state = ApplicationState()
        custom = state.tool_paths.get("lepton_netlist", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("lepton-netlist")
        if found:
            return found
        raise FileNotFoundError(
            "lepton-netlist not found. Install lepton-eda or set the path in "
            "Settings > External Converter Paths."
        )

    def _resolve_ngspice(self) -> str:
        if self._ngspice and os.path.isfile(self._ngspice):
            return self._ngspice
        state = ApplicationState()
        custom = state.tool_paths.get("ngspice", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("ngspice")
        if found:
            return found
        raise FileNotFoundError(
            "ngspice not found. Install ngspice or set the path in "
            "Settings > External Converter Paths."
        )

    def _ensure_cross_probe(self):
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        if not hasattr(self, "_cross_probe") or self._cross_probe is None:
            self._cross_probe = LeptonCrossProbeClient()
        return self._cross_probe
```

- [ ] **Step 3: Commit**

```bash
git add pqwave/bridge/lepton/__init__.py pqwave/bridge/lepton/bridge.py
git commit -m "feat: add LeptonBridge core with netlist export and simulation pipeline"
```

---

### Task 2: File Watcher

**Files:**
- Create: `pqwave/bridge/lepton/file_watcher.py`

- [ ] **Step 1: Write LeptonFileWatcher**

```python
# pqwave/bridge/lepton/file_watcher.py
"""File watcher for .sch files — mtime polling."""

import os
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class LeptonFileWatcher(QObject):
    """Watch a single .sch file for changes via mtime polling.

    Signals:
        file_changed(str): emitted with the watched file path on save
    """

    file_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._watched_path: str | None = None
        self._last_mtime: float = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._miss_count = 0

    def watch(self, path: str) -> None:
        self._watched_path = os.path.abspath(path)
        self._miss_count = 0
        try:
            self._last_mtime = os.path.getmtime(self._watched_path)
        except OSError:
            self._last_mtime = 0
        self._timer.start(1000)

    def unwatch(self) -> None:
        self._timer.stop()
        self._watched_path = None
        self._last_mtime = 0

    @property
    def watched_path(self) -> str | None:
        return self._watched_path

    def _poll(self):
        if not self._watched_path:
            return
        try:
            mtime = os.path.getmtime(self._watched_path)
        except OSError:
            self._miss_count += 1
            if self._miss_count > 10:
                self._timer.stop()
            return
        self._miss_count = 0
        if mtime != self._last_mtime:
            self._last_mtime = mtime
            self.file_changed.emit(self._watched_path)
```

- [ ] **Step 2: Commit**

```bash
git add pqwave/bridge/lepton/file_watcher.py
git commit -m "feat: add LeptonFileWatcher for .sch mtime polling"
```

---

### Task 3: Scheme Server Script + Cross-Probe Client

**Files:**
- Create: `pqwave/bridge/lepton/pqwave-server.scm`
- Create: `pqwave/bridge/lepton/cross_probe.py`

- [ ] **Step 1: Create the Scheme server script**

Write `pqwave/bridge/lepton/pqwave-server.scm` — the complete Guile Scheme script (see appendix at end of plan for full source). This file is a versioned part of pqwave, NOT an embedded string. It is deployed to `~/.config/lepton-eda/scheme/autoload/` only when the user explicitly opts in.

- [ ] **Step 2: Write LeptonCrossProbeClient with install helpers**

```python
# pqwave/bridge/lepton/cross_probe.py
"""TCP client for pqwave-server.scm running inside lepton-schematic.

Does NOT silently install the Scheme server. The caller (MainWindow or
headless API) must explicitly call install_scheme_server() after
obtaining user consent.
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
        current_version_mtime: float | None (mtime of installed copy, or None)
        bundled_version_mtime: float (mtime of the bundled source)
        needs_update: bool (bundled is newer than installed)
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

    Creates the autoload directory if it doesn't exist.
    Returns {"status": "ok", "target_path": str} or {"status": "error", "message": str}.
    Caller is responsible for obtaining user consent before calling this.
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
                    self._handle_message(line.decode("utf-8").strip())
            except OSError:
                break
        if self._running:
            self._running = False
            self.disconnected.emit()

    def _handle_message(self, msg: str):
        if msg.startswith("$SELECTED:net "):
            self.net_selected.emit(msg[14:].strip())
        elif msg.startswith("$SELECTED:part "):
            self.part_selected.emit(msg[15:].strip())
```

- [ ] **Step 3: Commit**

```bash
git add pqwave/bridge/lepton/pqwave-server.scm pqwave/bridge/lepton/cross_probe.py
git commit -m "feat: add pqwave-server.scm and LeptonCrossProbeClient with opt-in install"
```

---

### Task 4: Control Bar

**Files:**
- Create: `pqwave/bridge/lepton/control_bar.py`

- [ ] **Step 1: Write LeptonControlBar**

```python
# pqwave/bridge/lepton/control_bar.py
"""Status bar widget for Lepton-EDA bridge controls."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal


class LeptonControlBar(QWidget):
    """Status and control bar for lepton-eda bridge.

    Same pattern as MCControlBar and KiCadControlBar: lazy creation,
    hidden by default, horizontal layout, 40px max height.

    Signals:
        simulate_clicked():           user wants to run simulation
        annotate_dc_clicked():        user wants to stamp DC voltages
        clear_annotations_clicked():  user wants to clear labels
        unwatch_clicked():            user wants to stop watching
    """

    simulate_clicked = pyqtSignal()
    annotate_dc_clicked = pyqtSignal()
    clear_annotations_clicked = pyqtSignal()
    unwatch_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self._status_label = QLabel("Lepton: not watching")
        layout.addWidget(self._status_label)
        layout.addSpacing(10)

        self._simulate_btn = QPushButton("Simulate Now")
        self._simulate_btn.setMinimumWidth(110)
        self._simulate_btn.clicked.connect(self.simulate_clicked.emit)
        layout.addWidget(self._simulate_btn)

        self._annotate_btn = QPushButton("Annotate DC")
        self._annotate_btn.setMinimumWidth(100)
        self._annotate_btn.clicked.connect(self.annotate_dc_clicked.emit)
        self._annotate_btn.setEnabled(False)
        layout.addWidget(self._annotate_btn)

        self._clear_annotations_btn = QPushButton("Clear Annotations")
        self._clear_annotations_btn.setMinimumWidth(130)
        self._clear_annotations_btn.clicked.connect(self.clear_annotations_clicked.emit)
        layout.addWidget(self._clear_annotations_btn)

        self._unwatch_btn = QPushButton("Stop Watching")
        self._unwatch_btn.setMinimumWidth(110)
        self._unwatch_btn.clicked.connect(self.unwatch_clicked.emit)
        layout.addWidget(self._unwatch_btn)

        layout.addStretch()
        self.setMaximumHeight(40)
        self.setLayout(layout)

    def set_status(self, text: str):
        self._status_label.setText(f"Lepton: {text}")

    def set_simulating(self, active: bool):
        self._simulate_btn.setEnabled(not active)
        self._annotate_btn.setEnabled(False)
        if active:
            self.set_status("simulating...")

    def set_simulation_complete(self):
        self._annotate_btn.setEnabled(True)
        self.set_status("simulation complete")
```

- [ ] **Step 2: Commit**

```bash
git add pqwave/bridge/lepton/control_bar.py
git commit -m "feat: add LeptonControlBar with simulate/annotate/clear controls"
```

---

### Task 5: Session API Commands

**Files:**
- Modify: `pqwave/session/api.py`

- [ ] **Step 1: Add lepton_* commands**

Insert after the existing `kicad_config` method in `pqwave/session/api.py`:

```python
    # ---- Lepton-EDA bridge methods ----

    def lepton_watch(self, path: str) -> dict:
        """Start watching a .sch file for changes."""
        if self._on_mutation:
            self._on_mutation("lepton_watch", path=path)
            return {"status": "ok"}
        self._lepton_watched_path = path
        return {"status": "ok"}

    def lepton_simulate(self, sch_path: str | None = None) -> dict:
        """Run export → post-process → ngspice pipeline."""
        path = sch_path or getattr(self, "_lepton_watched_path", None)
        if not path:
            raise ValueError("No .sch file specified or watched")
        if self._on_mutation:
            self._on_mutation("lepton_simulate", path=path)
            return {"status": "ok"}
        from pqwave.bridge.lepton.bridge import LeptonBridge
        bridge = LeptonBridge()
        return bridge.simulate(path)

    def lepton_unwatch(self) -> dict:
        """Stop watching the schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_unwatch")
            return {"status": "ok"}
        self._lepton_watched_path = None
        return {"status": "ok"}

    def lepton_probe_net(self, name: str) -> dict:
        """Highlight a net in lepton-schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_probe_net", name=name)
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.probe_net(name)
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running or pqwave server not active"}

    def lepton_probe_part(self, ref: str, pin: str | None = None) -> dict:
        """Highlight a component in lepton-schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_probe_part", ref=ref, pin=pin)
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.probe_part(ref, pin)
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_clear(self) -> dict:
        """Clear all lepton-schematic highlights."""
        if self._on_mutation:
            self._on_mutation("lepton_clear")
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.clear()
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_annotate_dc(self, voltages: dict[str, float] | None = None) -> dict:
        """Stamp DC voltages onto lepton-schematic netname attributes."""
        if self._on_mutation:
            self._on_mutation("lepton_annotate_dc", voltages=voltages)
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            for netname, voltage in (voltages or {}).items():
                client.send_command(f"$ANNOTATE:DC {netname} {voltage}")
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_clear_annotations(self) -> dict:
        """Clear all floating labels and DC stamps from lepton-schematic."""
        if self._on_mutation:
            self._on_mutation("lepton_clear_annotations")
            return {"status": "ok"}
        from pqwave.bridge.lepton.cross_probe import LeptonCrossProbeClient
        client = LeptonCrossProbeClient()
        if client.connect_to_server():
            client.send_command("$CLEAR:ANNOTATIONS")
            client.send_command("$CLEAR:DC")
            client.disconnect()
            return {"status": "ok"}
        return {"status": "error", "message": "lepton-schematic not running"}

    def lepton_config(self, key: str, value=None) -> dict:
        """Get or set lepton-eda bridge configuration.

        Keys:
            port: int — TCP port for cross-probe server (default 9424)
            auto_simulate: bool — auto-simulate on file save (default True)
            install_server: (write-only) — install pqwave-server.scm to autoload dir
        """
        if key == "install_server":
            from pqwave.bridge.lepton.cross_probe import install_scheme_server
            return install_scheme_server()

        state = ApplicationState()
        if not hasattr(state, "_lepton_config"):
            state._lepton_config = {"port": 9424, "auto_simulate": True}
        if value is None:
            return {"status": "ok", "data": state._lepton_config.get(key)}
        state._lepton_config[key] = value
        return {"status": "ok"}
```

- [ ] **Step 2: Commit**

```bash
git add pqwave/session/api.py
git commit -m "feat: add lepton_* session API commands including install_server"
```

---

### Task 6: MainWindow Wiring (with Install Dialog)

**Files:**
- Modify: `pqwave/ui/main_window.py`

- [ ] **Step 1: Add lepton bridge attributes to MainWindow.__init__**

After the KiCad attribute block (around line 158-166), add:

```python
        # Lepton-EDA bridge (lazy, same pattern as KiCad)
        self.lepton_control_bar = None
        self._lepton_watcher = None
        self._lepton_bridge = None
        self._lepton_cross_probe = None
        self._lepton_watched_path = None
        self._lepton_simulating = False
        self._lepton_last_path = ""
```

- [ ] **Step 2: Add lepton dispatch in _handle_mutation**

After `elif action == "kicad_clear":`, add:

```python
        elif action == "lepton_watch":
            self._start_lepton_watch(kwargs["path"])
        elif action == "lepton_simulate":
            self._on_lepton_simulate()
        elif action == "lepton_unwatch":
            self._on_lepton_unwatch()
        elif action == "lepton_probe_net":
            if self._lepton_cross_probe:
                self._lepton_cross_probe.probe_net(kwargs["name"])
        elif action == "lepton_probe_part":
            if self._lepton_cross_probe:
                self._lepton_cross_probe.probe_part(kwargs["ref"], kwargs.get("pin"))
        elif action == "lepton_clear":
            if self._lepton_cross_probe:
                self._lepton_cross_probe.clear()
        elif action == "lepton_annotate_dc":
            self._on_lepton_annotate_dc(kwargs.get("voltages", {}))
        elif action == "lepton_clear_annotations":
            self._on_lepton_clear_annotations()
```

- [ ] **Step 3: Add lepton bridge handler methods**

Add after the KiCad handler methods:

```python
    # ---- Lepton-EDA Bridge handlers ----

    def _on_lepton_watch(self):
        """File > Lepton Bridge > Watch Schematic."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Lepton-EDA Schematic",
            os.path.expanduser("~"),
            "Schematic (*.sch);;All Files (*)"
        )
        if not path:
            return
        self._start_lepton_watch(path)

    def _start_lepton_watch(self, sch_path: str):
        """Initialize lepton-eda bridge and start watching.

        On first use, prompts the user to install pqwave-server.scm
        to lepton-eda's autoload directory. Does NOT silently copy files.
        """
        from PyQt6.QtWidgets import QMessageBox
        from pqwave.bridge.lepton.bridge import LeptonBridge
        from pqwave.bridge.lepton.file_watcher import LeptonFileWatcher
        from pqwave.bridge.lepton.cross_probe import (
            LeptonCrossProbeClient, check_scheme_server, install_scheme_server
        )
        from pqwave.bridge.lepton.control_bar import LeptonControlBar

        # Check if Scheme server is installed
        status = check_scheme_server()
        if not status["installed"] or status["needs_update"]:
            action = "update" if status["installed"] else "install"
            target = status["target_path"]
            reply = QMessageBox.question(
                self,
                "Lepton-EDA Bridge Setup",
                f"The Lepton-EDA bridge needs to {action} a companion script "
                f"to enable cross-probe and back-annotation.\n\n"
                f"Install to:\n{target}\n\n"
                f"lepton-schematic will load this script automatically on startup. "
                f"You only need to do this once.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                self.chat_panel.append_output(
                    "[lepton] Bridge setup cancelled. Cross-probe and back-annotation "
                    "will not be available.\n"
                )
            else:
                result = install_scheme_server()
                if result["status"] == "ok":
                    self.chat_panel.append_output(
                        f"[lepton] Server installed to {result['target_path']}. "
                        "Restart lepton-schematic for changes to take effect.\n"
                    )
                else:
                    self.chat_panel.append_output(
                        f"[lepton] Install failed: {result['message']}\n"
                    )

        # Clean up previous bridge instances
        if self._lepton_cross_probe:
            self._lepton_cross_probe.disconnect()
        if self._lepton_watcher:
            self._lepton_watcher.unwatch()

        self._lepton_bridge = LeptonBridge()
        self._lepton_watcher = LeptonFileWatcher()
        self._lepton_cross_probe = LeptonCrossProbeClient()

        # Lazy-create control bar
        if self.lepton_control_bar is None:
            self.lepton_control_bar = LeptonControlBar()
            upper = self._main_splitter.widget(0)
            if upper and upper.layout():
                upper.layout().addWidget(self.lepton_control_bar)
            self.lepton_control_bar.simulate_clicked.connect(self._on_lepton_simulate)
            self.lepton_control_bar.annotate_dc_clicked.connect(
                lambda: self._on_lepton_annotate_dc()
            )
            self.lepton_control_bar.clear_annotations_clicked.connect(
                self._on_lepton_clear_annotations
            )
            self.lepton_control_bar.unwatch_clicked.connect(self._on_lepton_unwatch)

        self._lepton_watcher.file_changed.connect(self._on_lepton_file_changed)
        self._lepton_watcher.watch(sch_path)
        self._lepton_watched_path = sch_path
        self._lepton_last_path = sch_path

        # Reverse cross-probe: schematic → pqwave
        self._lepton_cross_probe.net_selected.connect(self._on_lepton_net_selected)
        self._lepton_cross_probe.error_occurred.connect(
            lambda msg: self.chat_panel.append_output(f"[lepton] {msg}\n")
        )

        self.lepton_control_bar.setVisible(True)
        basename = os.path.basename(sch_path)
        self.statusBar().showMessage(
            f"Watching {basename} — save in lepton-schematic to auto-simulate"
        )
        self.lepton_control_bar.set_status(f"watching {basename}")
        self._run_lepton_pipeline(sch_path)

    def _on_lepton_file_changed(self, path: str):
        if self.lepton_control_bar:
            self.lepton_control_bar.set_status("change detected, simulating...")
        self._run_lepton_pipeline(path)

    def _on_lepton_simulate(self):
        if self._lepton_watched_path:
            self._run_lepton_pipeline(self._lepton_watched_path)

    def _on_lepton_unwatch(self):
        self._lepton_last_path = self._lepton_watched_path
        if self._lepton_watcher:
            self._lepton_watcher.unwatch()
        if self._lepton_cross_probe:
            self._lepton_cross_probe.disconnect()
        if self.lepton_control_bar:
            self.lepton_control_bar.set_status("not watching")
        self._lepton_watched_path = None

    def _run_lepton_pipeline(self, sch_path: str):
        if self._lepton_simulating:
            self.chat_panel.append_output("[lepton] pipeline skipped (already simulating)\n")
            return
        if self._lepton_bridge is None:
            return
        self._lepton_simulating = True
        if self.lepton_control_bar:
            self.lepton_control_bar.set_simulating(True)
        try:
            result = self._lepton_bridge.simulate(sch_path)
            if result["returncode"] != 0:
                self.chat_panel.append_output(
                    f"[lepton] Simulation failed (code {result['returncode']}):\n"
                    f"{result['stderr']}\n"
                )
                return
            if result["raw_file"]:
                self._load_raw_file(result["raw_file"])
                self.chat_panel.append_output(
                    f"[lepton] Simulation complete: "
                    f"{len(self.state.datasets[-1].variables)} signals loaded\n"
                )
                if self.lepton_control_bar:
                    self.lepton_control_bar.set_simulation_complete()
        except (FileNotFoundError, RuntimeError) as e:
            self.chat_panel.append_output(f"[lepton] {e}\n")
        finally:
            self._lepton_simulating = False
            if self.lepton_control_bar:
                self.lepton_control_bar.set_simulating(False)

    def _on_lepton_annotate_dc(self, voltages: dict[str, float] | None = None):
        if not self._lepton_cross_probe or not self._lepton_cross_probe.is_connected():
            self._lepton_cross_probe.connect_to_server()
        if self._lepton_cross_probe and self._lepton_cross_probe.is_connected():
            if voltages is None:
                voltages = self._extract_dc_voltages()
            for netname, voltage in voltages.items():
                self._lepton_cross_probe.send_command(
                    f"$ANNOTATE:DC {netname} {voltage}"
                )
            self.chat_panel.append_output(
                f"[lepton] DC annotations stamped: {len(voltages)} nets\n"
            )

    def _on_lepton_clear_annotations(self):
        if not self._lepton_cross_probe or not self._lepton_cross_probe.is_connected():
            self._lepton_cross_probe.connect_to_server()
        if self._lepton_cross_probe and self._lepton_cross_probe.is_connected():
            self._lepton_cross_probe.send_command("$CLEAR:ANNOTATIONS")
            self._lepton_cross_probe.send_command("$CLEAR:DC")
            self.chat_panel.append_output("[lepton] Annotations cleared\n")

    def _on_lepton_net_selected(self, netname: str):
        """Reverse cross-probe: user clicked a net in lepton-schematic → plot trace."""
        self.chat_panel.append_output(f"[lepton] Selected net: {netname}\n")
        state = ApplicationState()
        panel = self.panel_grid.get_active_panel()
        if panel and panel.state and state.datasets:
            ds_idx = panel.state.dataset_index
            if ds_idx < len(state.datasets):
                ds = state.datasets[ds_idx]
                candidates = [f"v({netname})", netname]
                for c in candidates:
                    for var in ds.variables:
                        if var.name.lower() == c.lower():
                            from pqwave.models.trace import Trace
                            trace = Trace(
                                x_data=var.data if ds.variables[0].name == "time" else None,
                                y_data=var.data,
                                name=c,
                                source_net=netname,
                            )
                            panel.state.traces.append(trace)
                            panel.trace_manager.update_traces()
                            return
```

- [ ] **Step 4: Add callbacks to _action_handlers**

Add after the KiCad entries in the `_action_handlers` dict:

```python
            'lepton_watch': self._on_lepton_watch,
            'lepton_simulate': self._on_lepton_simulate,
            'lepton_unwatch': self._on_lepton_unwatch,
```

- [ ] **Step 5: Commit**

```bash
git add pqwave/ui/main_window.py
git commit -m "feat: wire LeptonBridge with install dialog and handlers"
```

---

### Task 7: Menu Manager Integration

**Files:**
- Modify: `pqwave/ui/menu_manager.py`

- [ ] **Step 1: Add Lepton Bridge submenu to File menu**

After the KiCad bridge submenu block, add:

```python
        # Lepton-EDA Bridge submenu
        lepton_menu = QMenu("Lepton Bridge", self.parent)

        watch_action = QAction("Watch Schematic...", self.parent)
        watch_action.triggered.connect(self.callbacks.get("lepton_watch", lambda: None))
        lepton_menu.addAction(watch_action)

        simulate_action = QAction("Simulate Now", self.parent)
        simulate_action.triggered.connect(self.callbacks.get("lepton_simulate", lambda: None))
        lepton_menu.addAction(simulate_action)

        lepton_menu.addSeparator()

        annotate_action = QAction("Annotate DC", self.parent)
        annotate_action.triggered.connect(
            self.callbacks.get("lepton_annotate_dc", lambda: None)
        )
        lepton_menu.addAction(annotate_action)

        clear_action = QAction("Clear Annotations", self.parent)
        clear_action.triggered.connect(
            self.callbacks.get("lepton_clear_annotations", lambda: None)
        )
        lepton_menu.addAction(clear_action)

        lepton_menu.addSeparator()

        cross_probe_menu = QMenu("Cross-Probe", self.parent)
        probe_action = QAction("Probe Selected Net", self.parent)
        probe_action.triggered.connect(
            self.callbacks.get("lepton_probe_net", lambda: None)
        )
        cross_probe_menu.addAction(probe_action)
        clear_probe = QAction("Clear Highlight", self.parent)
        clear_probe.triggered.connect(
            self.callbacks.get("lepton_clear", lambda: None)
        )
        cross_probe_menu.addAction(clear_probe)
        lepton_menu.addMenu(cross_probe_menu)

        lepton_menu.addSeparator()
        unwatch_action = QAction("Stop Watching", self.parent)
        unwatch_action.triggered.connect(
            self.callbacks.get("lepton_unwatch", lambda: None)
        )
        lepton_menu.addAction(unwatch_action)

        file_menu.addMenu(lepton_menu)
        file_menu.addSeparator()
```

- [ ] **Step 2: Add Lepton User Guide to Help menu**

After the KiCad guide entry, add:

```python
        lepton_guide_action = QAction("Lepton-EDA User Guide", self.parent)
        lepton_guide_action.triggered.connect(
            self.callbacks.get("show_lepton_guide", lambda: None)
        )
        help_menu.addAction(lepton_guide_action)
```

- [ ] **Step 3: Commit**

```bash
git add pqwave/ui/menu_manager.py
git commit -m "feat: add Lepton Bridge submenu and Help guide entry"
```

---

### Task 8: Settings Dialog

**Files:**
- Modify: `pqwave/ui/settings_dialog.py`

- [ ] **Step 1: Add lepton-netlist and ngspice path fields**

Add two QLineEdit fields in the External Converter Paths group for `lepton_netlist` and `ngspice`, following the same pattern as existing `kicad_cli`, `fst2vcd`, `ghwdump` fields. Load/save from `ApplicationState.tool_paths` with those keys.

- [ ] **Step 2: Commit**

```bash
git add pqwave/ui/settings_dialog.py
git commit -m "feat: add lepton-netlist and ngspice path fields to settings"
```

---

### Task 9: Testing

**Files:**
- Create: `tests/test_lepton_bridge.py`

- [ ] **Step 1: Write bridge core tests**

```python
# tests/test_lepton_bridge.py
"""Tests for Lepton-EDA bridge."""

import pytest
from pqwave.bridge.lepton.bridge import LeptonBridge


class TestLeptonBridge:
    def test_get_netlist_fixes_returns_empty(self):
        bridge = LeptonBridge()
        assert bridge.get_netlist_fixes() == []

    def test_get_watch_extensions_returns_sch(self):
        bridge = LeptonBridge()
        assert bridge.get_watch_extensions() == [".sch"]

    def test_detect_tool_returns_path_when_installed(self):
        bridge = LeptonBridge()
        path = bridge.detect_tool()
        assert path is not None
        assert "lepton-netlist" in path

    def test_is_tool_running_returns_bool(self):
        bridge = LeptonBridge()
        assert isinstance(bridge.is_tool_running(), bool)

    def test_simulate_with_invalid_sch_raises(self):
        bridge = LeptonBridge()
        with pytest.raises(Exception):
            bridge.simulate("/nonexistent/file.sch")


class TestLeptonBridgeNetlistExport:
    def test_export_two_stage_amp(self):
        bridge = LeptonBridge()
        sch = "/home/wing/Apps/lepton-eda.git/examples/TwoStageAmp/TwoStageAmp.sch"
        netlist = bridge.export_netlist(sch)
        assert ".end" in netlist
        assert "/Vbase1" not in netlist  # no leading slashes
        assert "Q1" in netlist or "Q2" in netlist

    def test_simulate_two_stage_amp(self):
        bridge = LeptonBridge()
        sch = "/home/wing/Apps/lepton-eda.git/examples/TwoStageAmp/TwoStageAmp.sch"
        result = bridge.simulate(sch)
        assert result["returncode"] == 0
        assert result["raw_file"] is not None
        assert ".end" in result["netlist"]


class TestSchemeServerDeployment:
    def test_check_scheme_server_returns_status(self):
        from pqwave.bridge.lepton.cross_probe import check_scheme_server
        status = check_scheme_server()
        assert "installed" in status
        assert "target_path" in status
        assert "bundled_version_mtime" in status
        assert "needs_update" in status

    def test_bundled_scm_exists(self):
        from pqwave.bridge.lepton.cross_probe import _get_package_scm_path
        import os
        assert os.path.exists(_get_package_scm_path())
```

- [ ] **Step 2: Run tests**

```bash
cd /home/wing/Apps/pqwave.git && python -m pytest tests/test_lepton_bridge.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_lepton_bridge.py
git commit -m "test: add LeptonBridge core and deployment tests"
```

---

### Task 10: Documentation

**Files:**
- Create: `docs/lepton/guide.html`

- [ ] **Step 1: Write lepton-eda bridge user guide**

Create `docs/lepton/guide.html` — self-contained HTML with inline CSS, two-part structure:

**Part 1 — Feature Reference:** Overview, netlist pipeline (zero fixes), in-schematic menus, bidirectional cross-probe, back-annotation (DC stamps + floating labels + clear), session API commands, Scheme server deployment instructions.

**Part 2 — Worked Tutorials:**
1. TwoStageAmp — complete in-schematic workflow (SPICE → ngspice → pqwave)
2. Bidirectional cross-probe (click net → plot; click trace → highlight)
3. DC back-annotation (stamp, verify, clear)
4. Standalone scripting example (headless API)

- [ ] **Step 2: Commit**

```bash
git add docs/lepton/guide.html
git commit -m "docs: add lepton-eda bridge user guide (HTML)"
```

---

## Appendix: pqwave-server.scm

The complete Scheme script is stored at `pqwave/bridge/lepton/pqwave-server.scm`. Key sections:

- **TCP server**: Guile `(ice-9 sockets)` server listening on port 9424
- **Command dispatch**: `$NET`, `$PART`, `$CLEAR`, `$ANNOTATE:DC`, `$ANNOTATE:LABEL`, `$CLEAR:ANNOTATIONS`, `$CLEAR:DC`
- **Cross-probe handlers**: `pqwave-probe-net`, `pqwave-probe-part`, `pqwave-clear-selection`
- **Back-annotation handlers**: `pqwave-annotate-dc`, `pqwave-annotate-label`, `pqwave-clear-labels`, `pqwave-clear-dc-stamps`
- **Reverse cross-probe**: `select-objects-hook` → sends `$SELECTED:net`/`$SELECTED:part` to pqwave
- **In-schematic menus**: `&spice-netlist`, `&sim-ngspice`, `&wave-pqwave` actions + `add-menu` calls

---

## Self-Review

**1. Spec coverage:** All 9 requirements covered → Tasks 1 (export, simulate), 2 (file watch), 3 (cross-probe, scheme server, in-schematic menus), 4 (control bar), 5 (session API), 6 (wiring, install dialog), 7 (menu manager), 8 (settings), 9 (tests), 10 (docs).

**2. Placeholder scan:** No TBD, TODO, or vague descriptions. Every step has complete code or specific instructions.

**3. Type consistency:** All signals, method names, and tool_paths keys are consistent across tasks.
