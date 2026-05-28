# lepton-bridge Specification

## Purpose
Defines the Lepton-EDA-specific bridge implementation: netlist export via lepton-netlist (spice-sdb backend, zero fixes), bidirectional cross-probe via Scheme TCP server (select-object! + select-objects-hook), back-annotation (DC stamps, floating labels, annotation clearing), in-schematic menus (Netlist > SPICE, Simulation > ngspice, Wave View > pqwave), file watching, simulation pipeline, and session API.

## ADDED Requirements

### Requirement: Lepton-EDA netlist export

The system SHALL export SPICE netlists from `.sch` files by invoking `lepton-netlist -g spice-sdb`.

The `LeptonBridge` class in `pqwave/bridge/lepton/bridge.py` SHALL:
- Locate `lepton-netlist` via `shutil.which()` with optional override from `ApplicationState.tool_paths["lepton_netlist"]`
- Raise `FileNotFoundError` with a user-friendly message if `lepton-netlist` is not found
- Run `lepton-netlist` via `subprocess.run()` with `capture_output=True, text=True`
- Return the netlist text as a string (output to stdout via `-o -`)
- Return an empty list from `get_netlist_fixes()` (lepton-eda SPICE output requires no post-processing)

#### Scenario: Successful export

- **WHEN** `export_netlist("/path/to/circuit.sch")` is called and `lepton-netlist` is in PATH
- **THEN** `lepton-netlist -g spice-sdb -o - circuit.sch` SHALL be invoked
- **THEN** the netlist text SHALL be returned from stdout

#### Scenario: lepton-netlist not found

- **WHEN** `export_netlist()` is called but `lepton-netlist` is not in PATH and no override is configured
- **THEN** `FileNotFoundError` SHALL be raised with message indicating how to install or configure the path

#### Scenario: Invalid schematic file

- **WHEN** `export_netlist()` is called with a path to a non-existent `.sch` file
- **THEN** `RuntimeError` SHALL be raised with the lepton-netlist error output

#### Scenario: No netlist fixes needed

- **WHEN** `get_netlist_fixes()` is called
- **THEN** an empty list SHALL be returned (lepton-eda SPICE output is clean)

---

### Requirement: Lepton-EDA simulation pipeline

The system SHALL provide a `simulate(sch_path, raw_output=None) -> dict` method on `LeptonBridge` that runs the full pipeline: export netlist, run ngspice, and load the result.

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

### Requirement: Lepton-EDA file watching

The system SHALL watch `.sch` files for changes using mtime+size polling via `QTimer` at 1-second intervals.

The `LeptonFileWatcher` class in `pqwave/bridge/lepton/file_watcher.py` SHALL:
- Emit a `file_changed(str)` signal when the watched file is modified
- Support `watch(path)` to start watching and `unwatch()` to stop
- Initialize with no file watched

#### Scenario: File saved triggers signal

- **WHEN** the user saves the watched `.sch` file in lepton-schematic
- **THEN** `file_changed` SHALL be emitted with the file path
- **THEN** the auto-simulation pipeline SHALL be triggered if `auto_simulate` is enabled

#### Scenario: Stop watching

- **WHEN** `unwatch()` is called
- **THEN** subsequent file saves SHALL NOT trigger `file_changed`

---

### Requirement: Cross-probe via Scheme TCP server

The system SHALL deploy and communicate with a Guile Scheme TCP server running inside lepton-schematic for net and component highlighting.

The `LeptonCrossProbeClient` class in `pqwave/bridge/lepton/cross_probe.py` SHALL:
- Connect to `localhost:<port>` (default 9424, configurable)
- Send plain-text commands: `$NET: "name"`, `$PART: "ref"`, `$PART: "ref" $PAD: "pin"`, `$CLEAR`
- Emit `connected()`, `disconnected()`, and `error_occurred(str)` Qt signals
- Support a connection timeout (default 2 seconds)
- Handle connection failures gracefully (emit `error_occurred`, do not crash)

The companion Scheme script `pqwave-server.scm` SHALL:
- Be deployed to `~/.config/lepton-eda/scheme/autoload/pqwave-server.scm`
- Start a TCP server listening on the configured port when lepton-schematic starts
- Use `open-page-hook` to build netname→object and refdes→object maps after page load
- Handle `$NET: "name"` by calling `select-object!` on matching net objects and `schematic_canvas_zoom_object` to center the view
- Handle `$PART: "ref"` by finding the component by refdes and calling `select-object!` + `schematic_canvas_zoom_object`
- Handle `$CLEAR` by deselecting all objects
- Log connection and error information to stderr

