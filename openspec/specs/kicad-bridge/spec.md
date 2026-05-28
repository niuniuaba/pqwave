# kicad-bridge Specification

## Purpose
Defines the KiCad-specific bridge implementation: netlist export via kicad-cli, four netlist post-processing fixes (slash stripping, diode/BJT pin reordering, control block relocation), file watching, cross-probe via TCP, and simulation pipeline.
## Requirements
### Requirement: KiCad netlist export

The system SHALL export SPICE netlists from `.kicad_sch` files by invoking `kicad-cli sch export netlist --format spice`.

The `KiCadBridge` class in `pqwave/bridge/kicad/bridge.py` SHALL:
- Locate `kicad-cli` via `shutil.which()` with optional override from `ApplicationState.tool_paths["kicad_cli"]`
- Raise `FileNotFoundError` with a user-friendly message if `kicad-cli` is not found
- Run `kicad-cli` via `subprocess.run()` with `capture_output=True, text=True`
- Raise `RuntimeError` with the stderr output if the process returns non-zero
- Return the netlist text as a string

#### Scenario: Successful export
- **WHEN** `export_netlist("/path/to/circuit.kicad_sch")` is called and `kicad-cli` is in PATH
- **THEN** `kicad-cli sch export netlist --format spice` SHALL be invoked with a temporary output file
- **THEN** the netlist text SHALL be returned

#### Scenario: kicad-cli not found
- **WHEN** `export_netlist()` is called but `kicad-cli` is not in PATH and no override is configured
- **THEN** `FileNotFoundError` SHALL be raised with message indicating how to install or configure the path

#### Scenario: Invalid schematic file
- **WHEN** `export_netlist()` is called with a path to a non-existent or invalid `.kicad_sch` file
- **THEN** `RuntimeError` SHALL be raised with the kicad-cli error output

---

### Requirement: KiCad simulation pipeline

The system SHALL provide a `simulate(sch_path, raw_output=None) -> dict` method on `KiCadBridge` that runs the full pipeline: export netlist, post-process, run ngspice, and load the result.

The pipeline SHALL:
- Export the netlist from the schematic file
- Apply all configured `NetlistFix` instances via `NetlistPostProcessor`
- Write the fixed netlist to a temporary `.cir` file
- Run `ngspice -b -r <output.raw> <circuit.cir>` via `subprocess.run()`
- Return a dict with keys: `returncode`, `stdout`, `stderr`, `raw_file`, `netlist`

Optional `context` SHALL be passed to `NetlistPostProcessor.process()` containing `Sim.Pins` data extracted from the `.kicad_sch` file.

#### Scenario: Successful simulation
- **WHEN** `simulate()` is called with a valid `.kicad_sch` and `ngspice` is in PATH
- **THEN** the pipeline SHALL complete and return `returncode=0`
- **THEN** the `.raw` file SHALL exist at the specified output path
- **THEN** the fixed netlist text SHALL be returned in the result dict

#### Scenario: ngspice simulation error
- **WHEN** ngspice exits with a non-zero code (e.g., convergence failure)
- **THEN** `returncode` SHALL reflect the exit code
- **THEN** `stderr` SHALL contain the ngspice error output
- **THEN** no exception SHALL be raised (simulation failures are reported, not thrown)

---

### Requirement: KiCad file watching

The system SHALL watch `.kicad_sch` files for changes using `QFileSystemWatcher`.

The `KiCadFileWatcher` class in `pqwave/bridge/kicad/file_watcher.py` SHALL:
- Emit a `file_changed(str)` signal when the watched file is modified
- Handle KiCad's atomic save pattern (delete-then-rename) by re-adding the file path after a brief delay
- Support `watch(path)` to start watching and `unwatch()` to stop
- Initialize with no file watched (user must explicitly call `watch`)

#### Scenario: File saved triggers signal
- **WHEN** the user saves the watched `.kicad_sch` file in KiCad
- **THEN** `file_changed` SHALL be emitted with the file path
- **THEN** the auto-simulation pipeline SHALL be triggered if `auto_simulate` is enabled

#### Scenario: Atomic save handling
- **WHEN** KiCad saves by deleting the file and renaming a temp file in its place
- **THEN** the watcher SHALL detect the file removal and re-add the path after 200ms
- **THEN** the save SHALL still trigger `file_changed`

#### Scenario: Stop watching
- **WHEN** `unwatch()` is called
- **THEN** subsequent file saves SHALL NOT trigger `file_changed`
- **THEN** the control bar SHALL update to show "not watching"

---

### Requirement: Cross-probe back-annotation to KiCad

The system SHALL provide a TCP client that connects to KiCad's built-in cross-probe server on `localhost:4243`.

The `CrossProbeClient` class in `pqwave/bridge/kicad/cross_probe.py` SHALL:
- Connect to `localhost:<port>` (default 4243, configurable)
- Send plain-text commands: `$NET: "name"`, `$PART: "ref"`, `$PART: "ref" $PAD: "pin"`, `$CLEAR`
- Emit `connected()`, `disconnected()`, and `error_occurred(str)` Qt signals
- Support a connection timeout (default 2 seconds)
- Handle the case where KiCad is not running gracefully (emit `error_occurred`, do not crash)

#### Scenario: Highlight a net
- **WHEN** `probe_net("R1")` is called and KiCad is running
- **THEN** the string `$NET: "R1"\n` SHALL be sent over the TCP socket
- **THEN** KiCad SHALL highlight the R1 net on the schematic

#### Scenario: Highlight a component
- **WHEN** `probe_part("Q1")` is called
- **THEN** `$PART: "Q1"\n` SHALL be sent
- **THEN** KiCad SHALL highlight and center on Q1

