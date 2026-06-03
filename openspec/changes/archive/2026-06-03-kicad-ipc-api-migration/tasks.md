## 1. IPC Connection Layer in KiCadBridge

- [x] 1.1 Add `_ensure_ipc()` method to `KiCadBridge` — lazy import `kipy`, resolve socket path from `KICAD_API_SOCKET` env or platform default, connect with `ipc://` prefix, cache the `kipy.KiCad` instance, return True/False
- [x] 1.2 Add `kicad-python` functionality guard — `import kipy` then check `hasattr(kipy.KiCad, 'get_schematic')`, `hasattr(schematic, 'export_netlist')`, `hasattr(schematic, 'get_symbols')`; raise clear `RuntimeError` listing missing APIs if any fail (no version numbers in logic or messages)
- [x] 1.3 Add `_ipc_available` property — returns True when connected and version check passed
- [x] 1.4 Add IPC connection status to `KiCadControlBar` — show "connected via IPC API" vs "kicad-cli fallback" vs "disconnected"

## 2. IPC-Based Netlist Export

- [x] 2.1 Modify `export_netlist()` — try IPC path first: `schematic.export_netlist(format=SNF_SPICE)`, write to temp file, read back; fall through to existing `kicad-cli` subprocess on failure
- [x] 2.2 Handle IPC export errors — catch `ConnectionError`, `ApiError`, and generic exceptions; log and fall back to `kicad-cli`
- [x] 2.3 Update `simulate()` to pass through whichever export path was used — the pipeline should be transparent to the caller

## 3. IPC-Based Sim.Pins Extraction

- [x] 3.1 Add `_extract_sim_pins_ipc()` — call `schematic.get_symbols()`, traverse `definition.items` for `SchematicPin` objects, build `{ref: {pin_num: pin_name, ...}}` dict
- [x] 3.2 Modify `extract_sim_pins()` — try IPC path first; fall back to existing S-expression regex parsing
- [x] 3.3 Update `_build_context()` to pass IPC-extracted Sim.Pins into the fix pipeline

## 4. Conditional StripSlashes

- [x] 4.1 Make `StripSlashes` content-aware — inspect exported netlist for leading-slash pattern (`\s/[A-Za-z_]`); skip fix if no matches found
- [x] 4.2 Apply `StripSlashes` only when slashes detected; log "Detected leading slashes in netlist: applying..." vs "No leading slashes detected: skipping..."
- [x] 4.3 Log the decision — "No leading slashes detected in netlist: skipping slash-stripping fix" vs "Detected leading slashes in netlist: applying slash-stripping fix"

## 5. IPC-Based Cross-Probe

- [x] 5.1 Research and document the correct `run_action` names for Eeschema selection and highlighting (check KiCad source or test experimentally)
- [x] 5.2 Rewrite `CrossProbeClient` to use IPC API — replace TCP socket with `run_action()` or `AddToSelection`/`ClearSelection` IPC commands
- [x] 5.3 Implement `probe_net()` — resolve net name → selection in Eeschema via IPC
- [x] 5.4 Implement `probe_part()` — resolve reference designator → selection in Eeschema via IPC
- [x] 5.5 Implement `clear_probe()` — clear selection in Eeschema via IPC
- [x] 5.6 Graceful degradation — when IPC unavailable, log warning "Cross-probe unavailable — requires KiCad 10+ with IPC API enabled" instead of crashing
- [x] 5.7 Wire cursor-driven back-annotation in MainWindow — 250ms debounced QTimer that calls `probe_net()` for the trace under cursor A

## 6. Remove Legacy TCP Cross-Probe

- [x] 6.1 Remove TCP socket code from `CrossProbeClient` (the `socket.create_connection` path to port 4243)
- [x] 6.2 Update `CrossProbeClient` tests — replace mock socket tests with mock IPC client tests
- [x] 6.3 Remove port 4243 from conflict prevention in `main.py`

## 7. Settings and Preferences

- [~] 7.1 Add `kicad_api_enabled` preference to `ApplicationState` (default: True — try IPC first) — **DEFERRED**: auto-detection via `_ensure_ipc()` is better UX than a manual toggle; IPC is always tried first, falls back automatically
- [~] 7.2 Update `SettingsWidget` — add checkbox "Use KiCad IPC API (recommended)" with tooltip explaining requirements — **DEFERRED**: see 7.1
- [~] 7.3 Persist preference to `prefs.json` — **DEFERRED**: see 7.1

## 8. Session API Updates

- [x] 8.1 Add `kicad_status` API command — returns connection status, version, export path used (ipc/kicad-cli)
- [x] 8.2 Update existing `kicad_*` commands to reflect IPC vs fallback state

## 9. Tests

- [x] 9.1 Add tests for `_ensure_ipc()` — mock `kipy.KiCad`, test socket resolution, test version guard
- [x] 9.2 Add tests for IPC netlist export path — mock `schematic.export_netlist()`, verify SPICE format
- [x] 9.3 Add tests for IPC Sim.Pins extraction — mock `schematic.get_symbols()` with sample symbol data
- [x] 9.4 Add tests for content-aware `StripSlashes` — verify skipped when netlist has no slashes, applied when slashes present
- [x] 9.5 Add tests for IPC cross-probe — mock `run_action`, verify command strings
- [x] 9.6 Add tests for fallback path — verify kicad-cli is invoked when IPC mock returns failure
- [x] 9.7 Update existing `KiCadBridge` tests to work with the dual-path architecture
- [x] 9.8 Run full test suite — verify no regressions in xschem, Lepton, or existing KiCad tests

## 10. Documentation

- [x] 10.1 Update `docs/kicad/guide.md` — document IPC API prerequisites (KiCad 10+, enable IPC API in Preferences → Plugins, install kicad-python from Git)
- [x] 10.2 Add setup section to guide — step-by-step: verify KiCad version, enable API, install kicad-python, verify with test command
- [x] 10.3 Add cross-probe workflow to guide — how to probe nets/components from pqwave, cursor-driven back-annotation, clearing highlights
- [x] 10.4 Add troubleshooting section — "kicad-python not installed" error and fix, "IPC API not enabled" and fix, "missing get_schematic" and Git install command, connection refused (KiCad not running), socket not found
- [x] 10.5 Update the KiCad integration plan (`docs/superpowers/plans/2026-05-26-kicad-integration.md`) with IPC API changes
