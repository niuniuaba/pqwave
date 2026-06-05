"""TCP client for xschem's setup_tcp_xschem Tcl eval server.

Sends raw Tcl commands to xschem's built-in TCP Tcl server on the port
configured via ``xschem_listen_port`` (default 2021).  xschem evaluates
each command, sends back the result, and closes the connection — every
command opens a fresh TCP connection.

The old pqwave-server.tcl custom protocol ($NET:, $PART:, $CLEAR) is
replaced by direct Tcl commands that call xschem's built-in procs:

  $NET: "VOUT"     -->  probe_net VOUT 1     (Tcl proc in xschem.tcl)
  $PART: "R1"      -->  select_inst R1 1      (Tcl proc in xschem.tcl)
  $CLEAR           -->  xschem unhilight_all; xschem redraw

Back-annotation sets values directly in the ::ngspice::ngspice_data Tcl
array, then triggers xschem to redraw — no C patch needed.
"""

import re
import socket
from PyQt6.QtCore import QObject, pyqtSignal


class XschemCrossProbeClient(QObject):
    """Stateless TCP client for xschem's setup_tcp_xschem Tcl eval server.

    Each command opens a new TCP connection, sends raw Tcl, reads the
    response, and closes the socket — xschem closes the connection after
    each evaluation.

    Signals (kept for backward compatibility):
        connected():          emitted on connect_to_server() (no-op, always)
        disconnected():       emitted on disconnect() (no-op, never)
        error_occurred(str):  TCP connection or send error
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, port: int = 2021, timeout: float = 2.0):
        super().__init__()
        self._port = port
        self._timeout = timeout

    # ---- Stateless connection lifecycle ----

    def is_connected(self) -> bool:
        """Always True — client is stateless (connects per command)."""
        return True

    def connect_to_server(self) -> bool:
        """No-op in stateless mode.  Returns True."""
        self.connected.emit()
        return True

    def disconnect(self) -> None:
        """No-op in stateless mode."""
        pass

    # ---- Command send ----

    def send_command(self, text: str) -> tuple[bool, str]:
        """Send a Tcl command to xschem's setup_tcp_xschem server.

        Opens a new TCP connection, sends *text*, reads the response
        (until EOF — xschem closes after eval), then closes.

        Args:
            text: Raw Tcl command string (semicolons for multiple commands).

        Returns:
            (True, response_text) on success,
            (False, error_message) on failure.
        """
        try:
            sock = socket.create_connection(
                ("127.0.0.1", self._port), timeout=self._timeout
            )
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            msg = (
                f"xschem not running or not listening "
                f"on localhost:{self._port}: {exc}"
            )
            self.error_occurred.emit(msg)
            return False, msg

        try:
            payload = text.rstrip("\n") + "\n"
            sock.sendall(payload.encode("utf-8"))

            # Read response until EOF (xschem closes the connection).
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

            return True, response.decode("utf-8").strip()
        except OSError as exc:
            msg = f"xschem send/recv failed: {exc}"
            self.error_occurred.emit(msg)
            return False, msg
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # ---- Cross-probe commands ----

    def probe_net(self, name: str) -> bool:
        """Highlight *name* net in xschem.

        xschem net names are case-sensitive.  Tries verbatim first,
        then uppercase (SPICE convention).  Sends: probe_net <name> 1
        """
        for attempt in (name, name.upper()):
            if attempt != name:
                pass  # fallback
            ok, result = self.send_command(f"probe_net {attempt} 1")
            if ok and result.strip():
                return True
        return False

    def probe_part(self, ref: str, pin: str | None = None) -> bool:
        """Select/highlight component *ref* in xschem.

        With *pin*:  select_inst <ref> <pin>
        Without:     select_inst <ref> 1
        """
        if pin:
            success, _ = self.send_command(f"select_inst {ref} {pin}")
        else:
            success, _ = self.send_command(f"select_inst {ref} 1")
        return success

    def clear(self) -> bool:
        """Clear all highlights in xschem.

        Sends:  xschem unhilight_all; xschem redraw
        """
        success, _ = self.send_command(
            "xschem unhilight_all; xschem redraw"
        )
        return success

    # ---- Back-annotation (label stamping) ----

    def stamp_values(self, net_values: dict[str, str]) -> bool:
        """Stamp trace values onto lab_pin label attributes.

        Finds lab_pin instances whose ``lab`` attribute matches a net
        name in *net_values* (case-insensitive) and appends the value
        to the label text, e.g. ``R1`` → ``R1 = 1.234V``.

        All Tcl commands are batched into a single TCP round-trip to
        avoid the ``redef_puts`` rename collision in ``xschem_getdata``
        when multiple connections arrive in rapid succession.

        Original lab values are tracked so ``clear_stamps()`` can
        restore them.  Much simpler than the ``tcleval`` / ``@spice``
        approach — pure Tcl attribute modification with no C-level
        dependencies.

        Args:
            net_values: dict mapping net name → display value,
                        e.g. ``{"r1": "1.234", "r2": "5.678"}``.
        """
        label_map = self._build_label_map()
        if not label_map:
            return False

        # Build a single batched Tcl script for all setprop calls.
        tcl_lines: list[str] = []
        stamp_count = 0
        for net_name, value in net_values.items():
            inst_name = self._find_label_instance(label_map, net_name)
            if inst_name is None:
                continue

            # Save original lab value once (read from cached map).
            if inst_name not in self._original_labs:
                orig_lab = net_name.upper()
                # Try to read the real original from the label map keys
                for lab_key, mapped_inst in label_map.items():
                    if mapped_inst == inst_name and lab_key != net_name.lower():
                        orig_lab = lab_key.upper()
                        break
                self._original_labs[inst_name] = orig_lab

            label = f"{net_name.upper()} = {value}V"
            tcl_lines.append(
                f"xschem setprop instance {inst_name} lab {{{label}}}"
            )
            stamp_count += 1

        if stamp_count:
            tcl_lines.append("xschem redraw")
            self.send_command("; ".join(tcl_lines))
        return stamp_count > 0

    def clear_stamps(self) -> bool:
        """Restore original lab_pin label values cleared by ``stamp_values()``."""
        if not self._original_labs:
            return False

        tcl_lines = [
            f"xschem setprop instance {n} lab {{{lab}}}"
            for n, lab in self._original_labs.items()
        ]
        tcl_lines.append("xschem redraw")
        self._original_labs.clear()
        self.send_command("; ".join(tcl_lines))
        return True

    # ---- Label map helpers ----

    _label_map_cache: dict[str, str] | None = None
    _original_labs: dict[str, str] = {}

    def _build_label_map(self) -> dict[str, str]:
        """Build ``{lab_value_lower: instance_name}`` from xschem's
        instance list.  Result is cached until ``invalidate_label_map()``
        is called.

        Batches all getprop calls into a single TCP round-trip.
        """
        if self._label_map_cache is not None:
            return self._label_map_cache

        ok, result = self.send_command("xschem instance_list")
        if not ok:
            return {}

        # Output: {p2} {lab_pin.sym} {label} {p3} {lab_pin.sym} {label} ...
        tokens = result.replace("{", "").replace("}", "").split()
        label_insts: list[str] = []
        for i in range(0, len(tokens) - 2, 3):
            inst_name, sym_name = tokens[i], tokens[i + 1]
            if sym_name in ("lab_pin.sym", "pqwave_lab_pin.sym"):
                label_insts.append(inst_name)

        if not label_insts:
            self._label_map_cache = {}
            return {}

        # Batch getprop into one TCP round-trip.  Use lappend + set
        # (not puts) because xschem_getdata's redef_puts can only
        # capture a single value — multiple puts overwrite each other.
        getprop_cmd = (
            "set _res {}; "
            + "; ".join(
                f"lappend _res [xschem getprop instance {n} lab]"
                for n in label_insts
            )
            + "; set _res"
        )
        ok_get, getprop_result = self.send_command(getprop_cmd)
        if not ok_get:
            self._label_map_cache = {}
            return {}

        label_map: dict[str, str] = {}
        # Parse Tcl list: {R2} {AC_p} {AC_n} — only values.
        lab_values = re.findall(r"\{([^}]*)\}", getprop_result)
        for inst_name, lab_val in zip(label_insts, lab_values):
            lab_val = lab_val.strip()
            if lab_val:
                label_map[lab_val.lower()] = inst_name

        self._label_map_cache = label_map
        return label_map

    @staticmethod
    def _find_label_instance(label_map: dict[str, str],
                             net_name: str) -> str | None:
        """Find a lab_pin instance by case-insensitive net name match."""
        net_lower = net_name.lower()
        if net_lower in label_map:
            return label_map[net_lower]
        # Try removing v() / i() prefix.
        if net_lower.startswith("v(") and net_lower.endswith(")"):
            bare = net_lower[2:-1]
            if bare in label_map:
                return label_map[bare]
        return None

    def invalidate_label_map(self) -> None:
        """Clear the cached label map (call after schematic changes)."""
        self._label_map_cache = None
        self._original_labs.clear()
