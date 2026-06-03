# kicad-bridge Specification (Delta)

## Purpose
Delta to the existing `kicad-bridge` spec. Modifies netlist export to use IPC API with kicad-cli fallback, rewrites cross-probe to use IPC API instead of TCP port 4243, and adds IPC connection lifecycle management.

## MODIFIED Requirements

### Requirement: KiCad netlist export

The system SHALL export SPICE netlists from `.kicad_sch` files. The primary method SHALL be the KiCad IPC API (`schematic.export_netlist(format=SNF_SPICE)`) when available. The system SHALL fall back to `kicad-cli sch export netlist --format spice` when the IPC API is unavailable.

The `KiCadBridge` class in `pqwave/bridge/kicad/bridge.py` SHALL:
- Attempt IPC API export first if `_ensure_ipc()` succeeds
- Fall back to `kicad-cli` via `subprocess.run()` if IPC is unavailable
- Locate `kicad-cli` via `shutil.which()` with optional override from `ApplicationState.tool_paths["kicad_cli"]` (for fallback path only)
- Raise `FileNotFoundError` with a user-friendly message if both IPC and `kicad-cli` are unavailable
- Return the netlist text as a string

#### Scenario: IPC export succeeds
- **WHEN** `export_netlist("/path/to/circuit.kicad_sch")` is called and the IPC API connection is active
- **THEN** `schematic.export_netlist(format=SNF_SPICE)` SHALL be invoked via the IPC API
- **THEN** the netlist text SHALL be returned
- **THEN** NO subprocess SHALL be spawned

#### Scenario: IPC unavailable, fallback to kicad-cli
- **WHEN** `export_netlist()` is called but `_ensure_ipc()` fails (KiCad not running, API disabled, or `kicad-python` not installed)
- **THEN** `kicad-cli sch export netlist --format spice` SHALL be invoked via `subprocess.run()`
- **THEN** the netlist text SHALL be returned

#### Scenario: Neither IPC nor kicad-cli available
- **WHEN** `export_netlist()` is called but both IPC and `kicad-cli` are unavailable
- **THEN** `FileNotFoundError` SHALL be raised with message indicating how to install KiCad or enable the IPC API

---

### Requirement: Cross-probe back-annotation to KiCad

The system SHALL provide cross-probe back-annotation from pqwave to KiCad Eeschema via the KiCad IPC API, using `run_action()` or structured selection commands (`AddToSelection`/`ClearSelection`).

The `KiCadBridge` class SHALL:
- Accept cross-probe calls (`probe_net`, `probe_part`, `clear_probe`) and forward them to the IPC API
- Resolve net names and reference designators to schematic items via the IPC API
- Emit a log message when cross-probe succeeds or fails
- Handle the case where the IPC API is not available by logging a warning (no crash, no exception)

The previous TCP port 4243 cross-probe approach SHALL be removed entirely. The `CrossProbeClient` class SHALL be deleted or repurposed as an IPC-based cross-probe helper.

#### Scenario: Highlight a net via IPC
- **WHEN** `probe_net("R1")` is called and the IPC API connection is active
- **THEN** the net R1 SHALL be highlighted in the KiCad schematic editor
- **THEN** a log message SHALL indicate "KiCad: highlighted net R1"

#### Scenario: Highlight a component via IPC
- **WHEN** `probe_part("Q1")` is called and the IPC API connection is active
- **THEN** the component Q1 SHALL be highlighted and centered in KiCad

#### Scenario: Clear highlights via IPC
- **WHEN** `clear_probe()` is called
- **THEN** all cross-probe highlights SHALL be cleared

#### Scenario: IPC unavailable, cross-probe skipped
- **WHEN** any probe command is called but the IPC API connection is not available
- **THEN** a warning SHALL be logged: "Cross-probe unavailable — requires KiCad 10+ with IPC API enabled"
- **THEN** no exception SHALL be raised
- **THEN** the application SHALL continue normally

#### Scenario: Cursor-driven back-annotation
- **WHEN** the user places cursor A on a waveform trace at position X
- **THEN** the system SHALL send a cross-probe command for the trace's source net with a debounce delay of 250ms
- **THEN** KiCad SHALL highlight the corresponding net via the IPC API
- **WHEN** the user moves the cursor along the trace
- **THEN** the highlighted net SHALL update (debounced) to follow the cursor position

