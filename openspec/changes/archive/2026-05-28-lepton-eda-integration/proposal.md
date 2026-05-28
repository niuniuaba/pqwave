## Why

pqwave's `SchematicBridge` framework was designed to support multiple EDA tools, but only KiCad is currently implemented. Lepton-EDA is a lightweight, mature schematic capture tool with no built-in simulation or waveform viewer — pqwave fills that gap entirely. Empirical testing confirms the integration is straightforward: netlist export produces clean SPICE with zero post-processing fixes, and lepton-eda's Guile Scheme extension system supports a cross-probe server and live back-annotation without modifying a single line of C code.

## What Changes

- New **LeptonBridge** class implementing `SchematicBridge` ABC in `pqwave/bridge/lepton/`
- Netlist export via `lepton-netlist -g spice-sdb` (no `NetlistFix` instances needed — output is clean SPICE)
- **Bidirectional cross-probe**: pqwave ↔ lepton-schematic. pqwave → schematic highlighting via `select-object!`; schematic → pqwave trace plotting via `select-objects-hook` + TCP — clicking a net in lepton-schematic plots its waveform in pqwave (mirrors xschem behavior)
- **Back-annotation**: Simulation results (DC voltages, operating points) written onto the schematic as text labels or attribute stamps using lepton-eda's Scheme API (`select-object!`, `set-attrib-value!`, `page-append!`, `page-remove!`)
- File watcher for `.sch` files with auto-simulation on save
- Session API commands (`lepton_watch`, `lepton_simulate`, `lepton_probe_net`, `lepton_probe_part`, `lepton_clear`, `lepton_config`)
- Menu integration (File > Lepton Bridge submenu)
- Settings UI for `lepton-netlist` and `ngspice` tool paths
- A companion Scheme script (`pqwave/bridge/lepton/pqwave-server.scm`) deployed by the bridge into the user's lepton-eda autoload directory, which also adds in-schematic menus (Netlist > SPICE, Simulation > ngspice, Wave View > pqwave) for a complete xschem-style workflow from within the editor

## Capabilities

### New Capabilities

- `lepton-bridge`: SchematicBridge implementation for lepton-eda — netlist export, file watching, cross-probe, back-annotation, simulation pipeline, session API, and menu integration

### Modified Capabilities

None. The `schematic-bridge` ABC was designed for this use case and requires no changes.

## Impact

- New package: `pqwave/bridge/lepton/` (bridge.py, control_bar.py, file_watcher.py, cross_probe.py, pqwave-server.scm)
- New dependency: `lepton-netlist` (from lepton-eda package), auto-detected via `shutil.which()`
- No changes to existing bridge framework or KiCad bridge code
- User-facing: new File > Lepton Bridge menu, new control bar widget, new settings fields
