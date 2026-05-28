## 1. Package Structure

- [x] 1.1 Create `pqwave/bridge/lepton/` package with `__init__.py`
- [x] 1.2 Create `pqwave/bridge/lepton/pqwave-server.scm` — Guile Scheme cross-probe/annotation server

## 2. LeptonBridge Core

- [x] 2.1 Implement `LeptonBridge(SchematicBridge)` class in `bridge.py` with `export_netlist()`, `get_netlist_fixes()` (empty list), `detect_tool()`, `is_tool_running()`, `get_watch_extensions()`
- [x] 2.2 Implement `_resolve_lepton_netlist()` and `_resolve_ngspice()` with `shutil.which()` + `tool_paths` override
- [x] 2.3 Implement `simulate()` pipeline: export → post-process (no-op) → ngspice → result dict

## 3. File Watcher

- [x] 3.1 Implement `LeptonFileWatcher(QObject)` in `file_watcher.py` with `watch()`, `unwatch()`, `file_changed` signal
- [x] 3.2 Handle lepton-schematic save patterns (atomic save detection if applicable)

## 4. Cross-Probe Client

- [x] 4.1 Implement `LeptonCrossProbeClient(QObject)` in `cross_probe.py` with TCP connection to localhost:9424
- [x] 4.2 Implement `probe_net()`, `probe_part()`, `clear()` methods sending `$NET`, `$PART`, `$CLEAR` commands
- [x] 4.3 Implement `annotate_dc()`, `annotate_label()`, `clear_annotations()`, `clear_dc_stamps()` methods
- [x] 4.4 Implement auto-deployment of Scheme server to `~/.config/lepton-eda/scheme/autoload/pqwave-server.scm`
- [x] 4.5 Emit `connected()`, `disconnected()`, `error_occurred(str)`, and `net_selected(str)`, `part_selected(str)` signals
- [x] 4.6 Read incoming `$SELECTED:net` and `$SELECTED:part` messages from the socket and emit corresponding signals

## 5. Scheme Server

- [x] 5.1 Implement TCP server in pqwave-server.scm using `(ice-9 sockets)` and `(ice-9 threads)`
- [x] 5.2 Implement `open-page-hook` handler to build netname→object and refdes→object maps
- [x] 5.3 Implement `$NET` handler: find net objects by netname attribute, call `select-object!` and `schematic_canvas_zoom_object`
- [x] 5.4 Implement `$PART` handler: find component by refdes attribute, call `select-object!` and `schematic_canvas_zoom_object`
- [x] 5.5 Implement `$CLEAR` handler: deselect all objects
- [x] 5.6 Implement `$ANNOTATE:DC` handler: modify netname attribute value with DC stamp
- [x] 5.7 Implement `$ANNOTATE:LABEL` handler: create floating text via `make-text` + `page-append!` and track for removal
- [x] 5.8 Implement `$CLEAR:ANNOTATIONS` handler: remove all tracked label objects via `page-remove!`
- [x] 5.9 Implement `$CLEAR:DC` handler: strip DC suffixes from netname attributes
- [x] 5.10 Register `select-objects-hook` to detect user clicks; extract netname/refdes and send `$SELECTED:net`/`$SELECTED:part` over TCP to pqwave
- [x] 5.11 Handle errors gracefully with Guile `catch`; log to stderr
- [x] 5.12 Define `&spice-netlist` action: run `lepton-netlist -g spice-sdb -o <base>.cir <file>` via `system*`
- [x] 5.13 Define `&sim-ngspice` action: run `lepton-netlist` then `ngspice -b -r <base>.raw <base>.cir` via `system*`
- [x] 5.14 Define `&wave-pqwave` action: launch `pqwave <base>.raw` via `system*`
- [x] 5.15 Add "SPICE" entry to existing Netlist menu via `add-menu`
- [x] 5.16 Add "Simulation > ngspice" menu via `add-menu`
- [x] 5.17 Add "Wave View > pqwave" menu via `add-menu`

