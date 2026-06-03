# kicad-ipc-api Specification

## Purpose
Defines the IPC API connection layer for KiCad integration: socket discovery, connection lifecycle, version negotiation, netlist export, schematic data querying, and cross-probe back-annotation — all via the KiCad IPC API with `kicad-cli` as a fallback.

## ADDED Requirements

### Requirement: IPC API dependency detection

The system SHALL detect `kicad-python` at runtime via a lazy import when the user first initiates a KiCad bridge operation. Compatibility SHALL be verified by **functionality checks** (`hasattr`), not by version number comparison.

If `import kipy` fails, the system SHALL raise a `RuntimeError` with a message that:
- States that `kicad-python` is required for KiCad IPC API integration
- Provides the install command: `pip install kicad-python` (or `pip install git+https://gitlab.com/kicad/code/kicad-python.git` for pre-release KiCad versions)
- Links to the kicad-python PyPI page

If `import kipy` succeeds but required APIs are absent, the system SHALL raise a `RuntimeError` listing the missing functionality. The check SHALL verify at minimum:
- `hasattr(kipy.KiCad, 'get_schematic')` — schematic access
- `hasattr(schematic, 'export_netlist')` — SPICE netlist export
- `hasattr(schematic, 'get_symbols')` — symbol/pin querying

The error message SHALL state which specific APIs are missing and recommend installing from Git: `pip install git+https://gitlab.com/kicad/code/kicad-python.git`.

#### Scenario: kicad-python not installed
- **WHEN** the user attempts to watch a `.kicad_sch` file and `import kipy` raises `ImportError`
- **THEN** `RuntimeError` SHALL be raised with a message containing "pip install kicad-python"
- **THEN** the error SHALL be displayed to the user in the control bar status and log

#### Scenario: kicad-python installed with all required APIs
- **WHEN** `import kipy` succeeds and all `hasattr` checks pass
- **THEN** the import SHALL succeed silently
- **THEN** the IPC connection SHALL be attempted

#### Scenario: kicad-python installed but missing required APIs
- **WHEN** `import kipy` succeeds but `hasattr(kipy.KiCad, 'get_schematic')` is `False`
- **THEN** `RuntimeError` SHALL be raised listing "get_schematic" as missing
- **THEN** the message SHALL recommend: `pip install git+https://gitlab.com/kicad/code/kicad-python.git`

---

### Requirement: IPC socket connection

The system SHALL connect to KiCad's IPC API via a Unix domain socket (`api.sock`) on Linux/macOS or a named pipe on Windows.

The connection SHALL:
- Read `KICAD_API_SOCKET` from the environment (set by KiCad when launching plugins)
- Fall back to the platform-specific default path: `<tmpdir>/kicad/api.sock`
- Use the `ipc://` URL scheme prefix required by the NNG transport layer
- Set a configurable timeout (default 5000ms) for all API calls
- Be established lazily on first use, not at bridge construction time

#### Scenario: KiCad is running with API enabled
- **WHEN** `_ensure_ipc()` is called and KiCad is running with the IPC API server enabled
- **THEN** a `kipy.KiCad` connection SHALL be established within the timeout
- **THEN** subsequent IPC calls SHALL reuse the same connection

#### Scenario: KiCad not running
- **WHEN** `_ensure_ipc()` is called but no KiCad instance has an open API socket
- **THEN** a `ConnectionError` SHALL be raised
- **THEN** the bridge SHALL fall back to the `kicad-cli` subprocess path for netlist export

#### Scenario: Connection drops mid-session
- **WHEN** the KiCad process terminates while pqwave holds an open IPC connection
- **THEN** the next IPC call SHALL raise `ConnectionError`
- **THEN** `_ensure_ipc()` SHALL attempt a fresh connection on the next bridge operation

---

### Requirement: SPICE netlist export via IPC

The system SHALL export SPICE netlists from `.kicad_sch` files by calling `schematic.export_netlist(format=SNF_SPICE)` via the IPC API when connected.

When the IPC API is available, the export SHALL:
- Call `schematic.export_netlist(output_path, format=schematic_jobs_pb2.SNF_SPICE)` via the `kipy` library
- Write the netlist to a temporary file
- Return the netlist text as a string

When the IPC API is NOT available (KiCad < 10, API disabled, or connection failed), the export SHALL fall back to the existing `kicad-cli sch export netlist --format spice` subprocess method.

#### Scenario: IPC export succeeds
- **WHEN** `export_netlist()` is called and the IPC API connection is active
- **THEN** `schematic.export_netlist(format=SNF_SPICE)` SHALL be invoked
- **THEN** the resulting netlist file SHALL be read and its text returned
- **THEN** NO subprocess SHALL be spawned

#### Scenario: IPC unavailable, fallback to kicad-cli
- **WHEN** `export_netlist()` is called but the IPC API connection failed or `kicad-python` is not installed
- **THEN** `kicad-cli sch export netlist --format spice` SHALL be invoked via `subprocess.run()`
- **THEN** the netlist text SHALL be returned

---

### Requirement: Sim.Pins extraction via IPC

The system SHALL extract `Sim.Pins` data from the schematic by calling `schematic.get_symbols()` via the IPC API, replacing the current regex-based `.kicad_sch` file parsing.

