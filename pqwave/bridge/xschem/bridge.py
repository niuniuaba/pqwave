"""Xschem-specific SchematicBridge implementation."""

import os
import re
import shlex
import shutil
import subprocess
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix, resolve_ngspice
from pqwave.bridge.netlist_postprocessor import NetlistPostProcessor
from pqwave.models.state import ApplicationState


class XschemBridge(SchematicBridge):
    """SchematicBridge for xschem.

    Uses xschem -n -s -x -q for netlist export.  Simulation follows the
    user's ~/.xschem/simrc configuration (sim(spice,default)).
    Cross-probe is handled by XschemCrossProbeClient communicating
    with pqwave-server.tcl running inside xschem.
    Wave push (Alt+G) is handled by WaveReceiver on port 2026.
    """

    def __init__(self, xschem_path: str = "", ngspice_path: str = ""):
        super().__init__()
        self._xschem = xschem_path
        self._ngspice = ngspice_path
        self._cross_probe = None  # lazily instantiated in _ensure_cross_probe()

    # ---- SchematicBridge implementation ----

    def export_netlist(self, sch_path: str) -> str:
        """Export SPICE netlist from a .sch file via xschem CLI.

        Respects xschem's configured netlist_dir — does NOT override it.
        Flags: -n (netlist), -s (spice type), -x (no X/GUI), -q (quit after).
        """
        xschem_bin = self._resolve_xschem()
        sch_dir = os.path.dirname(os.path.abspath(sch_path))
        sch_basename = os.path.splitext(os.path.basename(sch_path))[0]

        netlist_dir = self._resolve_netlist_dir(sch_dir)
        os.makedirs(netlist_dir, exist_ok=True)

        result = subprocess.run(
            [xschem_bin, "-n", "-s", "-x", "-q", sch_path],
            capture_output=True, text=True, timeout=30,
            cwd=sch_dir,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"xschem failed with code {result.returncode}: {result.stderr}"
            )

        spice_path = os.path.join(netlist_dir, f"{sch_basename}.spice")
        if os.path.exists(spice_path):
            with open(spice_path, "r") as f:
                return f.read()
        raise RuntimeError(
            f"xschem ran but no .spice file found at {spice_path}. "
            f"stderr: {result.stderr}"
        )

    def get_netlist_fixes(self) -> list[NetlistFix]:
        """Xschem SPICE output is clean — no fixes needed."""
        return []

    def probe_net(self, net_name: str) -> None:
        self._ensure_cross_probe().probe_net(net_name)

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        cp = self._ensure_cross_probe()
        cp.probe_part(ref, pin)

    def clear_probe(self) -> None:
        self._ensure_cross_probe().clear()

    def detect_tool(self) -> Optional[str]:
        try:
            return self._resolve_xschem()
        except FileNotFoundError:
            return None

    def is_tool_running(self) -> bool:
        # Try process-based detection first (pgrep / pidof).
        for cmd in (["pgrep", "-x", "xschem"], ["pidof", "xschem"]):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        # Fallback: check if the cross-probe TCP port is accepting connections.
        # This also works in containers / restricted shells where pgrep/pidof
        # are unavailable.
        import socket as _socket
        state = ApplicationState()
        cp_config = getattr(state, "_xschem_config", {})
        port = cp_config.get("cross_probe_port", 2021)
        try:
            sock = _socket.create_connection(
                ("localhost", port), timeout=0.5
            )
            sock.close()
            return True
        except (OSError, _socket.timeout):
            return False

    def get_watch_extensions(self) -> list[str]:
        return [".sch"]

    # ---- Simulation pipeline ----

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        """Export netlist and run the user's configured simulator from simrc.

        Terminal-based simulators (template contains $terminal) are
        launched non-blocking — pqwave does not wait for the user to
        close the terminal window.  Batch simulators run synchronously.

        Returns whatever .raw file is found after the simulator runs
        (or None if the simulator doesn't produce one).
        """
        netlist = self.export_netlist(sch_path)
        processor = NetlistPostProcessor(self.get_netlist_fixes())
        fixed = processor.process(netlist)

        sch_dir = os.path.dirname(os.path.abspath(sch_path))
        netlist_dir = self._resolve_netlist_dir(sch_dir)
        sch_basename = os.path.splitext(os.path.basename(sch_path))[0]
        spice_path = os.path.join(netlist_dir, f"{sch_basename}.spice")

        # Write the (possibly post-processed) netlist to disk so the
        # simulator reads the fixed content, not the raw xschem output.
        with open(spice_path, "w") as f:
            f.write(fixed)

        cmd, uses_terminal = self._resolve_sim_cmd(
            netlist_path=spice_path, netlist_basename=sch_basename,
        )

        # The simrc template is user-owned config — shell=True is
        # acceptable here (xschem itself shells out the same templates).
        # Substituted values are shlex.quote()'d; the template body is
        # trusted (if the user's simrc is compromised, they have bigger
        # problems than pqwave shell injection).

        # Record mtime of any existing .raw before launch so we don't
        # mistake a stale file from a prior run for current output.
        _raw_before = os.path.join(netlist_dir, f"{sch_basename}.raw")
        _raw_mtime_before = os.path.getmtime(_raw_before) if os.path.exists(_raw_before) else 0.0

        # Terminal-based simulators (template contains $terminal, e.g.
        # "ptyxis -e ngspice -i ...") would block forever.  Launch
        # detached instead.  returncode is None to signal "not yet known".
        if uses_terminal:
            # Log stderr to a known temp file for diagnostics.  Reuses
            # the same path across runs — each invocation overwrites.
            import tempfile as _tempfile
            _err_path = os.path.join(
                _tempfile.gettempdir(), "pqwave_xschem_sim.log"
            )
            _err_file = open(_err_path, "w")
            try:
                subprocess.Popen(
                    cmd, shell=True, cwd=netlist_dir,
                    stdout=subprocess.DEVNULL, stderr=_err_file,
                )
            finally:
                _err_file.close()  # Popen dup'd the fd; close parent's handle
            returncode = None
            stdout = ""
            stderr = f"detached terminal simulator; stderr in {_err_path}"
        else:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                cwd=netlist_dir, shell=True,
            )
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr

        # Look for .raw — respect raw_output if provided, otherwise
        # check the user's netlist_dir and sch_dir as fallbacks.
        # For terminal-based sims, reject files unchanged since launch.
        found_raw = None
        candidates = (
            [raw_output] if raw_output else []
        ) + [
            os.path.join(netlist_dir, f"{sch_basename}.raw"),
            os.path.join(sch_dir, f"{sch_basename}.raw"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                if uses_terminal and os.path.getmtime(candidate) <= _raw_mtime_before:
                    continue  # stale file from prior run
                found_raw = candidate
                break

        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "raw_file": found_raw,
            "netlist": fixed,
            "fix_info": [],
        }

    # ---- Tool resolution ----

    def _resolve_xschem(self) -> str:
        if self._xschem and os.path.isfile(self._xschem):
            return self._xschem
        state = ApplicationState()
        custom = state.tool_paths.get("xschem", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("xschem")
        if found:
            return found
        raise FileNotFoundError(
            "xschem not found. Install xschem or set the path in "
            "Settings > External Converter Paths."
        )

    def _resolve_ngspice(self) -> str:
        return resolve_ngspice(self._ngspice)

    @staticmethod
    def _resolve_netlist_dir(sch_dir: str) -> str:
        """Determine xschem's effective netlist output directory.

        Follows xschem's precedence:
        1. If ``local_netlist_dir 1`` → ``<sch_dir>/simulation/``
        2. If ``netlist_dir`` is explicitly set → that path (with ~ expansion)
        3. Default → ``~/.xschem/simulations/``
        """
        xschemrc = os.path.join(os.path.expanduser("~"), ".xschem", "xschemrc")
        local_nl_dir = False
        explicit_nl_dir = ""

        try:
            with open(xschemrc, "r") as f:
                for line in f:
                    # Match: set local_netlist_dir 1
                    m = re.match(r"^\s*set\s+local_netlist_dir\s+(\d+)", line)
                    if m and m.group(1) == "1":
                        local_nl_dir = True
                    # Match: set netlist_dir /some/path
                    m = re.match(r'^\s*set\s+netlist_dir\s+"?([^"\n#]+)"?', line)
                    if m:
                        # Strip trailing whitespace and inline comments.
                        explicit_nl_dir = m.group(1).rsplit("#", 1)[0].strip()
        except OSError:
            pass

        if local_nl_dir:
            return os.path.join(sch_dir, "simulation")
        if explicit_nl_dir:
            return os.path.expanduser(explicit_nl_dir)
        return os.path.join(os.path.expanduser("~"), ".xschem", "simulations")

    @staticmethod
    def _resolve_sim_cmd(netlist_path: str, netlist_basename: str) -> tuple[str, bool]:
        """Build the simulation shell command from the user's simrc.

        Reads ``~/.xschem/simrc`` to find the active spice simulator
        (``sim(spice,default)``), extracts its command template, and
        substitutes ``$N`` (netlist path), ``$n`` (basename), and
        ``$terminal`` (from xschemrc).

        Returns ``(command, uses_terminal)``.  ``uses_terminal`` is True
        when the template references ``$terminal`` — the simulator opens
        a terminal window and pqwave should not block waiting for it.

        Falls back to ``ngspice -b`` if simrc is unreadable or the
        configured simulator index has no command entry.
        """
        simrc = os.path.join(os.path.expanduser("~"), ".xschem", "simrc")
        default_idx = 0
        cmds: dict[int, str] = {}

        try:
            with open(simrc, "r") as f:
                for line in f:
                    m = re.match(
                        r"^\s*set\s+sim\(spice,default\)\s+(\d+)", line
                    )
                    if m:
                        default_idx = int(m.group(1))
                    m = re.match(
                        r"^\s*set\s+sim\(spice,(\d+),cmd\)\s+\{(.+)\}", line
                    )
                    if m:
                        cmds[int(m.group(1))] = m.group(2)
        except OSError:
            pass

        template = cmds.get(default_idx)
        if not template:
            return (
                f"ngspice -b -r {shlex.quote(netlist_basename + '.raw')} "
                f"{shlex.quote(netlist_path)}",
                False,
            )

        uses_terminal = "$terminal" in template

        # Resolve $terminal from xschemrc
        terminal = XschemBridge._resolve_terminal()

        # Substitute Tcl variables with shell-safe values.
        # shlex.quote() prevents injection even if paths contain
        # metacharacters (spaces, ;, $(), etc.).
        cmd = template.replace("$N", shlex.quote(netlist_path))
        cmd = cmd.replace("$n", shlex.quote(netlist_basename))
        # $terminal comes from the user's own xschemrc — do NOT quote it.
        # Multi-word values like "xterm -e" need shell word-splitting.
        cmd = cmd.replace("$terminal", terminal)
        cmd = re.sub(r"\$env\(HOME\)",
                     lambda m: shlex.quote(os.path.expanduser("~")), cmd)

        return cmd, uses_terminal

    @staticmethod
    def _resolve_terminal() -> str:
        """Read the ``terminal`` setting from xschemrc.  Defaults to ``xterm``."""
        xschemrc = os.path.join(os.path.expanduser("~"), ".xschem", "xschemrc")
        try:
            with open(xschemrc, "r") as f:
                for line in f:
                    m = re.match(r'^\s*set\s+terminal\s+\{(.+)\}', line)
                    if m:
                        return m.group(1)
        except OSError:
            pass
        return "xterm"

    def _ensure_cross_probe(self):
        from pqwave.bridge.xschem.cross_probe import XschemCrossProbeClient
        if self._cross_probe is None:
            self._cross_probe = XschemCrossProbeClient()
        return self._cross_probe
