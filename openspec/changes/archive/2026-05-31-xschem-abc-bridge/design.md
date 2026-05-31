## Context

The pqwave codebase has three schematic-capture tool integrations, but only two (KiCad, Lepton-EDA) follow the SchematicBridge ABC framework. The xschem integration predates this framework and uses a reversed architecture: xschem opens a TCP client connection to pqwave (emulating the GAW waveform viewer protocol), rather than pqwave connecting to xschem as a cross-probe client.

The exploration phase confirmed that xschem's Tcl API is rich enough to support a full ABC-compliant bridge without any C code modifications. Specifically:

- **Netlist export**: `xschem -n -s -q --quit <file.sch>` produces a SPICE netlist via xschem's internal `global_spice_netlist()` — no external CLI tool needed beyond xschem itself
- **Cross-probe (pqwave→xschem)**: xschem's built-in `xschem_server` (Tcl-eval-over-TCP) can execute `probe_net "name"` and `select_inst "ref"` to highlight nets and components. A dedicated companion Tcl script provides ABC-protocol translation.
- **Wave push (xschem→pqwave)**: The existing GAW-compatible `XschemServer` on port 2026 is preserved as a `WaveReceiver` within the bridge, so the Alt+G "Send selected net/pins to Viewer" workflow continues unchanged
- **File watching**: `.sch` files require mtime+size polling (same as Lepton), since xschem uses atomic saves like KiCad
- **No netlist fixes**: xschem's SPICE output is clean (like Lepton's `spice-sdb` backend)

## Goals / Non-Goals

**Goals:**
- Implement `XschemBridge(SchematicBridge)` with all 8 abstract methods
- Deploy a companion Tcl script (`pqwave-server.tcl`) that provides an ABC-protocol TCP server within xschem — zero C code changes
- Preserve the existing Alt+G push workflow via the GAW-compatible wave receiver
- Add `XschemControlBar`, `XschemFileWatcher`, session API, and menu integration following the established KiCad/Lepton pattern
- Refactor existing `XschemServer`/`CommandHandler`/`WindowRegistry` from `pqwave/communication/` into `pqwave/bridge/xschem/` under bridge management

**Non-Goals:**
- Modifying xschem C source code (hilight.c, scheduler.c, callback.c, etc.)
- Automatic click-to-send reverse cross-probe — xschem's Alt+G manual push is the intended workflow
- Back-annotation (DC stamps, floating labels) — deferred to a future change
- In-schematic menus within xschem (Netlist > SPICE, Simulation > ngspice, Wave View > pqwave) — deferred; the Tcl companion script infrastructure supports adding these later
- Replacing the GAW protocol with a new format for xschem→pqwave communication

## Decisions

### Decision 1: pqwave as TCP client for cross-probe (ABC pattern), pqwave as TCP server for wave push (GAW pattern)

**Chosen**: Hybrid — pqwave connects to xschem for cross-probe (ABC direction); xschem connects to pqwave for wave push (preserved GAW direction).

**Alternatives considered**:
- *Flip everything to pqwave-as-client*: Would require a new xschem→pqwave protocol for wave push, breaking Alt+G. Rejected because Alt+G is a core xschem workflow that users rely on.
- *Flip everything to xschem-as-client*: Would make cross-probe unnatural (xschem polling pqwave). Rejected because it doesn't match the ABC pattern and prevents cursor-driven cross-probe.

**Rationale**: Two TCP channels serve two different purposes. The cross-probe channel (pqwave→xschem) is event-driven and semantically matches KiCad/Lepton. The wave push channel (xschem→pqwave) is batch-oriented and semantically matches xschem's existing "send to viewer" mental model.

### Decision 2: Companion Tcl script with ABC protocol translation

**Chosen**: Deploy `pqwave-server.tcl` to `~/.config/xschem/` that listens on a configurable port (default 2021), parses `$NET:`/`$PART:`/`$CLEAR` commands, and translates them to xschem's built-in Tcl API (`probe_net`, `select_inst`, `xschem unhilight_all`).