When the IPC API is available, the extraction SHALL:
- Call `schematic.get_symbols()` to retrieve all `SchematicSymbolInstance` objects
- For each symbol, access `definition.items` to find `SchematicPin` objects
- Build a dict mapping reference designator → `{pin_number: pin_name, ...}`
- Return this dict for use by `FixBJTPins.apply()`

When the IPC API is NOT available, the extraction SHALL fall back to the existing S-expression regex parsing of `.kicad_sch` files.

#### Scenario: IPC Sim.Pins extraction
- **WHEN** `extract_sim_pins()` is called and the IPC API connection is active
- **THEN** `schematic.get_symbols()` SHALL be called
- **THEN** the returned symbols' pin definitions SHALL be traversed
- **THEN** a dict like `{"Q1": {"1": "E", "2": "B", "3": "C"}, ...}` SHALL be returned
- **THEN** NO file I/O on `.kicad_sch` SHALL be performed

#### Scenario: IPC unavailable, fallback to regex
- **WHEN** `extract_sim_pins()` is called but the IPC API connection is not available
- **THEN** the existing regex-based `.kicad_sch` parsing SHALL be used
- **THEN** the `.kicad_sch` file SHALL be read from disk

---

### Requirement: Cross-probe via IPC RunAction

The system SHALL highlight nets and components in KiCad Eeschema by calling `kicad.run_action()` with the appropriate editor action names.

For net probing, the system SHALL:
- Resolve the net name to a schematic item (via `get_netlist()` or by selecting items matching the net)
- Call `run_action()` to select and highlight the item
- If `run_action` proves unreliable, fall back to `AddToSelection`/`ClearSelection` IPC commands with KIID resolution

For part probing, the system SHALL:
- Resolve the reference designator to a schematic symbol KIID
- Call `run_action()` or `AddToSelection` to select and center on the symbol

For clearing, the system SHALL call `ClearSelection` or the equivalent `run_action`.

#### Scenario: Probe a net by name
- **WHEN** `probe_net("R1")` is called and the IPC API connection is active
- **THEN** the net SHALL be highlighted in the KiCad schematic editor
- **THEN** a success/failure status SHALL be returned

#### Scenario: Probe a component by reference
- **WHEN** `probe_part("Q1")` is called
- **THEN** the component Q1 SHALL be highlighted and centered in the KiCad schematic editor

#### Scenario: Clear highlights
- **WHEN** `clear_probe()` is called
- **THEN** all cross-probe highlights in the KiCad schematic SHALL be cleared

#### Scenario: IPC unavailable
- **WHEN** any probe command is called but the IPC API connection is not available
- **THEN** the probe SHALL fail silently (log a warning, do not crash)
- **THEN** the user SHALL see a status message: "Cross-probe unavailable — requires KiCad 10+ with IPC API enabled"

---

### Requirement: Content-aware StripSlashes fix

The system SHALL apply the `StripSlashes` netlist fix only when the exported netlist actually contains leading slashes on net names. Detection SHALL be based on the netlist content, not the KiCad version.

Before applying `StripSlashes`, the post-processor SHALL inspect the exported netlist for lines matching the pattern of a leading slash before a net name (e.g., `D1 /net_name /other_net`). If no such lines are found, `StripSlashes` SHALL be skipped.

When leading slashes are detected:
- `StripSlashes` SHALL be applied as the first fix in the pipeline
- A log message SHALL indicate: "Detected leading slashes in netlist: applying slash-stripping fix"

When no leading slashes are detected:
- `StripSlashes` SHALL be skipped
- A log message SHALL indicate: "No leading slashes detected in netlist: skipping slash-stripping fix"
- `FixDiodePins`, `FixBJTPins`, and `MoveControlBlock` SHALL still be applied

#### Scenario: Netlist has leading slashes (KiCad 9), fix applied
- **WHEN** the exported netlist contains lines like `D1 /AC_P /GND D1N4148`
- **THEN** `StripSlashes` SHALL be applied as the first fix
- **THEN** the log SHALL indicate "Detected leading slashes in netlist"

#### Scenario: Netlist has no leading slashes (KiCad 10.99+), fix skipped
- **WHEN** the exported netlist contains no `/word` patterns at node positions
- **THEN** `StripSlashes` SHALL NOT be applied
- **THEN** `FixDiodePins`, `FixBJTPins`, and `MoveControlBlock` SHALL still be applied

---

### Requirement: Connection status indicator

The system SHALL display the IPC API connection status in the `KiCadControlBar`.

The status label SHALL show one of:
- "KiCad: disconnected (IPC API not available)" — when kicad-python missing or connection failed
- "KiCad: connected via IPC API" — when IPC connection is active
- "KiCad: watching <filename> (kicad-cli fallback)" — when using subprocess fallback

#### Scenario: IPC connected
- **WHEN** the IPC API connection is successfully established
- **THEN** the control bar SHALL show "KiCad: connected via IPC API — watching <filename>"

#### Scenario: Fallback active
- **WHEN** the IPC API connection fails and kicad-cli fallback is in use
- **THEN** the control bar SHALL show "KiCad: watching <filename> (kicad-cli fallback)"
