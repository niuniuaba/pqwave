"""Abstract base classes for schematic-capture tool integration."""

import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional

from pqwave.models.state import ApplicationState


def resolve_ngspice(custom_path: str = "") -> str:
    """Resolve ngspice path with priority: custom_path > tool_paths setting > PATH."""
    if custom_path and os.path.isfile(custom_path):
        return custom_path
    state = ApplicationState()
    configured = state.tool_paths.get("ngspice", "")
    if configured and os.path.isfile(configured):
        return configured
    found = shutil.which("ngspice")
    if found:
        return found
    raise FileNotFoundError(
        "ngspice not found. Install ngspice or set the path in "
        "Settings > External Converter Paths."
    )


class NetlistFix(ABC):
    name: str = ""

    @abstractmethod
    def apply(self, netlist: str, context: Optional[dict] = None) -> str:
        ...

    @abstractmethod
    def info(self, netlist: str, context: Optional[dict] = None) -> list[dict]:
        ...


class SchematicBridge(ABC):
    @abstractmethod
    def export_netlist(self, sch_path: str) -> str:
        ...

    @abstractmethod
    def get_netlist_fixes(self) -> list[NetlistFix]:
        ...

    @abstractmethod
    def probe_net(self, net_name: str) -> None:
        ...

    @abstractmethod
    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        ...

    @abstractmethod
    def clear_probe(self) -> None:
        ...

    @abstractmethod
    def detect_tool(self) -> Optional[str]:
        ...

    @abstractmethod
    def is_tool_running(self) -> bool:
        ...

    @abstractmethod
    def get_watch_extensions(self) -> list[str]:
        ...
