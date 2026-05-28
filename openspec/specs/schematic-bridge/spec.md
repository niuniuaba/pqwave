# schematic-bridge Specification

## Purpose
Defines the SchematicBridge ABC and NetlistFix/NetlistPostProcessor framework — the reusable interface for integrating external schematic capture tools (KiCad, Lepton-EDA, Qucs-S) with pqwave.
## Requirements
### Requirement: SchematicBridge ABC

The system SHALL provide an abstract base class `SchematicBridge` in `pqwave/bridge/schem_bridge.py` that defines the interface for integrating external schematic capture tools with pqwave.

The interface SHALL define the following abstract methods:
- `export_netlist(sch_path: str) -> str` — export a SPICE netlist from a schematic file
- `get_netlist_fixes() -> list[NetlistFix]` — return post-processing fixes needed for this tool
- `probe_net(net_name: str) -> None` — highlight a net in the schematic tool
- `probe_part(ref: str, pin: str | None) -> None` — highlight a component or pin
- `clear_probe() -> None` — clear all highlights
- `detect_tool() -> str | None` — return path to the tool binary or None
- `is_tool_running() -> bool` — check if the tool process is running
- `get_watch_extensions() -> list[str]` — file extensions to watch for changes

#### Scenario: Subclass implements full interface
- **WHEN** a developer creates `class KiCadBridge(SchematicBridge)`
- **THEN** all abstract methods MUST be implemented or the class SHALL fail to instantiate

#### Scenario: Future tool integration
- **WHEN** a developer creates a Lepton-EDA or Qucs-S bridge
- **THEN** they SHALL only need to implement the `SchematicBridge` interface and provide tool-specific `NetlistFix` instances; the `NetlistPostProcessor` and file watcher infrastructure SHALL be reusable without modification

---

### Requirement: NetlistFix ABC and NetlistPostProcessor

The system SHALL provide an abstract base class `NetlistFix` in `pqwave/bridge/schem_bridge.py` for individual netlist text transforms.

Each `NetlistFix` SHALL have:
- `name: str` — human-readable fix name
- `apply(netlist: str, context: dict | None) -> str` — transform the netlist text
- `info(netlist: str) -> list[dict]` — dry-run: report changes without modifying

The system SHALL provide a `NetlistPostProcessor` class that:
- Accepts a list of `NetlistFix` instances at construction
- `process(netlist, context) -> str` — applies all fixes in sequence, returning the final netlist
- `dry_run(netlist, context) -> list[dict]` — reports what each fix would change without modifying

#### Scenario: Run fixes in sequence
- **WHEN** `process()` is called with a KiCad-exported netlist
- **THEN** fixes SHALL be applied in the order they were provided at construction
- **THEN** each fix receives the output of the previous fix as input

#### Scenario: Dry-run inspection
- **WHEN** `dry_run()` is called with a KiCad-exported netlist
- **THEN** each fix's `info()` method SHALL be called
- **THEN** results SHALL be aggregated into a list of dicts with keys `fix`, `detail`, and `count`

---

### Requirement: KiCad netlist post-processing fixes

The system SHALL provide four `NetlistFix` implementations in `pqwave/bridge/kicad/fixes.py` to correct known KiCad SPICE export issues.

**StripSlashes:**
- SHALL strip leading `/` from node names in component connection lines
- SHALL strip leading `/` from node names inside `V()` and `I()` expressions in behavioral source lines
- SHALL NOT strip `/` from lines inside `.subckt` port definitions or `.param`/`.func` expressions

#### Scenario: Strip slash from diode node
- **WHEN** the input netlist contains `D1 /d1 /ox D1N4148`
- **THEN** the output SHALL contain `D1 d1 ox D1N4148`

#### Scenario: Strip slash from B-source expression
- **WHEN** the input contains `B1 /out 0 V={V(/d1)}`
- **THEN** the output SHALL contain `B1 out 0 V={V(d1)}`

#### Scenario: Preserve hierarchical paths
- **WHEN** the input contains `XU1 /sheet1/net1 /sheet1/net2 opamp`
- **THEN** the leading `/` on multi-level hierarchical paths SHALL be preserved

**FixDiodePins:**
- SHALL swap the first two node names on lines starting with `D` followed by a reference designator
- SHALL preserve all other content on the line (model name, area, parameters)

#### Scenario: Swap diode anode/cathode
- **WHEN** the input contains `D3 AC_P GND D1N4148`
- **THEN** the output SHALL contain `D3 GND AC_P D1N4148`

#### Scenario: Skip non-diode D-lines
- **WHEN** the input contains a `.DC` analysis command or `.DISTO` line
- **THEN** those lines SHALL NOT be modified

**FixBJTPins:**
- SHALL reorder pins on Q (BJT), M (MOSFET), and J (JFET) device lines to match SPICE convention
- SHALL use `Sim.Pins` data from the `.kicad_sch` file, passed via the `context` dict
- For BJTs: SHALL reorder to Collector-Base-Emitter order
- For MOSFETs: SHALL reorder to Drain-Gate-Source order
- SHALL log a console warning for each reordered device

#### Scenario: Reorder 2N3904 BJT
- **WHEN** a Q-line has pin order E-B-C (TO-92 package in KiCad) and `Sim.Pins = "1=E 2=B 3=C"`
- **THEN** the output SHALL have pin order C-B-E

**MoveControlBlock:**
- SHALL locate any `.control`...`.endc` block in the netlist
- SHALL remove it from its current position
- SHALL re-insert it immediately before the `.end` line
- SHALL be a no-op if no `.control` block exists

#### Scenario: Move misplaced control block
- **WHEN** `.control`...`.endc` appears before circuit elements
- **THEN** the block SHALL be moved to just before `.end`

#### Scenario: No control block present
- **WHEN** the netlist contains no `.control` line
- **THEN** the netlist SHALL be returned unchanged