#### Scenario: Highlight a net

- **WHEN** `probe_net("Vbase1")` is called and lepton-schematic is running with the server active
- **THEN** the string `$NET: "Vbase1"\n` SHALL be sent over the TCP socket
- **THEN** lepton-schematic SHALL highlight all net segments with `netname=Vbase1`

#### Scenario: Highlight a component

- **WHEN** `probe_part("Q1")` is called
- **THEN** `$PART: "Q1"\n` SHALL be sent
- **THEN** lepton-schematic SHALL highlight and center on Q1

#### Scenario: Lepton-schematic not running

- **WHEN** any probe command is called but no connection exists on the configured port
- **THEN** `error_occurred` SHALL be emitted with "lepton-schematic not running or pqwave server not active"
- **THEN** no exception SHALL be raised

#### Scenario: Clear highlights

- **WHEN** `clear()` is called
- **THEN** `$CLEAR\n` SHALL be sent
- **THEN** all objects SHALL be deselected in lepton-schematic

#### Scenario: Reverse cross-probe — click net in schematic plots trace in pqwave

- **WHEN** the user clicks a net object in lepton-schematic that has a `netname=` attribute
- **THEN** `select-objects-hook` SHALL fire with the selected net object
- **THEN** the Scheme server SHALL extract the netname value and send `$SELECTED:net <netname>` over the TCP connection to pqwave
- **THEN** pqwave SHALL emit a `net_selected(str)` signal containing the net name
- **THEN** pqwave SHALL plot the corresponding waveform trace if it exists in the loaded dataset

#### Scenario: Reverse cross-probe — click component in schematic

- **WHEN** the user clicks a component in lepton-schematic that has a `refdes=` attribute
- **THEN** `select-objects-hook` SHALL fire with the selected component object
- **THEN** the Scheme server SHALL extract the refdes value and send `$SELECTED:part <refdes>` over the TCP connection to pqwave

#### Scenario: No feedback loop from programmatic selection

- **WHEN** pqwave sends `$NET: "Vbase1"` causing the Scheme server to call `select-object!`
- **THEN** `select-objects-hook` SHALL NOT fire (it is only triggered by user click via `o_attrib_add_selected`)
- **THEN** no `$SELECTED` message SHALL be sent back to pqwave

#### Scenario: Scheme server auto-deployment

- **WHEN** `LeptonCrossProbeClient` is first instantiated and `~/.config/lepton-eda/scheme/autoload/pqwave-server.scm` does not exist
- **THEN** the system SHALL copy the bundled Scheme script to the autoload directory
- **THEN** a message SHALL be logged instructing the user to restart lepton-schematic

#### Scenario: Port conflict prevention

- **WHEN** the user attempts to set the lepton cross-probe port to a value already used by xschem (2026/2021) or KiCad (4243)
- **THEN** the system SHALL display a warning listing the conflicting ports

---

### Requirement: Back-annotation of simulation results

The system SHALL support writing simulation data back onto the lepton-schematic canvas using two mechanisms: attribute stamps (persistent) and floating text labels (managed layer).

The Scheme server SHALL handle the following additional commands beyond cross-probe:

| Command | Action |
|---|---|
| `$ANNOTATE:DC <netname> <voltage>` | Append `[DC:<voltage>V]` to the netname attribute of matching net objects |
| `$ANNOTATE:LABEL <netname> <text> <x> <y>` | Create a floating text object at the specified coordinates |
| `$CLEAR:ANNOTATIONS` | Remove all floating text labels created by pqwave (tracked by a unique tag) |
| `$CLEAR:DC` | Restore original netname attribute values (strip `[DC:...V]` suffix) |

The `LeptonBridge` class SHALL provide additional methods:
- `annotate_dc(voltages: dict[str, float]) -> None` — send DC voltage stamps for each netname→voltage pair
- `annotate_label(netname: str, text: str, position: tuple) -> None` — place a floating label
- `clear_annotations() -> None` — remove all floating labels
- `clear_dc_stamps() -> None` — restore original netname values

#### Scenario: DC bias stamp

- **WHEN** `annotate_dc({"Vbase1": 1.82, "Vout": 5.67})` is called
- **THEN** the netname attribute on Vbase1 net objects SHALL be updated to include `[DC:1.82 V]`
- **THEN** the netname attribute on Vout net objects SHALL be updated to include `[DC:5.67 V]`

#### Scenario: Floating voltage label

