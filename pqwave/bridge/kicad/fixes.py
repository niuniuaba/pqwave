"""KiCad-specific netlist post-processing fixes.

Each fix inherits from :class:`pqwave.bridge.schem_bridge.NetlistFix` and
implements `apply()` (transform the netlist string) and `info()` (report what
would change without modifying).
"""

import logging
import re
from typing import Optional

_log = logging.getLogger(__name__)

from pqwave.bridge.schem_bridge import NetlistFix


class StripSlashes(NetlistFix):
    """Strip leading slashes from single-level net names.

    KiCad versions before 10.99.0 prepend '/' to root-level net names
    in exported SPICE netlists.  This fix strips those leading slashes
    from single-level names like /d1 → d1 while preserving multi-level
    hierarchical paths like /sheet1/net1.

    The fix is content-aware: if the netlist has no leading slashes
    at net positions, apply() is a no-op.
    """

    name = "Strip leading slashes from net names"

    _slash_re = re.compile(r"(?<![\w])/([A-Za-z_]\w*)(?![\/\w])")

    def _netlist_has_slashes(self, netlist: str) -> bool:
        """Check if the netlist contains leading slashes at net positions.

        Skips comment lines, .subckt, .param, and .func lines since
        slashes there are intentional.
        """
        for line in netlist.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("*"):
                continue
            if (stripped.startswith(".subckt") or stripped.startswith(".param")
                    or stripped.startswith(".func")):
                continue
            if self._slash_re.search(line):
                return True
        return False

    def apply(self, netlist: str, context: Optional[dict] = None) -> str:
        if not self._netlist_has_slashes(netlist):
            return netlist  # nothing to fix

        result_lines = []
        for line in netlist.split("\n"):
            stripped = line.strip()
            if (stripped.startswith("*") or stripped.startswith(".subckt")
                    or stripped.startswith(".param") or stripped.startswith(".func")):
                result_lines.append(line)
            else:
                result_lines.append(self._slash_re.sub(r"\1", line))
        return "\n".join(result_lines)

    def info(self, netlist: str, context: Optional[dict] = None) -> list[dict]:
        if not self._netlist_has_slashes(netlist):
            return []

        unique_names: set[str] = set()
        for line in netlist.split("\n"):
            stripped = line.strip()
            if (stripped.startswith("*") or stripped.startswith(".subckt")
                    or stripped.startswith(".param") or stripped.startswith(".func")):
                continue
            unique_names.update(self._slash_re.findall(line))
        if not unique_names:
            return []
        sorted_names = sorted(unique_names)
        return [
            {
                "fix": self.name,
                "detail": (
                    f"stripped '/' from {len(sorted_names)} node names: "
                    f"{', '.join(sorted_names[:5])}"
                    f"{'...' if len(sorted_names) > 5 else ''}"
                ),
            }
        ]


class FixDiodePins(NetlistFix):
    """Swap anode and cathode nodes on D-device lines.

    KiCad's SPICE export lists the anode first, but some simulation dialects
    expect cathode first.  This fix swaps the two node columns.
    """

    name = "Swap diode pins (anode/cathode order)"

    _diode_re = re.compile(r"^(D\S+)\s+(\S+)\s+(\S+)(\s.*)?")

    def apply(self, netlist: str, context: Optional[dict] = None) -> str:
        result_lines = []
        for line in netlist.split("\n"):
            m = self._diode_re.match(line)
            if m:
                suffix = m.group(4) or ""
                result_lines.append(f"{m.group(1)} {m.group(3)} {m.group(2)}{suffix}")
            else:
                result_lines.append(line)
        return "\n".join(result_lines)

    def info(self, netlist: str, context: Optional[dict] = None) -> list[dict]:
        results: list[dict] = []
        for line in netlist.split("\n"):
            m = self._diode_re.match(line)
            if m:
                results.append(
                    {
                        "fix": self.name,
                        "detail": f"swapped anode/cathode for {m.group(1)}",
                    }
                )
        return results


