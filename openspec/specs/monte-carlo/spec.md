## ADDED Requirements

### Requirement: Open Monte Carlo data explicitly

The system SHALL provide `File > Open Monte Carlo...` as a distinct menu item from `File > Open File`. The MC dialog SHALL allow users to select a source type (single stepped file, multiple files) and configure how runs are grouped before loading. The system SHALL NOT auto-detect MC data during normal file open.

#### Scenario: Open single stepped file as MC
- **WHEN** a user opens a stepped LTspice raw file via `File > Open Monte Carlo...` with source type "Single stepped file"
- **THEN** the system detects step count and parameter values, presents them for confirmation, and loads all steps as a run collection

#### Scenario: Open multiple files as MC runs
- **WHEN** a user selects three raw files via `File > Open Monte Carlo...` with source type "Multiple files"
- **THEN** each file becomes one run in the collection, with run index corresponding to file order

### Requirement: Step-based ingestion for LTspice and QSPICE

The system SHALL parse stepped raw files by reading step metadata and slicing trace data per step. For LTspice, steps SHALL be extracted from the companion `.log` file or the raw file header step count. For QSPICE, steps SHALL be extracted from `.step param` and `.param` lines in the raw file header. Each step becomes one run in the collection.

#### Scenario: LTspice stepped file ingestion
- **WHEN** loading an LTspice raw file with `Flags: stepped` and 21 steps of parameter X
- **THEN** the system creates 21 runs, each with `params: {X: step_value}`, and groups traces by their base variable names

#### Scenario: QSPICE stepped file ingestion
- **WHEN** loading a QSPICE `.qraw` file with `Flags: complex stepped` and `.step param run 1 100 1`
- **THEN** the system creates 100 runs from the 40,000 concatenated data points (400 per run)

### Requirement: Name-pattern-based ingestion for ngspice

The system SHALL support grouping traces into MC runs by naming pattern. When a raw file contains traces named `vout0`, `vout1`, ... `voutN`, the system SHALL group them as runs of a signal named `vout` when the user specifies or confirms the pattern.

#### Scenario: Auto-group ngspice MC traces
- **WHEN** loading an ngspice raw file with traces `time`, `vout0` through `vout30` via MC mode
- **THEN** the system suggests grouping `vout\d+` as 31 runs of signal `vout`, and `time` as the shared X axis

#### Scenario: Manual pattern override
- **WHEN** the suggested grouping does not match user intent
- **THEN** the user MAY override the naming pattern in the MC dialog before loading

### Requirement: MC display modes

The system SHALL support three display modes for MC signal groups: spaghetti (all runs overlaid with low opacity), envelope (mean ± Nσ band with configurable σ), and single-run (one run at full opacity). The display mode SHALL be configurable per signal group.

#### Scenario: Spaghetti plot rendering
- **WHEN** a user adds an MC-grouped signal to a panel with display mode "spaghetti"
- **THEN** the system renders all runs as thin, semi-transparent curves, with the nominal run at full opacity and distinct color

#### Scenario: Envelope rendering
- **WHEN** a user switches display mode to "envelope" with sigma=3
- **THEN** the system computes per-timepoint mean and std across runs, renders the mean as a solid line, and fills the area between mean-3σ and mean+3σ

#### Scenario: Single-run view
- **WHEN** a user switches display mode to "single" with run=5
- **THEN** only run 5 is rendered at full opacity, and all other runs are hidden

### Requirement: Nominal run designation

The system SHALL designate run 0 as the nominal run by default. Users MAY change the nominal run index. The nominal run SHALL be rendered distinctly (thicker line, different color) in spaghetti and envelope modes.

#### Scenario: Default nominal is run 0
- **WHEN** an MC collection is loaded
- **THEN** run 0 is designated as nominal and highlighted in all displays

#### Scenario: Change nominal run
- **WHEN** a user sets nominal run to 5 via the MC control bar
- **THEN** run 5 is rendered as the highlighted nominal in all displays

### Requirement: Run filtering

The system SHALL allow users to show a subset of runs by specifying run indices or a range. Filtered-out runs SHALL be excluded from both display and statistical calculations.

#### Scenario: Filter to specific runs
- **WHEN** a user sets run filter to `[0, 5, 10, 15]`
- **THEN** only runs 0, 5, 10, and 15 are displayed and used in envelope statistics

#### Scenario: Reset filter to all runs
- **WHEN** a user sets run filter to "all"
- **THEN** all runs are displayed and included in statistics

### Requirement: Parameter annotation

The system SHALL allow users to annotate each run with parameter name-value pairs. Parameter metadata SHALL be used by scatter plots and sensitivity analysis. For stepped files, parameters SHALL be auto-populated from step metadata.

#### Scenario: Auto-populate from step metadata
- **WHEN** loading a stepped file with parameter X varying from 0 to 20
- **THEN** each run is annotated with its X value automatically

#### Scenario: Manual parameter annotation for ngspice
- **WHEN** loading ngspice MC data where no step metadata exists
- **THEN** the user MAY annotate runs with parameter values via `mc_param("vth0", [0.58, 0.62, ...])` in the REPL

### Requirement: REPL commands for MC

The system SHALL provide `mc_load`, `mc_style`, `mc_nominal`, `mc_filter`, `mc_param`, `mc_group`, `mc_ungroup`, and `mc_info` commands via the REPL/API, following the existing `@api_command` registration pattern.

#### Scenario: MC load via REPL
- **WHEN** a user executes `mc_load("bandpass_mc.raw")` in the REPL
- **THEN** the system loads the stepped file as an MC run collection and returns run count and signal names

#### Scenario: Change display mode via REPL
- **WHEN** a user executes `mc_style("envelope", sigma=2)` in the REPL
- **THEN** the active signal group switches to envelope mode with ±2σ bands
