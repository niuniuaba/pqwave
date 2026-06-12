"""Qucs-S bridge — stateless filesystem configuration (no live TCP/IPC)."""

import os
import shutil
from typing import Optional

from pqwave.bridge.schem_bridge import SchematicBridge, NetlistFix
from pqwave.bridge.qucs_s.config import (
    get_config_path,
    is_configured_for_pqwave,
    apply_bridge_config,
    restore_config,
    detect_ngspice,
    read_config,
    write_config,
)

# Re-export for external use
__all__ = ["QucsSBridge"]


class QucsSBridge(SchematicBridge):
    """Bridge that configures Qucs-S to auto-launch pqwave after simulation.

    Unlike xschem/lepton bridges, this is NOT a live TCP connection.
    "Connect" means writing pqwave as NgspiceExecutable in ``qucs_s.conf``.
    After configuration, every simulation run from Qucs-S opens results in
    pqwave automatically.

    The bridge is **stateless** — every Connect / Disconnect reads the
    actual config file on disk, never relying on cached internal state.
    """

    name = "Qucs-S"

    def __init__(self):
        super().__init__()

    # ---- Required ABC methods ----

    def detect_tool(self) -> Optional[str]:
        """Check if Qucs-S config file exists."""
        path = get_config_path()
        return path if os.path.exists(path) else None

    def is_tool_running(self) -> bool:
        """Qucs-S has no live process to detect. Always False."""
        return False

    def is_configured(self) -> bool:
        """Check config on disk — both exe and params must be set."""
        return is_configured_for_pqwave()

    # ---- Status (always reads current disk state) ----

    def get_status(self) -> dict:
        """Return the current config state from disk.

        Keys: ``configured``, ``exe``, ``params``, ``config_path``.
        """
        cfg = read_config()
        return {
            "configured": self.is_configured(),
            "exe": cfg.get("General", "NgspiceExecutable", fallback=""),
            "params": cfg.get("General", "NgspiceParams", fallback=""),
            "config_path": get_config_path(),
        }

    # ---- Connect / Disconnect (stateless, idempotent) ----

    def connect(self, sch_path: Optional[str] = None) -> bool:
        """Write pqwave config — always, even if already configured.

        The subcommand MUST go in NgspiceParams (not NgspiceExecutable)
        because Qucs-S quotes the executable as a single token.

        Idempotent: calling Connect twice produces the same config.
        """
        pqwave_exe = shutil.which("pqwave")
        if not pqwave_exe:
            import sys
            pqwave_exe = sys.executable
            params = "-m pqwave.main --qucs-bridge"
        else:
            params = "--qucs-bridge"

        try:
            apply_bridge_config(pqwave_exe=pqwave_exe, pqwave_params=params)
            return True
        except Exception:
            return False

    def disconnect(self) -> bool:
        """Restore original Qucs-S config.

        Prefers the backup file created by :meth:`connect` so that any
        custom settings the user had are preserved.  Falls back to
        writing a safe default config if no backup exists.
        """
        backup = get_config_path() + ".pqwave_backup"
        if os.path.exists(backup):
            try:
                return restore_config(backup)
            except Exception:
                pass

        # No backup — write a safe default.
        ngspice = detect_ngspice() or "/usr/bin/ngspice"
        try:
            cfg = read_config()
            if not cfg.has_section("General"):
                cfg.add_section("General")
            cfg.set("General", "NgspiceExecutable", ngspice)
            cfg.set("General", "NgspiceParams", "")
            write_config(cfg)
            return True
        except Exception:
            return False

    # ---- Not applicable (no-ops / NotImplemented) ----

    def export_netlist(self, sch_path: str) -> str:
        raise NotImplementedError("Qucs-S owns netlist generation")

    def simulate(self, sch_path: str, raw_output: Optional[str] = None) -> dict:
        raise NotImplementedError("Qucs-S owns simulation")

    def probe_net(self, net_name: str) -> None:
        pass  # No cross-probe support

    def probe_part(self, ref: str, pin: Optional[str] = None) -> None:
        pass  # No cross-probe support

    def clear_probe(self) -> None:
        pass  # No cross-probe support

    def get_netlist_fixes(self) -> list[NetlistFix]:
        return []  # No fixes needed

    def get_watch_extensions(self) -> list[str]:
        return [".sch"]
