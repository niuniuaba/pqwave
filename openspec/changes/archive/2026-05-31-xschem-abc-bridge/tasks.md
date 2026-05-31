## 1. Module scaffolding and companion Tcl script

- [ ] 1.1 Create `pqwave/bridge/xschem/` package with `__init__.py`, exporting `XschemBridge`
- [ ] 1.2 Create companion Tcl script `share/pqwave-server.tcl` with ABC-protocol TCP server (handles `$NET:`, `$PART:`, `$CLEAR`, persistent connections)
- [ ] 1.3 Add Tcl script auto-deployment logic (copy to `~/.config/xschem/` on first bridge use, log xschemrc configuration instructions)

## 2. XschemBridge core (netlist export + simulation pipeline)

- [ ] 2.1 Implement `XschemBridge(SchematicBridge)` in `pqwave/bridge/xschem/bridge.py` with `export_netlist()` via `xschem -n -s -q --quit --netlist_type spice`
- [ ] 2.2 Implement `get_netlist_fixes()` returning empty list, `get_watch_extensions()` returning `[".sch"]`
- [ ] 2.3 Implement `detect_tool()` via `shutil.which("xschem")` with `tool_paths` override and `is_tool_running()` via `pgrep/pgidof xschem`
- [ ] 2.4 Implement `simulate()` pipeline method: export → post-process → ngspice → return result dict
- [ ] 2.5 Add `ngspice` and `xschem` entries to `ApplicationState.tool_paths` with Settings UI fields

## 3. Cross-probe client (pqwave → xschem)

- [ ] 3.1 Implement `XschemCrossProbeClient(QObject)` in `pqwave/bridge/xschem/cross_probe.py` with TCP connection to `localhost:<port>` (default 2021)
- [ ] 3.2 Implement `probe_net(name)` sending `$NET: "name"`, `probe_part(ref, pin=None)` sending `$PART: "ref"`, `clear()` sending `$CLEAR`
- [ ] 3.3 Implement `connected`, `disconnected`, `error_occurred` Qt signals with connection timeout (2s)
- [ ] 3.4 Implement `XschemBridge.probe_net()`, `probe_part()`, `clear_probe()` delegating to cross-probe client (lazy instantiation)

## 4. Wave receiver refactor (xschem → pqwave, GAW protocol)

- [ ] 4.1 Move `pqwave/communication/xschem_server.py` → `pqwave/bridge/xschem/wave_receiver.py` as `WaveReceiver` class
- [ ] 4.2 Move `pqwave/communication/command_handler.py` into `wave_receiver.py` as `WaveCommandHandler`
- [ ] 4.3 Move `pqwave/communication/window_registry.py` into `pqwave/bridge/xschem/window_registry.py`
- [ ] 4.4 Delete `pqwave/communication/` package (all three modules moved; nothing else lives there). Update all imports in `pqwave/main.py` and `pqwave/ui/main_window.py` to point to `pqwave.bridge.xschem`
- [ ] 4.5 Keep `--xschem-port`, `--xschem-ba-port`, `--no-xschem-server`, `--xschem-send` CLI flags in `main.py` (no user-facing change)
- [ ] 4.6 Keep `xschem_ba_port` constructor parameter on `MainWindow` for backward compatibility

## 5. File watcher

- [ ] 5.1 Implement `XschemFileWatcher(QObject)` in `pqwave/bridge/xschem/file_watcher.py` with mtime+size polling via `QTimer` at 1s intervals
- [ ] 5.2 Implement `watch(path)`, `unwatch()`, and `file_changed` signal
- [ ] 5.3 Handle xschem atomic save pattern (detect temp-file-write-then-rename via mtime+size change)

## 6. Control bar widget

- [ ] 6.1 Implement `XschemControlBar(QWidget)` in `pqwave/bridge/xschem/control_bar.py` following `MCControlBar`/`KiCadControlBar`/`LeptonControlBar` layout pattern
- [ ] 6.2 Add status label, "Simulate Now" button (`simulate_clicked` signal), "Stop Watching" button (`unwatch_clicked` signal)
- [ ] 6.3 Implement lazy creation (hidden until file is watched), disable Simulate Now during simulation

## 7. Menu integration

- [ ] 7.1 Add "Xschem Bridge" submenu to File menu in `MainWindow._setup_menus()` with Watch Schematic..., Simulate Now, Stop Watching, Cross-Probe submenu (Probe Selected Net, Clear Highlight)
- [ ] 7.2 Wire menu action enabled/disabled state based on whether a file is being watched
- [ ] 7.3 Connect menu actions to bridge methods (watch triggers file dialog → `XschemFileWatcher.watch()`, simulate triggers `XschemBridge.simulate()`, etc.)

## 8. Session API

- [ ] 8.1 Register `@api_command` functions in `pqwave/session/api.py`: `xschem_watch`, `xschem_unwatch`, `xschem_simulate`, `xschem_probe_net`, `xschem_probe_part`, `xschem_clear`, `xschem_config`
- [ ] 8.2 Implement mutation callback pattern (emit in GUI mode, execute directly in headless mode)
- [ ] 8.3 Add port conflict validation: cross-probe port (default 2021) must not conflict with KiCad (4243), Lepton (9424), or xschem wave receiver (2026)

## 9. MainWindow and main.py wiring

- [ ] 9.1 Create `XschemBridge` instance in `main.py` (lazy, created when needed)
- [ ] 9.2 Wire wave receiver signals from `XschemBridge.wave_receiver` to `MainWindow` (table_set → load raw file, copyvar → add trace, etc.)
- [ ] 9.3 Wire cross-probe for cursor-driven back-annotation: cursor A placement → debounced 250ms `probe_net()` call with trace's source net name
- [ ] 9.4 Wire control bar into `MainWindow` panel grid (same insertion point as KiCad/Lepton control bars)
- [ ] 9.5 Connect file watcher `file_changed` → auto-simulation pipeline (if `auto_simulate` enabled)

## 10. Tests

- [ ] 10.1 Write unit tests for `XschemBridge.export_netlist()` (mock subprocess)
- [ ] 10.2 Write unit tests for `XschemBridge.simulate()` pipeline (mock subprocess)
- [ ] 10.3 Write unit tests for `XschemCrossProbeClient` (mock socket)
- [ ] 10.4 Write unit tests for `WaveReceiver` GAW protocol parsing (table_set, copyvar, JSON commands)
- [ ] 10.5 Write unit tests for `XschemFileWatcher` (mock QTimer, simulate mtime changes)
- [ ] 10.6 Write integration tests for session API commands
- [ ] 10.7 Update existing xschem tests (`test_xschem_server.py`, `test_xschem_e2e.py`) to reference new module paths
- [ ] 10.8 Verify no regressions: existing GAW push workflow (Alt+G) continues to work end-to-end