#### Scenario: KiCad not running
- **WHEN** any probe command is called but no connection to port 4243 exists
- **THEN** `error_occurred` SHALL be emitted with "KiCad not running or cross-probe server not active"
- **THEN** no exception SHALL be raised

#### Scenario: Clear highlights
- **WHEN** `clear()` is called
- **THEN** `$CLEAR\n` SHALL be sent

#### Scenario: Cursor-driven back-annotation
- **WHEN** the user places cursor A on a waveform trace at position X
- **THEN** the system SHALL send a cross-probe command for the trace's source net with a debounce delay of 250ms
- **THEN** KiCad SHALL highlight the corresponding net
- **WHEN** the user moves the cursor along the trace
- **THEN** the highlighted net SHALL update (debounced) to follow the cursor position
- **THEN** the cursor's X and Y values SHALL be displayed in pqwave's status bar alongside the net name

#### Scenario: Port conflict prevention
- **WHEN** the user attempts to set the xschem server port to 4243 (KiCad's default cross-probe port)
- **THEN** the system SHALL display a warning that port 4243 is reserved for KiCad cross-probe
- **THEN** the xschem server SHALL NOT bind to that port
- **WHEN** the user sets `--kicad-port` to the same value as `--xschem-port`
- **THEN** the system SHALL display an error and exit with a message listing both conflicting port numbers

---

### Requirement: KiCad control bar

The system SHALL provide a `KiCadControlBar` widget in `pqwave/bridge/kicad/control_bar.py` for displaying bridge status and providing manual controls.

The control bar SHALL:
- Display a status label showing the current watched file or "not watching"
- Include a "Simulate Now" button that emits `simulate_clicked()`
- Include a "Stop Watching" button that emits `unwatch_clicked()`
- Be lazily created (hidden until the user starts watching a file)
- Follow the same layout pattern as `MCControlBar` (horizontal layout, 40px max height)
- Disable the "Simulate Now" button while a simulation is in progress

#### Scenario: Watching a file
- **WHEN** the user starts watching a `.kicad_sch` file
- **THEN** the control bar SHALL appear with status "KiCad: watching <filename>"
- **THEN** "Simulate Now" and "Stop Watching" buttons SHALL be enabled

#### Scenario: Simulation in progress
- **WHEN** a simulation pipeline is running
- **THEN** the "Simulate Now" button SHALL be disabled
- **THEN** the status SHALL show "KiCad: simulating..."

---

### Requirement: Session API for KiCad bridge

The system SHALL register the following `@api_command` functions in `pqwave/session/api.py`:

| Command | Signature | Description |
|---------|-----------|-------------|
| `kicad_watch` | `kicad_watch(path)` | Start watching a `.kicad_sch` file |
| `kicad_unwatch` | `kicad_unwatch()` | Stop watching |
| `kicad_simulate` | `kicad_simulate()` | Trigger full pipeline manually |
| `kicad_probe_net` | `kicad_probe_net(name)` | Highlight a net in KiCad |
| `kicad_probe_part` | `kicad_probe_part(ref, pin=None)` | Highlight a component or pin |
| `kicad_clear` | `kicad_clear()` | Clear all KiCad highlights |
| `kicad_config` | `kicad_config(key, value=None)` | Get or set bridge configuration |

Each command SHALL follow the existing `SessionAPI` mutation callback pattern: if `_on_mutation` is set (GUI mode), emit the mutation event and return early; otherwise execute directly (headless mode).

#### Scenario: API usage in headless mode
- **WHEN** `api.kicad_watch("circuit.kicad_sch")` is called in headless mode
- **THEN** the file watcher SHALL start
- **THEN** `api.kicad_simulate()` SHALL run the pipeline and load results

#### Scenario: API usage in GUI mode
- **WHEN** `api.kicad_simulate()` is called via the REPL in GUI mode
- **THEN** the mutation SHALL be emitted and the MainWindow SHALL handle the actual pipeline execution

---

### Requirement: Tool path configuration

The system SHALL allow users to configure `kicad-cli` and `ngspice` paths via the Settings dialog and the `kicad_config` API.

The paths SHALL be stored in `ApplicationState.tool_paths` with keys `"kicad_cli"` and `"ngspice"`.
The paths SHALL be persisted to `~/.pqwave/prefs.json` alongside existing tool paths.
The Settings dialog SHALL include input fields for both paths in the "External Converter Paths" group.

#### Scenario: Custom ngspice path
- **WHEN** the user sets `tool_paths["ngspice"]` to `/opt/local/bin/ngspice`
- **THEN** `shutil.which("ngspice")` SHALL NOT be used
- **THEN** the specified path SHALL be invoked for simulation

#### Scenario: Default PATH detection
- **WHEN** no custom path is configured
- **THEN** `shutil.which("kicad-cli")` and `shutil.which("ngspice")` SHALL be used

---

### Requirement: Menu integration

The system SHALL add a "KiCad Bridge" submenu to the File menu with the following actions:
- **Watch Schematic...** — opens file dialog to select a `.kicad_sch` file and starts watching
- **Simulate Now** — manually triggers simulation of the currently watched file
- **Stop Watching** — stops the file watcher and hides the control bar
- **Cross-Probe** submenu with **Probe Selected Net** and **Clear Highlight**

Menu actions SHALL be disabled when no bridge is active (no file being watched).

#### Scenario: No file watched
- **WHEN** no `.kicad_sch` file is being watched
- **THEN** "Simulate Now", "Stop Watching", and "Cross-Probe" actions SHALL be disabled
- **THEN** "Watch Schematic..." SHALL remain enabled

