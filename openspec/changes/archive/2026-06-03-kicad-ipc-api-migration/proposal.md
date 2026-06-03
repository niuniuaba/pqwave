## Why

The current KiCad integration shells out to `kicad-cli` for netlist export and parses `.kicad_sch` files with regex for symbol data. More critically, back-annotation (cross-probe from pqwave to KiCad) was never implemented because port 4243 is an internal Eeschema↔Pcbnew channel, not a public API. The KiCad IPC API — available from KiCad 10+ and maturing rapidly in KiCad 11 — provides the only public, stable path to cross-probe, and also eliminates subprocess overhead for netlist export and file parsing.

## What Changes

- **Replace `kicad-cli` subprocess** with `schematic.export_netlist(SNF_SPICE)` via the KiCad IPC API for SPICE netlist export
- **Replace regex-based `.kicad_sch` parsing** with `schematic.get_symbols()` for Sim.Pins extraction via structured IPC API objects
- **Add working cross-probe** via IPC API `run_action()` or direct selection manipulation, replacing the non-functional TCP port 4243 approach
- **Make `kicad-python` a prerequisite** (user-installed, not an automatic pqwave dependency) — pqwave detects it lazily at runtime via functionality checks (`hasattr`), not version numbers, with a clear error message if required APIs are missing
- **Keep `kicad-cli` as fallback** for netlist export when the IPC API is unavailable (KiCad < 10, or API not enabled)
- **Keep `StripSlashes` fix conditional** — KiCad 10.99.0 appears to have fixed the leading-slash issue at source; apply only when needed
- **Update the KiCad user guide** (`docs/kicad/guide.md`) to document IPC API prerequisites, setup steps (KiCad 10+, enable API, install kicad-python), connection troubleshooting, and the new cross-probe workflow
- **BREAKING**: KiCad 8 and 9 lose cross-probe capability entirely (never worked anyway). Netlist export via `kicad-cli` fallback remains available for these versions.

## Capabilities

### New Capabilities

- `kicad-ipc-api`: Connect to KiCad via IPC socket, export SPICE netlists, query schematic symbols/pins/nets/labels as structured objects, and cross-probe nets and components — all through the public IPC API instead of subprocess calls and regex parsing.

### Modified Capabilities

- `kicad-bridge`: The `KiCadBridge` class changes its internal implementation from `subprocess.run(["kicad-cli", ...])` to IPC API calls. The public interface (`export_netlist()`, `extract_sim_pins()`, `probe_net()`, `probe_part()`, `clear_probe()`) remains the same, but `probe_net()`/`probe_part()`/`clear_probe()` now actually work instead of being stubs. The `detect_tool()` and `is_tool_running()` methods gain IPC-based detection alongside existing `shutil.which()`/`pgrep` heuristics. The `_resolve_kicad_cli()` method gains an `_ensure_ipc_connection()` counterpart.

## Impact

- **Dependencies**: `kicad-python` (user-installed prerequisite, NOT listed in pqwave's setup.py/requirements; detected by functionality — `hasattr(kipy.KiCad, 'get_schematic')`)
- **Affected code**:
  - `pqwave/bridge/kicad/bridge.py` — primary changes: IPC connection, netlist export, Sim.Pins, cross-probe
  - `pqwave/bridge/kicad/cross_probe.py` — rewrite to use IPC API instead of TCP socket
  - `pqwave/bridge/kicad/file_watcher.py` — may add IPC-based change detection
  - `pqwave/bridge/kicad/control_bar.py` — add connection status indicator
  - `pqwave/bridge/kicad/fixes.py` — make `StripSlashes` conditional on KiCad version
  - `pqwave/bridge/schem_bridge.py` — possibly add `connect()/disconnect()` lifecycle methods
  - `pqwave/models/state.py` — add `kicad_api_enabled` preference
  - `pqwave/ui/settings_widget.py` — add IPC API configuration UI
  - `pqwave/ui/main_window.py` — update KiCad bridge wiring
  - `docs/kicad/guide.md` — update for IPC API prerequisites, setup, and cross-probe workflow
- **User requirements**:
  - KiCad 10+ installed
  - IPC API enabled in KiCad Preferences → Plugins
  - `kicad-python` installed in the same Python environment as pqwave
- **No changes** to Lepton-EDA or xschem bridges
