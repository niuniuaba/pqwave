## Why

KiCad is the most widely used open-source schematic capture tool, with a built-in SPICE simulator and wave viewer — but users who need serious waveform analysis quickly outgrow its limited plotting capabilities. pqwave already provides a powerful wave viewer with Monte Carlo analysis, correlation tools, and a session API. Integrating KiCad gives pqwave access to the largest open-source EDA user base while giving KiCad users production-grade analysis without touching KiCad's source code.

## What Changes

- **New `bridge/` package** with an abstract `SchematicBridge` base class and composable `NetlistFix` post-processing framework, designed to be reusable for future Lepton-EDA and Qucs-S integration
- **KiCad bridge implementation** that watches `.kicad_sch` files, exports SPICE netlists via `kicad-cli`, post-processes the netlist to fix four known KiCad export bugs, runs ngspice, and loads the `.raw` result
- **Bidirectional cross-probe**: clicking a trace in pqwave highlights the corresponding net or component in KiCad over its built-in TCP cross-probe server (port 4243)
- **Netlist post-processor** that automatically fixes: (1) `/` prefix on node names, (2) diode anode/cathode ordering, (3) BJT/MOSFET/JFET pin ordering to SPICE convention, (4) `.control`/`.endc` block placement
- **Session API commands** for headless/scripted KiCad workflow: `kicad_watch`, `kicad_simulate`, `kicad_probe_net`, `kicad_probe_part`, `kicad_clear`, `kicad_config`
- **User guide** (`docs/kicad/guide.md`) with feature reference and three worked tutorials using example `.kicad_sch` files

## Capabilities

### New Capabilities
- `schematic-bridge`: Abstract framework for integrating external schematic tools with pqwave. Defines `SchematicBridge` and `NetlistFix` base classes, plus a `NetlistPostProcessor` that runs fixes in sequence. Designed for reuse by KiCad, Lepton-EDA, and Qucs-S.
- `kicad-bridge`: KiCad-specific bridge implementing `SchematicBridge`. Handles netlist export via `kicad-cli`, post-processing with tool-specific fixes, ngspice simulation orchestration, file watching for schematic changes, and TCP cross-probe back-annotation to KiCad's built-in server.

### Modified Capabilities
<!-- No existing capabilities have spec-level requirement changes -->

## Impact

- **New dependency**: `kicad-cli` (ships with KiCad 8.0+) in PATH; ngspice (already a project dependency)
- **New files**: `pqwave/bridge/` (3 files), `pqwave/bridge/kicad/` (5 files), `docs/kicad/` (guide + 3 example `.kicad_sch` files)
- **Modified files**: `pqwave/models/state.py`, `pqwave/session/api.py`, `pqwave/ui/main_window.py`, `pqwave/ui/menu_manager.py`, `pqwave/ui/settings_widget.py`, `pqwave/main.py`
- **User-facing changes**: New "KiCad Bridge" submenu in File menu, new settings for tool paths, new API commands
- **No breaking changes** to existing functionality