**Alternatives considered**:
- *Send raw Tcl commands directly from XschemBridge*: Simpler but breaks protocol consistency with KiCad/Lepton. `XschemBridge.probe_net()` would contain xschem-specific Tcl strings instead of the generic `$NET:` format. Rejected on abstraction cleanliness.
- *Modify xschem C code to add a native ABC protocol handler*: Cleanest but violates the "no C changes" constraint. Not upstreamable without xschem maintainer buy-in.

**Rationale**: The companion Tcl script is ~80 lines, follows the exact same pattern as lepton's `pqwave-server.scm` (Scheme), and keeps the bridge layer protocol-agnostic. The Tcl script is additive — it does not modify any existing xschem file.

### Decision 3: File watching via QTimer polling (same as Lepton)

**Chosen**: 1-second mtime+size polling via `QTimer`, NOT `QFileSystemWatcher`.

**Alternatives considered**:
- *QFileSystemWatcher*: Works for KiCad because KiCad writes the file and QFSW detects the inode change. xschem does atomic saves (write temp, rename), which can confuse QFSW on some Linux configurations. Rejected for reliability.
- *Inotify/watchdog*: Overkill for a single-file watch. Adds dependency. Rejected.

**Rationale**: Same approach as Lepton-EDA. Consistent, reliable, no external dependencies.

### Decision 4: Wave receiver as internal bridge component — eliminate pqwave/communication/

**Chosen**: Move `XschemServer` + `CommandHandler` + `WindowRegistry` from `pqwave/communication/` into `pqwave/bridge/xschem/`, then delete the now-empty `pqwave/communication/` package entirely.

**Alternatives considered**:
- *Keep wave receiver in communication/ and reference from bridge*: Would leave xschem-specific code split across two packages. Rejected for cohesion.
- *Drop wave receiver entirely*: Would break Alt+G. Rejected.

**Rationale**: `pqwave/communication/` was created as a temporary home for the pre-ABC xschem integration. It has never contained anything other than xschem-specific code. Under the ABC framework, all bridge-specific communication belongs in `pqwave/bridge/<tool>/`. Once the three modules move, the package is empty — deleting it eliminates an unnecessary layer and makes the import graph flatter.

### Decision 5: Zero netlist fixes

**Chosen**: `get_netlist_fixes()` returns an empty list. xschem's SPICE netlist output is clean — it doesn't inject leading slashes (KiCad), doesn't have diode/BJT pin ordering issues, and doesn't place `.control` blocks incorrectly.

**Rationale**: Empirical verification during exploration. xschem's `spice_netlist.c` produces standard SPICE output. If issues are discovered later, fixes can be added incrementally via the `NetlistFix` ABC.

## Risks / Trade-offs

- **[Risk] xschem CLI not in PATH** → `detect_tool()` returns `None`; user sees friendly error with path configuration instructions. Same pattern as KiCad/Lepton.
- **[Risk] xschem_listen_port not configured** → Cross-probe requires users to add `set xschem_listen_port 2021` to their `xschemrc`. The companion Tcl script deployment process documents this requirement and can optionally auto-configure it.
- **[Risk] Tcl companion script not loaded** → Cross-probe connections fail silently (emit `error_occurred`). The bridge auto-deploys the script to `~/.config/xschem/` on first use (same pattern as Lepton's Scheme script auto-deployment).
- **[Risk] Port conflict with KiCad (4243) or Lepton (9424)** → Port validation on startup prevents conflicts. The cross-probe port (default 2021) is distinct from the wave receiver port (2026) and KiCad (4243).
- **[Trade-off] Two TCP ports instead of one** → The hybrid architecture uses port 2021 (cross-probe, pqwave→xschem) and port 2026 (wave receiver, xschem→pqwave). This is slightly more complex to explain but correctly separates the two communication directions with different lifetimes and protocols.
