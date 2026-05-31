# xschem-bridge Specification

## Purpose
Defines the xschem-specific bridge implementation: netlist export via `xschem -n -s -q --quit`, bidirectional cross-probe via companion Tcl TCP server (ABC protocol → xschem Tcl API translation), wave push via GAW-compatible receiver (preserving Alt+G workflow), file watching, simulation pipeline, and session API.

## ADDED Requirements

### Requirement: Xschem netlist export

The system SHALL export SPICE netlists from `.sch` files by invoking `xschem -n -s -q --quit --netlist_type spice`.

The `XschemBridge` class in `pqwave/bridge/xschem/bridge.py` SHALL:
- Locate `xschem` via `shutil.which()` with optional override from `ApplicationState.tool_paths["xschem"]`
- Raise `FileNotFoundError` with a user-friendly message if `xschem` is not found
- Run `xschem` via `subprocess.run()` with `capture_output=True, text=True`
- Set the working directory to the schematic file's parent directory
- Read the resulting `.spice` file from `netlist_dir` (default `~/.xschem/simulations/<basename>.spice`) and return its text
- Return an empty list from `get_netlist_fixes()` (xschem SPICE output requires no post-processing)

#### Scenario: Successful export

- **WHEN** `export_netlist("/path/to/circuit.sch")` is called and `xschem` is in PATH
- **THEN** `xschem -n -s -q --quit --netlist_type spice circuit.sch` SHALL be invoked with `cwd` set to the schematic's directory
- **THEN** the netlist text SHALL be read from the output `.spice` file and returned

#### Scenario: xschem not found

- **WHEN** `export_netlist()` is called but `xschem` is not in PATH and no override is configured
- **THEN** `FileNotFoundError` SHALL be raised with message indicating how to install or configure the path

#### Scenario: Invalid schematic file

- **WHEN** `export_netlist()` is called with a path to a non-existent `.sch` file
- **THEN** `RuntimeError` SHALL be raised with the xschem error output

#### Scenario: No netlist fixes needed

- **WHEN** `get_netlist_fixes()` is called
- **THEN** an empty list SHALL be returned (xschem SPICE output is clean)

---

### Requirement: Xschem simulation pipeline

The system SHALL provide a `simulate(sch_path, raw_output=None) -> dict` method on `XschemBridge` that runs the full pipeline: export netlist, run ngspice, and load the result.

The pipeline SHALL:
- Export the netlist from the schematic file
- Apply `NetlistPostProcessor` with the fixes from `get_netlist_fixes()` (currently no-op)
- Write the netlist to a temporary `.cir` file
- Run `ngspice -b -r <output.raw> <circuit.cir>` via `subprocess.run()`
- Return a dict with keys: `returncode`, `stdout`, `stderr`, `raw_file`, `netlist`

#### Scenario: Successful simulation

- **WHEN** `simulate()` is called with a valid `.sch` file and `ngspice` is in PATH
- **THEN** the pipeline SHALL complete and return `returncode=0`
- **THEN** the `.raw` file SHALL exist at the specified output path
- **THEN** the netlist text SHALL be returned in the result dict

#### Scenario: ngspice simulation error

- **WHEN** ngspice exits with a non-zero code (e.g., convergence failure)
- **THEN** `returncode` SHALL reflect the exit code
- **THEN** `stderr` SHALL contain the ngspice error output
- **THEN** no exception SHALL be raised (simulation failures are reported, not thrown)

---

### Requirement: Xschem file watching

The system SHALL watch `.sch` files for changes using mtime+size polling via `QTimer` at 1-second intervals.

The `XschemFileWatcher` class in `pqwave/bridge/xschem/file_watcher.py` SHALL:
- Emit a `file_changed(str)` signal when the watched file is modified
- Support `watch(path)` to start watching and `unwatch()` to stop
- Initialize with no file watched

#### Scenario: File saved triggers signal