## 6. Control Bar

- [x] 6.1 Implement `LeptonControlBar(QWidget)` in `control_bar.py` with status label, Simulate Now, Annotate DC, Clear Annotations, Stop Watching buttons
- [x] 6.2 Follow `MCControlBar` layout pattern (horizontal, 40px max height)
- [x] 6.3 Disable Simulate/Annotate buttons during simulation; enable Annotate DC only after successful simulation

## 7. Session API

- [x] 7.1 Register `lepton_watch(path)`, `lepton_unwatch()`, `lepton_simulate()` commands in `session/api.py`
- [x] 7.2 Register `lepton_probe_net(name)`, `lepton_probe_part(ref, pin=None)`, `lepton_clear()` commands
- [x] 7.3 Register `lepton_annotate_dc(voltages=None)`, `lepton_clear_annotations()` commands
- [x] 7.4 Register `lepton_config(key, value=None)` command
- [x] 7.5 Follow existing `@api_command` mutation callback pattern

## 8. Menu Integration

- [x] 8.1 Add "Lepton Bridge" submenu to File menu in `main_window.py`
- [x] 8.2 Wire Watch Schematic, Simulate Now, Annotate DC, Clear Annotations, Stop Watching actions
- [x] 8.3 Add Cross-Probe submenu with Probe Selected Net and Clear Highlight
- [x] 8.4 Disable actions when no file is being watched

## 9. Settings UI

- [x] 9.1 Add lepton-netlist and ngspice path fields to Settings dialog
- [x] 9.2 Persist paths to `ApplicationState.tool_paths` and `~/.pqwave/prefs.json`

## 10. Integration & Wiring

- [x] 10.1 Wire `LeptonBridge`, `LeptonFileWatcher`, `LeptonCrossProbeClient`, and `LeptonControlBar` in `MainWindow`
- [x] 10.2 Implement auto-simulation trigger from `file_changed` signal
- [x] 10.3 Implement cursor-driven cross-probe with 250ms debounce
- [x] 10.4 Implement DC annotation population from simulation results
- [x] 10.5 Wire port conflict validation (9424 vs xschem 2026/2021, KiCad 4243)

## 11. Testing

- [x] 11.1 Test netlist export with TwoStageAmp and RF_Amp example schematics
- [x] 11.2 Test simulation pipeline end-to-end (export → ngspice → load .raw)
- [x] 11.3 Test file watcher with actual lepton-schematic saves
- [x] 11.4 Test cross-probe net highlighting in running lepton-schematic
- [x] 11.5 Test back-annotation (DC stamps, floating labels, clear) in running lepton-schematic
- [x] 11.6 Test Session API commands in headless mode
- [x] 11.7 Test error handling: missing tools, invalid schematics, connection failures
- [x] 11.8 Test port conflict detection

## 12. Documentation

- [x] 12.1 Write lepton-eda bridge user guide at `docs/lepton/guide.html` — HTML format with inline CSS, following the KiCad guide structure (Part 1: Feature Reference, Part 2: Worked Tutorials)
- [x] 12.2 Tutorial 1: TwoStageAmp — complete in-schematic workflow (Netlist > SPICE → Simulation > ngspice → Wave View > pqwave), transient analysis, signal browsing
- [x] 12.3 Tutorial 2: Bidirectional cross-probe — click net in schematic plots trace in pqwave; click trace in pqwave highlights net in schematic; cursor tracking with status bar display
- [x] 12.4 Tutorial 3: DC back-annotation — stamp operating point voltages on schematic via Annotate DC; verify values; clear annotations; restore workflow
- [x] 12.5 Document Scheme server deployment, port configuration, and troubleshooting
- [x] 12.6 Document back-annotation workflow (DC stamp vs floating labels vs clear) and persistence behavior
- [x] 12.7 Include standalone scripting example (headless Session API usage)
- [x] 12.8 Create example schematics in `docs/lepton/examples/` if needed (copy from lepton-eda examples or create new ones)
