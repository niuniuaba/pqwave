"""VCD file parser adapter — wraps the vcdvcd library.

Provides VcdFile and VcdSignal classes that mirror the original API
while delegating all parsing to the established vcdvcd package.
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional

from vcdvcd import VCDVCD

_log = logging.getLogger(__name__)


def _parse_vcd_value(v: str) -> float:
    """Convert a VCD value string to a numeric representation.

    '0'/'1' → 0.0/1.0, 'x'/'X'/'z'/'Z' → -1.0,
    binary vectors parsed as floats, real-number values preserved.
    """
    if not v:
        return -1
    c = v[0]
    if c in '01':
        return int(v, 2) if len(v) > 1 else int(c)
    if c in 'bB':
        rest = v[1:]
        if not rest:
            return -1
        if any(ch in 'xXzZ' for ch in rest):
            return -1
        return int(rest, 2)
    if c in 'xXzZ':
        return -1
    # Real-number VCD values: 'r' followed by a float literal.
    # Preserve float precision instead of rounding to int.
    if c in 'rR':
        try:
            return float(v[1:]) if v[1:] else -1.0
        except (ValueError, TypeError):
            return -1
    # Other unhandled formats → unknown
    _log.debug("Unhandled VCD value type (first char=%r): %s", c, v[:20])
    return -1


class VcdSignal:
    """A single signal parsed from a VCD file, backed by vcdvcd's Signal."""

    def __init__(self, name: str, width: int, identifier: str,
                 tv: List[Tuple[int, str]]):
        self.name = name
        self.width = width
        self.identifier = identifier
        self.times: List[int] = [t for t, _ in tv]
        self.values: List[str] = [v for _, v in tv]

    def to_arrays(self, timescale: float = 1e-9) -> Tuple[np.ndarray, np.ndarray]:
        times = np.array(self.times, dtype=np.float64) * timescale
        values = np.array([_parse_vcd_value(v) for v in self.values],
                          dtype=np.float64)
        return times, values


class VcdFile:
    """Parser for IEEE 1364-2001 Value Change Dump files.

    Delegates to the vcdvcd library for all file parsing.
    """

    def __init__(self, filename: str):
        self.filename = filename

        try:
            vcd = VCDVCD(vcd_path=filename, store_tvs=True)
        except Exception as e:
            _log.error("Failed to parse VCD file %s: %s", filename, e)
            self.timescale = 1e-9
            self.date = ""
            self.version = ""
            self.signals = {}
            self._id_to_signal = {}
            return

        # Timescale: convert vcdvcd dict to float seconds (default 1 ns)
        ts_dict = vcd.timescale
        if ts_dict and "timescale" in ts_dict:
            self.timescale: float = float(ts_dict["timescale"])
        else:
            self.timescale: float = 1e-9

        self.date: str = ""
        self.version: str = ""

        # Build signals dict keyed by full reference name
        self.signals: Dict[str, VcdSignal] = {}
        self._id_to_signal: Dict[str, VcdSignal] = {}

        for ref_name in vcd.signals:
            identifier = vcd.references_to_ids.get(ref_name)
            if identifier is None:
                continue
            vcdvcd_sig = vcd.data.get(identifier)
            if vcdvcd_sig is None:
                continue
            try:
                width = int(vcdvcd_sig.size)
            except (ValueError, TypeError):
                width = 1

            sig = VcdSignal(
                name=ref_name,
                width=width,
                identifier=identifier,
                tv=vcdvcd_sig.tv,
            )
            self.signals[ref_name] = sig
            self._id_to_signal[identifier] = sig

        if not self.signals:
            _log.warning(
                "VCD file %s parsed successfully but contains no signals. "
                "The file may be corrupted or in an unsupported format.",
                filename)

    def get_signal_names(self) -> List[str]:
        return list(self.signals.keys())

    def get_signal(self, name: str) -> Optional[VcdSignal]:
        return self.signals.get(name)

    def get_signal_data(self, name: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        sig = self.signals.get(name)
        if sig is None:
            return None
        return sig.to_arrays(self.timescale)

    def get_max_time(self) -> float:
        """Return the maximum time (in seconds) across all signals."""
        max_t = 0.0
        for sig in self.signals.values():
            if sig.times:
                last_t = max(sig.times) * self.timescale
                if last_t > max_t:
                    max_t = last_t
        return max_t
