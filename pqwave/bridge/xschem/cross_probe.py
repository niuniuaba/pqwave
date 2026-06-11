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

Back-annotation stamps trace values onto lab_generic.sym ``value``
attributes via xschem setprop — no C patch needed.
"""

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
        self._lab_position_cache: dict[str, tuple[float, float]] | None = None
        self._cursor_text_cache: dict[str, int] | None = None
        self._dc_text_cache: dict[str, int] | None = None

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
        then uppercase (SPICE convention).

        Note: highlighted nets cannot be re-sent via Alt+G (xschem
        skips already-highlighted nodes).  Use Clear Highlight first.
        """
        for attempt in (name, name.upper()):
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
        """Stamp trace values as floating text near lab symbols.

        Finds ANY instance with a ``lab`` attribute (lab_pin, lab_wire,
        lab_generic, etc.) whose value matches a net name, then creates
        or updates a free-floating ``xschem text`` object at that position.

        Text objects are tagged with ``pqwave_net=<name>`` in their props
        so they can be found and updated in-place on cursor move.  No
        special symbol type is required — the user can use any lab.

        Args:
            net_values: dict mapping net name → display value,
                        e.g. ``{"r1": "96.0117", "r2": "48.3"}``.
        """
        lab_positions = self._build_lab_position_map()
        pqwave_texts = self._get_pqwave_texts_tag("pqwave_net", "cursor")

        tcl_lines: list[str] = []
        stamp_count = 0
        for net_name, value in net_values.items():
            net_lower = net_name.lower()
            text_idx = pqwave_texts.get(net_lower)
            if text_idx is not None:
                # Update existing floating text in-place.
                tcl_lines.append(
                    f"xschem setprop text {text_idx} txt_ptr {{{value}V}}"
                )
                stamp_count += 1
            elif net_lower in lab_positions:
                x, y = lab_positions[net_lower]
                tcl_lines.append(
                    f"xschem text {x:.0f} {y:.0f} 0 0 {{{value}V}} "
                    f"{{pqwave_net={net_lower}}} 0.3 1"
                )
                stamp_count += 1

        if stamp_count:
            tcl_lines.append("xschem redraw")
            self.send_command("; ".join(tcl_lines))
            self._invalidate_all_text_caches()
        return stamp_count > 0

    def stamp_dc_values(self, net_values: dict[str, str]) -> bool:
        """Stamp DC operating-point voltages as floating text near lab symbols.

        Same as ``stamp_values()`` but tags text with ``pqwave_dc=<name>``
        so DC annotations are independent from cursor back-annotation texts.
        """
        lab_positions = self._build_lab_position_map()
        pqwave_texts = self._get_pqwave_texts_tag("pqwave_dc", "dc")

        tcl_lines: list[str] = []
        stamp_count = 0
        for net_name, value in net_values.items():
            net_lower = net_name.lower()
            text_idx = pqwave_texts.get(net_lower)
            if text_idx is not None:
                tcl_lines.append(
                    f"xschem setprop text {text_idx} txt_ptr {{{value}V}}"
                )
                stamp_count += 1
            elif net_lower in lab_positions:
                x, y = lab_positions[net_lower]
                tcl_lines.append(
                    f"xschem text {x:.0f} {y:.0f} 0 0 {{{value}V}} "
                    f"{{pqwave_dc={net_lower}}} 0.3 1"
                )
                stamp_count += 1

        if stamp_count:
            tcl_lines.append("xschem redraw")
            self.send_command("; ".join(tcl_lines))
            self._invalidate_all_text_caches()
        return stamp_count > 0

    def clear_stamps(self) -> bool:
        """Delete cursor back-annotation texts tagged with ``pqwave_net=``."""
        return self._delete_tagged_texts("pqwave_net", "cursor")

    def clear_dc_stamps(self) -> bool:
        """Delete DC annotation texts tagged with ``pqwave_dc=``."""
        return self._delete_tagged_texts("pqwave_dc", "dc")

    def clear_all_stamps(self) -> bool:
        """Delete ALL pqwave floating texts (cursor + DC)."""
        a = self.clear_stamps()
        b = self.clear_dc_stamps()
        return a or b

    def remove_stamp(self, net_name: str) -> bool:
        """Delete a single cursor back-annotation text for *net_name*."""
        pqwave_texts = self._get_pqwave_texts_tag("pqwave_net", "cursor")
        return self._delete_one_text(pqwave_texts, net_name)

    def _delete_tagged_texts(self, tag: str, cache_key: str) -> bool:
        """Delete all text objects whose props contain ``<tag>=<name>``."""
        pqwave_texts = self._get_pqwave_texts_tag(tag, cache_key)
        if not pqwave_texts:
            return False

        tcl_lines: list[str] = []
        for idx in pqwave_texts.values():
            tcl_lines.append(f"xschem select text {idx}")
        tcl_lines.append("xschem delete")
        tcl_lines.append("xschem redraw")
        self.send_command("; ".join(tcl_lines))
        self._invalidate_all_text_caches()
        return True

    def _delete_one_text(self, pqwave_texts: dict[str, int],
                         net_name: str) -> bool:
        """Delete a single text object by net name."""
        net_lower = net_name.lower()
        idx = pqwave_texts.get(net_lower)
        if idx is None:
            return False

        self.send_command(
            f"xschem select text {idx}; xschem delete; xschem redraw"
        )
        self._invalidate_all_text_caches()
        return True

    # ---- Lab / text helpers ----

    def _build_lab_position_map(self) -> dict[str, tuple[float, float]]:
        """Build ``{lab_value_lower: (x, y)}`` for all instances that have
        a ``lab`` attribute — any symbol type (lab_pin, lab_wire,
        lab_generic, etc.).  Result is cached until ``invalidate_label_map()``.
        """
        if self._lab_position_cache is not None:
            return self._lab_position_cache

        ok, result = self.send_command("xschem instance_list")
        if not ok:
            return {}

        # Output: {p2} {lab_pin.sym} {label} {p3} {lab_pin.sym} {label} ...
        tokens = result.replace("{", "").replace("}", "").split()
        all_insts: list[str] = []
        for i in range(0, len(tokens) - 2, 3):
            all_insts.append(tokens[i])

        if not all_insts:
            self._lab_position_cache = {}
            return {}

        # Round 1: get lab attribute for every instance.
        lab_cmd = (
            "set _res {}; "
            + "; ".join(
                f"lappend _res [xschem getprop instance {n} lab]"
                for n in all_insts
            )
            + "; set _res"
        )
        ok_lab, lab_result = self.send_command(lab_cmd)
        if not ok_lab:
            self._lab_position_cache = {}
            return {}

        lab_values = lab_result.split()
        # Filter to instances with a non-empty lab attribute.
        lab_insts: list[tuple[str, str]] = []  # [(inst_name, lab_value), ...]
        for inst_name, lab_val in zip(all_insts, lab_values):
            lab_val = lab_val.strip()
            if lab_val and lab_val != "{}":
                lab_insts.append((inst_name, lab_val))

        if not lab_insts:
            self._lab_position_cache = {}
            return {}

        # Round 2: get coordinates for lab instances.
        # xschem instance_coord <name> returns: {name} {sym} x0 y0 rot flip
        coord_cmd = (
            "set _res {}; "
            + "; ".join(
                f"lappend _res [xschem instance_coord {name}]"
                for name, _ in lab_insts
            )
            + "; set _res"
        )
        ok_coord, coord_result = self.send_command(coord_cmd)
        if not ok_coord:
            self._lab_position_cache = {}
            return {}

        # Parse: each instance_coord contributes 6 tokens.
        # xschem returns newlines in the output — strip braces and split on
        # whitespace (newlines included).
        coord_tokens = (
            coord_result.replace("{", "").replace("}", "").split()
        )
        lab_positions: dict[str, tuple[float, float]] = {}
        for i, (_, lab_val) in enumerate(lab_insts):
            base = i * 6
            if base + 3 >= len(coord_tokens):
                break
            try:
                # Tokens: name, sym, x0, y0, rot, flip
                x = float(coord_tokens[base + 2])
                y = float(coord_tokens[base + 3])
                lab_positions[lab_val.lower()] = (x, y)
            except (ValueError, IndexError):
                continue

        self._lab_position_cache = lab_positions
        return lab_positions

    def _get_pqwave_texts_tag(self, tag: str, cache_key: str) -> dict[str, int]:
        """Find text objects tagged with ``<tag>=<name>`` in props.
        Returns ``{net_name: text_index}``.  Result is cached per *cache_key*.
        """
        cache = getattr(self, f"_{cache_key}_text_cache", None)
        if cache is not None:
            return cache

        # Get total text count.
        ok, result = self.send_command("xschem globals")
        if not ok:
            return {}

        texts_n = 0
        for line in result.splitlines():
            if line.startswith("texts="):
                texts_n = int(line.split("=")[1])
                break

        if texts_n == 0:
            setattr(self, f"_{cache_key}_text_cache", {})
            return {}

        # Batch: get <tag> prop for every text object.
        getprop_cmd = (
            "set _res {}; "
            + "; ".join(
                f"lappend _res [xschem getprop text {i} {tag}]"
                for i in range(texts_n)
            )
            + "; set _res"
        )
        ok_get, getprop_result = self.send_command(getprop_cmd)
        if not ok_get:
            setattr(self, f"_{cache_key}_text_cache", {})
            return {}

        pqwave_texts: dict[str, int] = {}
        values = getprop_result.split()
        for i in range(min(texts_n, len(values))):
            net_name = values[i].strip()
            # Tcl represents empty list elements as "{}" — skip them.
            if net_name and net_name != "{}":
                pqwave_texts[net_name] = i

        setattr(self, f"_{cache_key}_text_cache", pqwave_texts)
        return pqwave_texts

    def _invalidate_all_text_caches(self) -> None:
        """Clear all text caches — needed after any deletion since indices
        shift and invalidate cached positions for OTHER tag types."""
        self._cursor_text_cache = None
        self._dc_text_cache = None

    def invalidate_label_map(self) -> None:
        """Clear all cached maps (call after schematic changes)."""
        self._lab_position_cache = None
        self._invalidate_all_text_caches()