- **WHEN** `annotate_label("Vbase1", "1.82 V", (30300, 49850))` is called
- **THEN** a text object displaying "1.82 V" SHALL appear near the Vbase1 net segment in lepton-schematic
- **THEN** the text object SHALL be tracked for later bulk removal

#### Scenario: Clear annotations

- **WHEN** `clear_annotations()` is called
- **THEN** all floating text labels created via `$ANNOTATE:LABEL` SHALL be removed from the page
- **THEN** DC stamps SHALL NOT be affected (use `clear_dc_stamps()` for that)

#### Scenario: Cursor-driven back-annotation

- **WHEN** the user places cursor A on a waveform trace at position X
- **THEN** the system SHALL send a `$NET` cross-probe command for the trace's source net with a debounce delay of 250ms
- **THEN** lepton-schematic SHALL highlight the corresponding net
- **THEN** the cursor's X and Y values SHALL be displayed in pqwave's status bar alongside the net name

---

### Requirement: In-schematic menus (Scheme plugin)

The companion Scheme script SHALL add the following menus and actions to lepton-schematic at startup, enabling the user to drive the complete simulation workflow from within the schematic editor.

Three custom actions SHALL be defined via `define-action-public`:

- **`&spice-netlist`**: Exports a SPICE netlist for the current schematic page by running `lepton-netlist -g spice-sdb -o <basename>.cir <filename>`. The output file SHALL be placed in the same directory as the schematic, overwriting any previous netlist. On failure, the error SHALL be logged to the lepton-schematic log window.

- **`&sim-ngspice`**: Runs `ngspice -b -r <basename>.raw <basename>.cir` on the netlist exported by `&spice-netlist`. The `.raw` output SHALL be placed in the same directory as the schematic. On failure, ngspice's stderr SHALL be logged.

- **`&wave-pqwave`**: Launches `pqwave <basename>.raw` via `system*`, opening the simulation results in pqwave. If pqwave is already running with the file being watched, the file watcher SHALL detect the updated `.raw` file and reload automatically.

Three menus SHALL be added via `add-menu`:

- A **"SPICE"** entry appended to the existing **Netlist** menu
- A new **Simulation** menu with an **"ngspice"** entry
- A new **Wave View** menu with a **"pqwave"** entry

#### Scenario: Generate SPICE netlist from menu

- **WHEN** the user clicks Netlist > SPICE in lepton-schematic
- **THEN** `lepton-netlist -g spice-sdb` SHALL be invoked on the current schematic page
- **THEN** a `<basename>.cir` file SHALL be created in the schematic's directory
- **THEN** any previous `.cir` file SHALL be overwritten
- **THEN** success or error SHALL be displayed in the lepton-schematic log window

#### Scenario: Run ngspice simulation from menu

- **WHEN** the user clicks Simulation > ngspice in lepton-schematic
- **THEN** a SPICE netlist SHALL be generated first (equivalent to Netlist > SPICE)
- **THEN** `ngspice -b -r <basename>.raw <basename>.cir` SHALL be invoked
- **THEN** a `<basename>.raw` file SHALL be created in the schematic's directory
- **THEN** if pqwave is watching this file, it SHALL auto-load the new simulation data

#### Scenario: Launch pqwave from menu

- **WHEN** the user clicks Wave View > pqwave in lepton-schematic
- **THEN** `pqwave <basename>.raw` SHALL be launched via `system*`
- **THEN** if pqwave is already running, it SHALL detect the updated file and reload

#### Scenario: Workflow sequence

- **WHEN** the user opens a `.sch` file in lepton-schematic with the pqwave server loaded
- **THEN** Netlist > SPICE, Simulation > ngspice, and Wave View > pqwave SHALL all be present in the menu bar
- **WHEN** the user clicks them in sequence (SPICE → ngspice → pqwave)
- **THEN** a complete simulation-to-viewer workflow SHALL execute without leaving lepton-schematic

---

### Requirement: Lepton-EDA control bar

The system SHALL provide a `LeptonControlBar` widget in `pqwave/bridge/lepton/control_bar.py` for displaying bridge status and providing manual controls.

The control bar SHALL:
- Display a status label showing the current watched file or "not watching"
- Include a "Simulate Now" button that emits `simulate_clicked()`
- Include a "Stop Watching" button that emits `unwatch_clicked()`
- Include an "Annotate DC" button that emits `annotate_dc_clicked()` (enabled only after simulation)
- Include a "Clear Annotations" button that emits `clear_annotations_clicked()`
- Be lazily created (hidden until the user starts watching a file)
- Follow the same layout pattern as `MCControlBar` and `KiCadControlBar` (horizontal layout, 40px max height)
- Disable "Simulate Now" and "Annotate DC" buttons while a simulation is in progress

