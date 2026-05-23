# mc-tutorial-guide Specification

## Purpose
TBD - created by archiving change rework-mc-guide-tutorial. Update Purpose after archive.
## Requirements
### Requirement: Hybrid guide structure

The Monte Carlo user guide SHALL be organized in two parts: a feature reference (Part 1) followed by worked tutorials (Part 2). Part 1 SHALL provide compact tables of all MC capabilities with menu paths and API signatures. Part 2 SHALL be a sequence of worked examples anchored to files in `docs/monte_carlo/examples/`, each following the Input → Steps → Expected Output pattern with concrete values extracted from the example files.

#### Scenario: Guide opens with table of contents

- **WHEN** a user opens the guide
- **THEN** a table of contents lists both parts: the feature reference sections and the three tutorial examples with links

#### Scenario: Feature reference covers all capabilities

- **WHEN** a user scrolls through Part 1
- **THEN** compact tables describe loading modes, display modes, control bar controls, statistical analysis features, correlation tools, and session API commands with menu paths and command signatures

#### Scenario: RC filter example covers loading workflow

- **WHEN** a user follows the RC filter tutorial
- **THEN** the guide provides exact steps to open `rc_filter_mc.raw` via File > Open Monte Carlo, with the dialog values to enter (source type: named runs, base name: vout), and states the expected result (21 runs loaded, MC control bar visible)

#### Scenario: RC filter example covers display exploration

- **WHEN** a user follows the display mode tutorial
- **THEN** the guide shows how to switch between spaghetti, envelope (σ=3.0), and single modes, and describes what the user should see (e.g., "envelope mode shows the nominal run with shaded ±3σ bands; at 1 kHz the mean gain is approximately 0.85 with σ ≈ 0.35")

#### Scenario: RC filter example covers parameter annotation

- **WHEN** a user follows the parameter annotation tutorial
- **THEN** the guide shows how to load `rc_filter_params.csv` and use `mc_param` to annotate Rval and Cval, with the exact values from the file

#### Scenario: RC filter example covers sensitivity and scatter

- **WHEN** a user follows the sensitivity tutorial
- **THEN** the guide shows Analyze > MC Sensitivity with measurement `max(v(out))`, and presents the expected Spearman results (R: r≈-0.04, C: r≈-0.21 — C has stronger influence on max output for this filter)

#### Scenario: RC filter example covers yield and worst-case

- **WHEN** a user follows the yield tutorial
- **THEN** the guide shows Analyze > MC Yield with spec limits and reports the expected result (e.g., DC gain > 0.99 yields ~14% of runs) and the top 3 worst-case runs with their deviation values

#### Scenario: Ring oscillator example covers transient MC

- **WHEN** a user follows the ring oscillator tutorial
- **THEN** the guide shows how to load `MC_ring.raw` (31 transient runs), use envelope display mode to see ring oscillator variation, compute cross-run statistics, and create a histogram of peak-to-peak amplitudes (expected range: 3.10–3.15 V)

#### Scenario: LTspice example covers stepped loading

- **WHEN** a user follows the stepped loading tutorial
- **THEN** the guide shows how to open `MonteCarlo.raw` as a stepped file, notes the auto-detected parameter `x` (a dummy run counter), and explains the difference between stepped and pattern loading

### Requirement: API coverage in both parts

The feature reference (Part 1) SHALL include a compact table of all `mc_*` session API commands with signatures and one-line descriptions. Tutorial sections (Part 2) SHALL present API commands inline as "or via API" code blocks alongside GUI steps, plus a final standalone scripting example.

#### Scenario: Feature reference includes API command table

- **WHEN** a user looks up API commands in Part 1
- **THEN** a table lists all 17 `mc_*` commands with signature and purpose

#### Scenario: API appears alongside GUI instructions in tutorials

- **WHEN** a user reads a tutorial section
- **THEN** after GUI instructions, a code block shows the equivalent API command

#### Scenario: Final scripting example is self-contained

- **WHEN** a user reaches the end of the guide
- **THEN** a complete scripting example loads the RC filter data, annotates parameters, runs sensitivity, and prints results — all copy-paste runnable

