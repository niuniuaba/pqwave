"""Abstract base classes for schematic-capture tool integration."""

from abc import ABC, abstractmethod
from typing import Optional


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