- **WHEN** the user saves the watched `.sch` file in xschem
- **THEN** `file_changed` SHALL be emitted with the file path after the mtime+size change is detected
- **THEN** the auto-simulation pipeline SHALL be triggered if `auto_simulate` is enabled

#### Scenario: Stop watching

- **WHEN** `unwatch()` is called
- **THEN** subsequent file saves SHALL NOT trigger `file_changed`
- **THEN** the control bar SHALL update to show "not watching"

---

### Requirement: Cross-probe via companion Tcl TCP server

The system SHALL deploy and communicate with a companion Tcl TCP server running inside xschem for net and component highlighting.

The `XschemCrossProbeClient` class in `pqwave/bridge/xschem/cross_probe.py` SHALL:
- Connect to `localhost:<port>` (default 2021, configurable)
- Send plain-text commands: `$NET: "name"`, `$PART: "ref"`, `$CLEAR`
- Emit `connected()`, `disconnected()`, and `error_occurred(str)` Qt signals
- Support a connection timeout (default 2 seconds)
- Handle connection failures gracefully (emit `error_occurred`, do not crash)

The companion Tcl script `pqwave-server.tcl` SHALL:
- Be deployed to `~/.config/xschem/pqwave-server.tcl` and loaded via the user `xschemrc` (`~/.xschem/xschemrc`) by adding it to the `tcl_files` list
- Start a TCP server listening on the configured port when xschem starts
- Handle `$NET: "name"` by calling `probe_net <name>` to navigate hierarchy and highlight the net
- Handle `$PART: "ref"` by calling `select_inst <ref>` to navigate hierarchy and select/zoom to the component
- Handle `$CLEAR` by calling `xschem unhilight_all` to clear all highlights
- Log connection and error information to stderr
- Keep connections open for multiple commands (persistent connection model, unlike xschem's built-in `xschem_server` which closes after each command)

#### Scenario: Highlight a net

- **WHEN** `probe_net("Vout")` is called and xschem is running with the companion server active
- **THEN** the string `$NET: "Vout"\n` SHALL be sent over the TCP socket
- **THEN** xschem SHALL highlight the net named "Vout" and center the view

#### Scenario: Highlight a hierarchical net

- **WHEN** `probe_net("x1.xamp.Vout")` is called
- **THEN** `$NET: "x1.xamp.Vout"\n` SHALL be sent
- **THEN** the companion script SHALL call `probe_net x1.xamp.Vout` to descend hierarchy and highlight the net

#### Scenario: Highlight a component

- **WHEN** `probe_part("Q1")` is called
- **THEN** `$PART: "Q1"\n` SHALL be sent
- **THEN** xschem SHALL select, highlight, and center on Q1

#### Scenario: xschem not running

- **WHEN** any probe command is called but no connection exists on the configured port
- **THEN** `error_occurred` SHALL be emitted with "xschem not running or pqwave server not active"
- **THEN** no exception SHALL be raised

#### Scenario: Clear highlights

- **WHEN** `clear()` is called
- **THEN** `$CLEAR\n` SHALL be sent
- **THEN** all highlights SHALL be cleared in xschem

#### Scenario: Companion script auto-deployment

- **WHEN** `XschemCrossProbeClient` is first instantiated and `~/.config/xschem/pqwave-server.tcl` does not exist
- **THEN** the system SHALL copy the bundled Tcl script to the config directory
- **THEN** a message SHALL be logged instructing the user to add `lappend tcl_files ~/.config/xschem/pqwave-server.tcl` to their `xschemrc` and restart xschem

#### Scenario: Port conflict prevention

- **WHEN** the user attempts to set the xschem cross-probe port to a value already used by KiCad (4243), Lepton (9424), or the xschem wave receiver (2026)
- **THEN** the system SHALL display a warning listing the conflicting ports

---

### Requirement: Wave push via GAW-compatible receiver

The system SHALL preserve the existing xschem Alt+G "Send selected net/pins to Viewer" workflow by running a GAW-compatible TCP server that receives `table_set` and `copyvar` commands from xschem.

The `WaveReceiver` class in `pqwave/bridge/xschem/wave_receiver.py` SHALL:
- Listen on `localhost:<port>` (default 2026, configurable via `--xschem-port`)
- Accept connections from xschem's `gaw_fd` client
- Echo back each received line (GAW handshake protocol)
- Parse `table_set <raw_file>` commands to load `.raw` files
- Parse `copyvar v(<node>) sel #<color>` commands to add waveform traces
- Support JSON-extended commands: `open_file`, `add_trace`, `remove_trace`, `get_data_point`, `close_window`, `list_windows`, `ping`
- Emit Qt signals for the bridge to relay to `MainWindow`
- Support multi-window routing via `WindowRegistry` (mapping client addresses to window IDs)

#### Scenario: Alt+G sends selected net to pqwave

- **WHEN** user selects a net in xschem and presses Alt+G (or clicks Highlight > Send selected net/pins to Viewer)
- **THEN** xschem SHALL connect to pqwave on port 2026
- **THEN** xschem SHALL send `table_set <basename>.raw` followed by `copyvar v(<node>) sel #<color>`
- **THEN** pqwave SHALL load the `.raw` file (if not already loaded) and add the trace with the specified color

#### Scenario: Wave push with JSON commands

- **WHEN** xschem sends `json {"command": "add_trace", "args": {"var_name": "v(out)", "color": "#00ff00"}}`
- **THEN** pqwave SHALL parse the JSON and add the trace
- **THEN** a success response SHALL be sent

#### Scenario: Wave receiver starts before xschem

- **WHEN** pqwave starts with `--xschem-port 2026` (or default)
- **THEN** the GAW-compatible server SHALL listen on port 2026
- **THEN** xschem can connect at any later time (no startup ordering requirement)

#### Scenario: Wave receiver disabled

- **WHEN** pqwave starts with `--no-xschem-server` or `--xschem-port 0`
- **THEN** the GAW-compatible server SHALL NOT start
- **THEN** Alt+G in xschem SHALL fail with a connection error (handled by xschem's existing error dialog)

---

### Requirement: Xschem control bar

The system SHALL provide a `XschemControlBar` widget in `pqwave/bridge/xschem/control_bar.py` for displaying bridge status and providing manual controls.

The control bar SHALL:
- Display a status label showing the current watched file or "not watching"
- Include a "Simulate Now" button that emits `simulate_clicked()`
- Include a "Stop Watching" button that emits `unwatch_clicked()`
- Be lazily created (hidden until the user starts watching a file)
- Follow the same layout pattern as `MCControlBar`, `KiCadControlBar`, and `LeptonControlBar` (horizontal layout, 40px max height)
- Disable the "Simulate Now" button while a simulation is in progress

#### Scenario: Watching a file

- **WHEN** the user starts watching a `.sch` file
- **THEN** the control bar SHALL appear with status "Xschem: watching <filename>"
- **THEN** "Simulate Now" and "Stop Watching" buttons SHALL be enabled

#### Scenario: Simulation in progress

- **WHEN** a simulation pipeline is running
- **THEN** the "Simulate Now" button SHALL be disabled
- **THEN** the status SHALL show "Xschem: simulating..."

#### Scenario: After successful simulation

- **WHEN** simulation completes successfully
- **THEN** the status SHALL show "Xschem: simulation complete"
- **THEN** the "Simulate Now" button SHALL re-enable

---

### Requirement: Session API for xschem bridge

The system SHALL register the following `@api_command` functions in `pqwave/session/api.py`:

| Command | Signature | Description |
|---------|-----------|-------------|
| `xschem_watch` | `xschem_watch(path)` | Start watching a `.sch` file |
| `xschem_unwatch` | `xschem_unwatch()` | Stop watching |
| `xschem_simulate` | `xschem_simulate()` | Trigger full pipeline manually |
| `xschem_probe_net` | `xschem_probe_net(name)` | Highlight a net in xschem |
| `xschem_probe_part` | `xschem_probe_part(ref, pin=None)` | Highlight a component or pin |
| `xschem_clear` | `xschem_clear()` | Clear all xschem highlights |
| `xschem_config` | `xschem_config(key, value=None)` | Get or set bridge configuration |

Each command SHALL follow the existing `SessionAPI` mutation callback pattern: if `_on_mutation` is set (GUI mode), emit the mutation event and return early; otherwise execute directly (headless mode).

#### Scenario: API usage in headless mode

- **WHEN** `api.xschem_watch("circuit.sch")` is called in headless mode
- **THEN** the file watcher SHALL start
- **THEN** `api.xschem_simulate()` SHALL run the pipeline and load results

#### Scenario: API usage in GUI mode

- **WHEN** `api.xschem_simulate()` is called via the REPL in GUI mode
- **THEN** the mutation SHALL be emitted and the MainWindow SHALL handle the actual pipeline execution

#### Scenario: API for cross-probe

- **WHEN** `api.xschem_probe_net("Vout")` is called
- **THEN** the bridge SHALL connect to xschem's companion Tcl server and send `$NET: "Vout"`
- **WHEN** `api.xschem_clear()` is called
- **THEN** the bridge SHALL send `$CLEAR`

---

### Requirement: Tool path configuration

The system SHALL allow users to configure `xschem` and `ngspice` paths via the Settings dialog and the `xschem_config` API.

The paths SHALL be stored in `ApplicationState.tool_paths` with keys `"xschem"` and `"ngspice"`.
The paths SHALL be persisted to `~/.pqwave/prefs.json` alongside existing tool paths.
The Settings dialog SHALL include input fields for both paths in the "External Converter Paths" group.

#### Scenario: Custom xschem path

- **WHEN** the user sets `tool_paths["xschem"]` to `/opt/local/bin/xschem`
- **THEN** `shutil.which("xschem")` SHALL NOT be used
- **THEN** the specified path SHALL be invoked for netlist export

#### Scenario: Default PATH detection

- **WHEN** no custom path is configured
- **THEN** `shutil.which("xschem")` and `shutil.which("ngspice")` SHALL be used

---

### Requirement: Menu integration

The system SHALL add an "Xschem Bridge" submenu to the File menu with the following actions:
- **Watch Schematic...** — opens file dialog to select a `.sch` file and starts watching
- **Simulate Now** — manually triggers simulation of the currently watched file
- **Stop Watching** — stops the file watcher and hides the control bar
- **Cross-Probe** submenu with **Probe Selected Net** and **Clear Highlight**

Menu actions SHALL be disabled when no bridge is active (no file being watched).

#### Scenario: No file watched

- **WHEN** no `.sch` file is being watched
- **THEN** "Simulate Now", "Stop Watching", and "Cross-Probe" actions SHALL be disabled
- **THEN** "Watch Schematic..." SHALL remain enabled

---

### Requirement: Wave receiver cursor-driven back-annotation

The system SHALL support cursor-driven back-annotation from pqwave to xschem using the cross-probe channel (port 2021), debounced at 250ms.

#### Scenario: Cursor A placed on trace

- **WHEN** the user places cursor A on a waveform trace originating from xschem
- **THEN** the system SHALL send a `$NET` cross-probe command for the trace's source net with a debounce delay of 250ms
- **THEN** xschem SHALL highlight the corresponding net
- **THEN** the cursor's X and Y values SHALL be displayed in pqwave's status bar alongside the net name

#### Scenario: Cursor-driven update

- **WHEN** the user moves the cursor along the trace
- **THEN** the highlighted net SHALL update (debounced) to follow the cursor position
