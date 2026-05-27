## 1. Abstract Framework (bridge/)

- [x] 1.1 Create `pqwave/bridge/__init__.py` with re-exports of `SchematicBridge`, `NetlistFix`, `NetlistPostProcessor`
- [x] 1.2 Create `pqwave/bridge/schem_bridge.py` with `SchematicBridge` ABC (8 abstract methods) and `NetlistFix` ABC (apply, info, name)
- [x] 1.3 Create `pqwave/bridge/netlist_postprocessor.py` with `NetlistPostProcessor` class (process, dry_run)
- [x] 1.4 Write `pqwave/tests/test_schem_bridge.py`: verify ABC instantiation fails on incomplete subclass, test post-processor with mock fixes

## 2. KiCad Bridge Core

- [x] 2.1 Create `pqwave/bridge/kicad/__init__.py` with re-exports
- [x] 2.2 Create `pqwave/bridge/kicad/bridge.py` with `KiCadBridge(SchematicBridge)`: export_netlist (kicad-cli via subprocess.run), simulate pipeline, tool detection (shutil.which + tool_paths override), extract_sim_pins from .kicad_sch
- [x] 2.3 Write `pqwave/tests/test_kicad_bridge.py`: mock subprocess, test export failure modes, test tool detection

## 3. Netlist Post-Processing Fixes

- [x] 3.1 Create `pqwave/bridge/kicad/fixes.py` with `StripSlashes` — strip leading `/` from node names in component lines and B-source expressions
- [x] 3.2 Add `FixDiodePins` — swap first two nodes on D-device lines
- [x] 3.3 Add `FixBJTPins` — reorder Q/M/J device pins using Sim.Pins from context dict
- [x] 3.4 Add `MoveControlBlock` — relocate .control/.endc to before .end
- [x] 3.5 Write `pqwave/tests/test_kicad_fixes.py`: test each fix against sample netlist text fixtures, verify correct transforms, verify idempotency

## 4. Cross-Probe Client

- [x] 4.1 Create `pqwave/bridge/kicad/cross_probe.py` with `CrossProbeClient(QObject)`: TCP connect to localhost:port, send_command, probe_net, probe_part, clear, connected/disconnected/error_occurred signals
- [x] 4.2 Write `pqwave/tests/test_kicad_cross_probe.py`: mock socket, verify command formatting, test KiCad-not-running scenario

## 5. TCP Port Conflict Prevention

- [x] 5.1 Add port conflict validation in `pqwave/main.py` startup: verify that xschem server port, xschem back-annotation port, and KiCad cross-probe port are all distinct
- [x] 5.2 Display clear error message and exit if any two ports conflict, listing both conflicting port numbers and their associated tools
- [x] 5.3 Add unit test for port conflict detection in `pqwave/tests/test_kicad_integration.py`

## 6. Settings and State

- [x] 6.1 Add `"kicad_cli"` and `"ngspice"` keys to `ApplicationState.tool_paths` in `pqwave/models/state.py`
- [x] 6.2 Add kicad-cli and ngspice path input fields to "External Converter Paths" group in `pqwave/ui/settings_widget.py`
- [x] 6.3 Update `_save_global_prefs()` and `_load_global_prefs()` in `pqwave/ui/main_window.py` to include new tool path keys

## 7. File Watcher and Control Bar

- [x] 7.1 Create `pqwave/bridge/kicad/file_watcher.py` with `KiCadFileWatcher(QObject)`: QFileSystemWatcher wrapper, file_changed signal, atomic save handling (200ms re-watch delay), watch/unwatch
- [x] 7.2 Create `pqwave/bridge/kicad/control_bar.py` with `KiCadControlBar(QWidget)`: status label, Simulate Now button, Stop Watching button, MCControlBar-style layout (40px max height, horizontal), simulate_clicked/unwatch_clicked signals

## 8. MainWindow Integration

- [x] 8.1 Add "KiCad Bridge" submenu to File menu in `pqwave/ui/menu_manager.py` with Watch Schematic, Simulate Now, Stop Watching, and Cross-Probe submenu actions
- [x] 8.2 Add callbacks in `pqwave/ui/main_window.py`: _on_kicad_watch (file dialog + starts watcher), _on_kicad_simulate, _on_kicad_unwatch, _on_kicad_probe_selected, _on_kicad_clear_probe
- [x] 8.3 Implement `_start_kicad_watch()` in MainWindow: create KiCadControlBar (lazy), insert into upper_layout (MCControlBar pattern), wire signals, create KiCadFileWatcher and CrossProbeClient
- [x] 8.4 Implement `_run_kicad_pipeline()` in MainWindow: export → post-process → ngspice → SessionAPI.load() → update signal browser
- [x] 8.5 Handle cross-probe from trace click: connect cursor/focus events to CrossProbeClient.probe_net with the selected trace's source net name
- [x] 8.6 Implement cursor-driven back-annotation: when user places/moves cursor on a trace, debounce (250ms) and send cross-probe command for the trace's net; display cursor X/Y values and net name in status bar
- [x] 8.7 Add `--kicad-port` CLI argument to `pqwave/main.py` (default 4243)

## 9. Session API Commands

- [x] 9.1 Add `KiCadBridge` reference to `SessionAPI` or use ApplicationState to access bridge state
- [x] 9.2 Register `@api_command("kicad_watch", ...)`, `kicad_unwatch`, `kicad_simulate`, `kicad_probe_net`, `kicad_probe_part`, `kicad_clear`, `kicad_config` in `pqwave/session/api.py`
- [x] 9.3 Add mutation callback dispatch cases in `pqwave/ui/main_window.py` `_on_session_mutation` for each kicad_* action

## 10. Example Schematic and Documentation

- [x] 10.1 Create `docs/kicad/examples/back_annotate.kicad_sch` — two-stage 2N3904 BJT amplifier, 12V supply, 1kHz 50mV input, capacitive inter-stage coupling
- [x] 10.2 Verify `docs/kicad/guide.md` covers all bridge features and that all three example tutorials reference existing files

## 11. Integration Tests

- [x] 11.1 Write `pqwave/tests/test_kicad_integration.py`: full pipeline test with bridge.kicad_sch fixture, verify .raw loads and v(r1) ≈ +98V, port conflict detection
- [x] 11.2 Write `pqwave/tests/test_kicad_e2e.py`: file watcher simulation, cross-probe command verification, cursor back-annotation, tool detection
- [x] 11.3 Manual E2E: open KiCad, save schematic, verify auto-simulate, place cursor on trace, verify KiCad net highlight, move cursor, verify highlight follows
