## Why

The xschem integration is the oldest schematic-tool bridge in pqwave, built before the SchematicBridge ABC framework existed. KiCad and Lepton-EDA have since been integrated under this framework with a consistent architecture: `SchematicBridge` subclass, netlist post-processing, file watching, cross-probe via TCP, control bar, and session API. The xschem integration must be re-engineered to match this pattern — consolidating three tool-specific code paths into one uniform bridge layer, without requiring any changes to xschem's C source code.

## What Changes

- **New `XschemBridge(SchematicBridge)`** class implementing the full ABC interface: netlist export via `xschem -n -s -q --quit`, zero netlist fixes (xschem produces clean SPICE), cross-probe via xschem's built-in Tcl TCP server, and file watching on `.sch` files
- **New Tcl companion script** (`pqwave-server.tcl`) deployed to `~/.config/xschem/` and sourced via `xschemrc`, providing a dedicated TCP server that translates ABC protocol commands (`$NET:`, `$PART:`, `$CLEAR`) into xschem Tcl API calls — no C code modifications needed
- **New `XschemControlBar`** widget following the same layout pattern as `KiCadControlBar` and `LeptonControlBar`
- **New `XschemFileWatcher`** polling `.sch` files via `QTimer` (same approach as Lepton, since xschem's atomic save requires it)
- **New session API commands**: `xschem_watch`, `xschem_unwatch`, `xschem_simulate`, `xschem_probe_net`, `xschem_probe_part`, `xschem_clear`, `xschem_config`
- **Menu integration**: "Xschem Bridge" submenu in File menu (Watch Schematic..., Simulate Now, Stop Watching, Cross-Probe submenu)
- **Preserve existing Alt+G workflow**: The GAW-compatible `XschemServer` on port 2026 continues to receive `table_set`/`copyvar` commands from xschem's built-in "Send selected net/pins to Viewer" action — no regression in existing push functionality
- **Deprecation of standalone xschem wiring**: The `XschemServer`/`CommandHandler` directly in `main.py` and `main_window.py` is refactored into `pqwave/bridge/xschem/` and managed by `XschemBridge`. The `--xschem-port`, `--xschem-ba-port`, `--no-xschem-server` CLI flags continue to work.

## Capabilities

### New Capabilities

- `xschem-bridge`: Full SchematicBridge implementation for xschem — netlist export via CLI, ABC-protocol cross-probe via companion Tcl TCP server, file watching, control bar, simulation pipeline, and session API. Preserves existing Alt+G push workflow via GAW-compatible wave receiver.

### Modified Capabilities

<!-- None. The SchematicBridge ABC is designed for exactly this extension pattern and requires no changes. -->

## Impact

- **New files**: `pqwave/bridge/xschem/__init__.py`, `bridge.py`, `cross_probe.py`, `file_watcher.py`, `control_bar.py`; companion Tcl script `share/pqwave-server.tcl`
- **Modified files**: `pqwave/main.py` (register XschemBridge, keep CLI flags), `pqwave/ui/main_window.py` (wire bridge signals, add menu), `pqwave/session/api.py` (add xschem_* commands), `pqwave/bridge/__init__.py` (export XschemBridge)
- **Refactored**: Move xschem wave-receiver logic from `pqwave/communication/xschem_server.py` into `pqwave/bridge/xschem/wave_receiver.py` (keeps GAW protocol, but under bridge management)
- **No changes to**: xschem C source code, xschem Tcl scripts (companion script is additive, sourced via `xschemrc`)
- **Dependencies**: xschem must be in PATH for netlist export; xschem's `xschem_listen_port` must be configured for cross-probe