class FixBJTPins(NetlistFix):
    """Re-order the three terminal nodes of BJTs, MOSFETs, and JFETs to the
    conventional SPICE order (C-B-E for BJTs, D-G-S for FETs).

    The calling code passes a ``sim_pins`` dictionary inside *context* that maps
    device reference designators to either a list of pin-type strings (in the
    order they appear in the raw netlist) or a dict mapping pin-type to its
    zero-based column index.  Example::

        context = {"sim_pins": {"Q1": ["E", "B", "C"]}}
    """

    name = "Reorder transistor pins to SPICE convention"

    _transistor_re = re.compile(r"^([QMJ]\S+)\s+(\S+)\s+(\S+)\s+(\S+)(\s.*)?")

    # SPICE conventional order: position 0 is collector/drain, 1 is base/gate, 2 is emitter/source
    _BJT_ORDER = ["C", "B", "E"]
    _FET_ORDER = ["D", "G", "S"]

    @staticmethod
    def _get_desired_order(name: str) -> list[str]:
        if name.startswith("Q"):
            return FixBJTPins._BJT_ORDER
        return FixBJTPins._FET_ORDER  # M or J

    def apply(self, netlist: str, context: Optional[dict] = None) -> str:
        sim_pins = (context or {}).get("sim_pins", {})

        result_lines = []
        for line in netlist.split("\n"):
            m = self._transistor_re.match(line)
            if m is None:
                result_lines.append(line)
                continue

            name = m.group(1)
            original_nodes = [m.group(2), m.group(3), m.group(4)]
            suffix = m.group(5) or ""

            device_pins = sim_pins.get(name)
            if not device_pins:
                # No context -- leave nodes as-is
                result_lines.append(line)
                continue

            # Build pin_type -> original_node mapping
            pin_to_node: dict[str, str] = {}
            if isinstance(device_pins, list):
                for i, pin_type in enumerate(device_pins):
                    if i < len(original_nodes):
                        pin_to_node[pin_type] = original_nodes[i]
            elif isinstance(device_pins, dict):
                # Two dict formats are supported:
                #   A) Sim.Pins: {"1": "E", "2": "B"} — key=pin-number, val=pin-name
                #   B) Direct:   {"E": 0, "B": 1}    — key=pin-name,  val=node-index
                first_val = next(iter(device_pins.values()), None)
                if isinstance(first_val, int):
                    # Format B: model-pin-name -> original-node-index
                    for pin_name, idx in device_pins.items():
                        if isinstance(idx, int) and 0 <= idx < len(original_nodes):
                            pin_to_node[pin_name] = original_nodes[idx]
                else:
                    # Format A: symbol-pin-number -> model-pin-name
                    for sym_pin, model_pin in device_pins.items():
                        try:
                            idx = int(sym_pin) - 1
                        except (ValueError, TypeError):
                            continue
                        if 0 <= idx < len(original_nodes):
                            pin_to_node[model_pin] = original_nodes[idx]

            desired = self._get_desired_order(name)
            new_nodes = [pin_to_node.get(p, "NC") for p in desired]

            # If all pins are NC, the Sim.Pins names don't match our SPICE_ORDER
            # keys.  Leave the device unchanged rather than destroying it.
            if all(n == "NC" for n in new_nodes):
                result_lines.append(line)
                continue

            if new_nodes != original_nodes:
                _log.warning("FixBJTPins: reordered %s pins to %s (was %s)",
                             name, " ".join(new_nodes), " ".join(original_nodes))

            result_lines.append(
                f"{name} {new_nodes[0]} {new_nodes[1]} {new_nodes[2]}{suffix}"
            )

        return "\n".join(result_lines)

    def info(self, netlist: str, context: Optional[dict] = None) -> list[dict]:
        sim_pins = (context or {}).get("sim_pins", {})
        results: list[dict] = []
        for line in netlist.split("\n"):
            m = self._transistor_re.match(line)
            if m:
                name = m.group(1)
                if name in sim_pins:
                    results.append(
                        {
                            "fix": self.name,
                            "detail": f"reordered pins for {name}",
                        }
                    )
        return results


class MoveControlBlock(NetlistFix):
    """Move a ``.control`` ... ``.endc`` block so it sits immediately before
    the ``.end`` statement, as required by ngspice.
    """

    name = "Move .control/.endc block before .end"

    def apply(self, netlist: str, context: Optional[dict] = None) -> str:
        lines = netlist.split("\n")

        # Locate the first .control ... .endc pair
        control_idx: Optional[int] = None
        endc_idx: Optional[int] = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(".control") and stripped.split()[0] == ".control":
                if control_idx is None:
                    control_idx = i
            elif stripped.startswith(".endc") and stripped.split()[0] == ".endc":
                if control_idx is not None:
                    endc_idx = i
                    break

        if control_idx is None or endc_idx is None:
            return netlist

        # Extract the block
        control_block = lines[control_idx : endc_idx + 1]

        # Remove it from the body
        remaining = lines[:control_idx] + lines[endc_idx + 1 :]

        # Find .end in the remaining lines
        end_idx: Optional[int] = None
        for i, line in enumerate(remaining):
            stripped = line.strip()
            if stripped.startswith(".end") and stripped.split()[0] == ".end":
                end_idx = i
                break

        if end_idx is None:
            return netlist  # can't place without .end

        # Insert the control block just before .end
        result = remaining[:end_idx] + control_block + remaining[end_idx:]
        return "\n".join(result)

    def info(self, netlist: str, context: Optional[dict] = None) -> list[dict]:
        lines = netlist.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(".control") and stripped.split()[0] == ".control":
                return [
                    {
                        "fix": self.name,
                        "detail": f".control block found at line {i + 1}, will move before .end",
                    }
                ]
        return []
