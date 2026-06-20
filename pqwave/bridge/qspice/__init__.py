"""QSPICE bridge integration.

Provides the headless simulation runner that invokes QSPICE64.exe
(under Wine on Linux) and opens .qraw results in pqwave.
"""

from pqwave.bridge.qspice.wrapper import (
    QspiceBridgeRunner,
    resolve_qspice,
    resolve_qux,
)

__all__ = [
    "QspiceBridgeRunner",
    "resolve_qspice",
    "resolve_qux",
]