#### Scenario: Watching a file

- **WHEN** the user starts watching a `.sch` file
- **THEN** the control bar SHALL appear with status "Lepton: watching <filename>"
- **THEN** "Simulate Now" and "Stop Watching" buttons SHALL be enabled

#### Scenario: Simulation in progress

- **WHEN** a simulation pipeline is running
- **THEN** the "Simulate Now" and "Annotate DC" buttons SHALL be disabled
- **THEN** the status SHALL show "Lepton: simulating..."

#### Scenario: After successful simulation

- **WHEN** simulation completes successfully
- **THEN** the "Annotate DC" button SHALL become enabled
- **THEN** the status SHALL show "Lepton: simulation complete"

---

### Requirement: Session API for Lepton-EDA bridge

The system SHALL register the following `@api_command` functions in `pqwave/session/api.py`:

| Command | Signature | Description |
|---------|-----------|-------------|
| `lepton_watch` | `lepton_watch(path)` | Start watching a `.sch` file |
| `lepton_unwatch` | `lepton_unwatch()` | Stop watching |
| `lepton_simulate` | `lepton_simulate()` | Trigger full pipeline manually |
| `lepton_probe_net` | `lepton_probe_net(name)` | Highlight a net in lepton-schematic |
| `lepton_probe_part` | `lepton_probe_part(ref, pin=None)` | Highlight a component or pin |
| `lepton_clear` | `lepton_clear()` | Clear all lepton-schematic highlights |
| `lepton_annotate_dc` | `lepton_annotate_dc(voltages=None)` | Stamp DC voltages onto the schematic |
| `lepton_clear_annotations` | `lepton_clear_annotations()` | Remove all floating labels |
| `lepton_config` | `lepton_config(key, value=None)` | Get or set bridge configuration |

Each command SHALL follow the existing `SessionAPI` mutation callback pattern: if `_on_mutation` is set (GUI mode), emit the mutation event and return early; otherwise execute directly (headless mode).

#### Scenario: API usage in headless mode

- **WHEN** `api.lepton_watch("circuit.sch")` is called in headless mode
- **THEN** the file watcher SHALL start
- **THEN** `api.lepton_simulate()` SHALL run the pipeline and load results
- **THEN** `api.lepton_annotate_dc()` SHALL stamp DC voltages

#### Scenario: API usage in GUI mode

- **WHEN** `api.lepton_simulate()` is called via the REPL in GUI mode
- **THEN** the mutation SHALL be emitted and the MainWindow SHALL handle the actual pipeline execution

---

### Requirement: Tool path configuration

The system SHALL allow users to configure `lepton-netlist` and `ngspice` paths via the Settings dialog and the `lepton_config` API.

The paths SHALL be stored in `ApplicationState.tool_paths` with keys `"lepton_netlist"` and `"ngspice"`.
The paths SHALL be persisted to `~/.pqwave/prefs.json` alongside existing tool paths.
The Settings dialog SHALL include input fields for both paths in the "External Converter Paths" group.

#### Scenario: Custom lepton-netlist path

- **WHEN** the user sets `tool_paths["lepton_netlist"]` to `/opt/local/bin/lepton-netlist`
- **THEN** `shutil.which("lepton-netlist")` SHALL NOT be used
- **THEN** the specified path SHALL be invoked for netlist export

#### Scenario: Default PATH detection

- **WHEN** no custom path is configured
- **THEN** `shutil.which("lepton-netlist")` and `shutil.which("ngspice")` SHALL be used

---

### Requirement: Menu integration

The system SHALL add a "Lepton Bridge" submenu to the File menu with the following actions:
- **Watch Schematic...** — opens file dialog to select a `.sch` file and starts watching
- **Simulate Now** — manually triggers simulation of the currently watched file
- **Annotate DC** — stamps DC operating point voltages onto the schematic
- **Clear Annotations** — removes all floating labels from the schematic
- **Stop Watching** — stops the file watcher and hides the control bar
- **Cross-Probe** submenu with **Probe Selected Net**, **Clear Highlight**

Menu actions SHALL be disabled when no bridge is active (no file being watched).

#### Scenario: No file watched

- **WHEN** no `.sch` file is being watched
- **THEN** "Simulate Now", "Stop Watching", "Annotate DC", "Clear Annotations", and "Cross-Probe" actions SHALL be disabled
- **THEN** "Watch Schematic..." SHALL remain enabled
