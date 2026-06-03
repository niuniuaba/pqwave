## Context

pqwave currently integrates with one external schematic tool (xschem) via TCP socket communication (`pqwave/communication/`). Adding KiCad requires a different architectural pattern: pqwave must be the **client** (connecting out to KiCad's cross-probe server) and the **orchestrator** (running the simulation pipeline). KiCad itself requires zero modifications — everything works with pre-built binaries.

Two additional tools (Lepton-EDA, Qucs-S) have been researched and will follow later. The bridge layer must be designed as a reusable framework from the start.

## Goals / Non-Goals

**Goals:**
- Reusable `SchematicBridge` ABC that Lepton-EDA and Qucs-S bridges can implement
- Composable `NetlistFix` post-processing framework
- KiCad bridge: file watching, netlist export via `kicad-cli`, post-processing, ngspice simulation, raw file loading
- Bidirectional cross-probe: pqwave trace click → KiCad schematic highlight via TCP port 4243
- Session API commands for headless/scripted use
- Settings UI for tool path configuration
- User guide with worked tutorials

**Non-Goals:**
- KiCad source modifications (strictly stock binaries)
- Auto-injection of `.control` blocks into netlists
- Real-time simulation progress streaming from ngspice
- Multi-sheet hierarchical schematic support (future for both KiCad and xschem)
- Lepton-EDA or Qucs-S implementation

## Decisions

### D1: New `pqwave/bridge/` package, not inside `communication/`

**Rationale:** The `communication/` package is for real-time bidirectional protocols (TCP servers). The bridge layer has a different concern: orchestrating a pipeline (export → fix → simulate → load). It's file-system-driven, not socket-driven. Placing it under `bridge/` makes the architectural distinction clear and avoids coupling with the xschem-specific command handler.

**Alternatives considered:** Extending `communication/` with a new server type. Rejected because KiCad integration is fundamentally a client, not a server, and the pipeline orchestration pattern has no analogue in the xschem code.

### D2: ABC-first design: `SchematicBridge` and `NetlistFix`

**Rationale:** The proposal lists three target tools (KiCad, Lepton-EDA, Qucs-S). Each has different netlist export mechanisms (kicad-cli, lepton-netlist, qucs -n), different cross-probe strategies (TCP, Guile server, file-watching), and different post-processing needs. Defining ABCs upfront forces a clean separation of generic framework from tool-specific code, and makes future bridges a matter of implementing the interface.

**Alternatives considered:** Build KiCad first, extract common patterns later. Rejected because the research phase already identified the common patterns, and retrofitting ABCs after implementation creates more work than designing them upfront.

### D3: Regex-based netlist fixes, not a full SPICE parser

**Rationale:** The four known KiCad export bugs are narrow and well-understood: (1) strip `/` from node names, (2) swap first two nodes on D-lines, (3) reorder Q/M/J pins using Sim.Pins, (4) relocate `.control` block. Regex handles all four correctly and is simpler than pulling in a SPICE parser dependency. The `NetlistFix` ABC provides the escape hatch: any future fix that needs real parsing can be implemented as a single new class.

**Alternatives considered:** Full SPICE parser via `ngspice` shared library or a Python SPICE parsing library. Rejected as heavyweight, fragile against tool-specific dialect variations, and unnecessary for four straightforward text transforms.

### D4: `subprocess.run()` not `QProcess` for external tool invocation

**Rationale:** Follows existing codebase conventions in `fst_adapter.py` and `ghw_adapter.py`. The pipeline runs synchronously triggered by the file watcher signal; no async process management is needed. `subprocess.run()` is simpler and the pipeline duration (< 5 seconds for typical circuits) is well within acceptable UI responsiveness.

**Alternatives considered:** `QProcess` with async signals. Rejected as over-engineered for the use case and inconsistent with existing patterns.

### D5: `QFileSystemWatcher` not `watchdog`

**Rationale:** `QFileSystemWatcher` is already available via the Qt dependency. For watching a single `.kicad_sch` file, it is sufficient. Adding a third-party library for this is unnecessary.

**Alternatives considered:** `watchdog` (Python library). Rejected due to unnecessary dependency overhead for single-file watching.

### D6: Lazy instantiation of bridge components

**Rationale:** Follows the `MCControlBar` pattern (`main_window.py:157`). The KiCad bridge (watcher, control bar, cross-probe client) is only created when the user explicitly opts in via "File > KiCad Bridge > Watch Schematic". Resources are not allocated until needed.

**Alternatives considered:** Always-visible KiCad status bar. Rejected as intrusive for users who don't use KiCad.

### D7: Probing starts from pqwave, not KiCad

**Rationale:** KiCad's cross-probe server (port 4243) already supports `$NET`, `$PART`, `$PAD` commands — pqwave can send these today with zero KiCad changes. The reverse direction (probe in KiCad → plot in pqwave) would require modifying KiCad's source or installing a plugin. pqwave loads ALL simulation signals, so the user browses in pqwave and back-annotates interesting findings to the schematic. For a simulation workflow, this is the right direction: the analysis cockpit drives the schematic, not vice versa.

### D8: Session API commands follow existing `@api_command` pattern

**Rationale:** All commands are registered in `session/api.py` using the decorator at line 28-41. The GUI/headless dispatch uses the existing `_on_mutation` callback pattern (lines 64, 138-139, 492-494). No new dispatch mechanism.

### D9: TCP port conflict prevention between xschem and KiCad

**Rationale:** xschem uses user-configurable TCP ports (default 2026 for server, 2021 for back-annotation). KiCad uses fixed ports (4243 for schematic, 4242 for PCB). If the user accidentally configures the xschem server port to 4243 (KiCad's cross-probe port) or sets `--kicad-port` to 2026 (xschem's port), one service silently fails. At startup, `main.py` SHALL validate that the xschem port, xschem back-annotation port, and KiCad cross-probe port are all distinct. If a conflict is detected, the program SHALL exit with a clear error message listing the conflicting ports.

**Alternatives considered:** Warn but continue. Rejected because a port conflict causes silent failures that are hard to debug — one TCP bind succeeds and the other fails, but the user may not notice until cross-probe stops working.

## Risks / Trade-offs

- **[Risk] `kicad-cli` path varies across OS/installation** → Mitigation: `shutil.which()` fallback + user-configurable `tool_paths` override in settings, same pattern as `fst2vcd`/`ghwdump`
- **[Risk] KiCad's cross-probe protocol may change in future versions** → Mitigation: Protocol is stable since KiCad 5.x (plain text over TCP). The `CrossProbeClient` is isolated in a single file; protocol changes require only that file's modification.
- **[Risk] `QFileSystemWatcher` may miss events on some filesystems** → Mitigation: KiCad's atomic save (delete+rename) is handled by delayed re-watching. Network filesystem edge cases are documented in troubleshooting.
- **[Risk] Regex-based fixes may produce false positives on malformed netlists** → Mitigation: The `info()` dry-run method lets users inspect fixes before simulation. Fixes are individually toggleable via `kicad_config`. The `NetlistFix` ABC allows replacement with a parser-based fix if needed.
- **[Trade-off] Cross-probe is unidirectional (pqwave → KiCad)** → Users cannot click a net in KiCad and have it plotted in pqwave. The file watcher partially mitigates this: save the schematic → pqwave auto-reloads everything.