---

### Requirement: Tool path configuration

The system SHALL allow users to configure `kicad-cli` and `ngspice` paths via the Settings dialog and the `kicad_config` API.

The paths SHALL be stored in `ApplicationState.tool_paths` with keys `"kicad_cli"` and `"ngspice"`.
The paths SHALL be persisted to `~/.pqwave/prefs.json` alongside existing tool paths.
The Settings dialog SHALL include input fields for both paths in the "External Converter Paths" group.

The `kicad-cli` path SHALL be used only for the fallback export path and tool detection; when the IPC API is active, netlist export does not use `kicad-cli`.

#### Scenario: Custom ngspice path
- **WHEN** the user sets `tool_paths["ngspice"]` to `/opt/local/bin/ngspice`
- **THEN** `shutil.which("ngspice")` SHALL NOT be used
- **THEN** the specified path SHALL be invoked for simulation

#### Scenario: Default PATH detection
- **WHEN** no custom path is configured
- **THEN** `shutil.which("kicad-cli")` and `shutil.which("ngspice")` SHALL be used

#### Scenario: kicad-cli path unused when IPC active
- **WHEN** the IPC API is active and netlist export is requested
- **THEN** the `kicad_cli` tool path SHALL NOT be consulted for export
- **THEN** `kicad-cli` SHALL only be invoked if IPC export fails

---

## ADDED Requirements

### Requirement: IPC connection lifecycle

The `KiCadBridge` class SHALL manage an IPC API connection via the `_ensure_ipc()` method.

`_ensure_ipc()` SHALL:
- Lazily import `kipy` on first call
- Connect to the KiCad IPC API socket if not already connected
- Cache the `kipy.KiCad` instance for the session lifetime
- Return `True` if connected, `False` if connection failed
- Reconnect automatically if the previous connection was dropped

The bridge SHALL call `_ensure_ipc()` before any IPC-dependent operation (export, Sim.Pins extraction, cross-probe).

#### Scenario: First IPC call connects
- **WHEN** the first IPC-dependent operation is invoked
- **THEN** `_ensure_ipc()` SHALL import `kipy` and establish a connection
- **THEN** the `kipy.KiCad` instance SHALL be cached

#### Scenario: Subsequent calls reuse connection
- **WHEN** a second IPC-dependent operation is invoked
- **THEN** `_ensure_ipc()` SHALL return the cached connection without re-importing or re-connecting

#### Scenario: Connection lost, auto-reconnect
- **WHEN** the cached IPC connection is dropped (KiCad closed and reopened)
- **THEN** the next `_ensure_ipc()` call SHALL detect the broken connection and re-establish it

### Requirement: kicad-python functionality guard

The system SHALL verify that the installed `kicad-python` library exposes the required APIs by checking for the presence of specific methods (`hasattr`), NOT by comparing version numbers.

The check SHALL verify at minimum:
- `hasattr(kipy.KiCad, 'get_schematic')` — schematic document access
- After obtaining a schematic handle: `hasattr(schematic, 'export_netlist')` — SPICE netlist export
- After obtaining a schematic handle: `hasattr(schematic, 'get_symbols')` — symbol/pin querying

If any required method is absent, `RuntimeError` SHALL be raised with a message listing which APIs are missing and recommending: `pip install git+https://gitlab.com/kicad/code/kicad-python.git`.

The check SHALL NOT reference version numbers in its logic or error messages.

#### Scenario: All required APIs present
- **WHEN** `import kipy` succeeds and all `hasattr` checks pass
- **THEN** the functionality check SHALL pass silently
- **THEN** IPC API operations SHALL proceed

#### Scenario: Required APIs absent
- **WHEN** `hasattr(kipy.KiCad, 'get_schematic')` returns `False`
- **THEN** `RuntimeError` SHALL be raised listing "get_schematic" as missing
- **THEN** the message SHALL NOT mention a version number
- **THEN** the message SHALL recommend installing from Git
