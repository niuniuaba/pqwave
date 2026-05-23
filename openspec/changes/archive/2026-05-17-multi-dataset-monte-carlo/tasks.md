## 1. Data model foundations

- [ ] 1.1 Add `MCRun`, `MCRunCollection`, and `CorrelationMatrix` dataclasses to `pqwave/models/state.py`
- [ ] 1.2 Add `mc_collection: MCRunCollection | None` field to `ApplicationState`
- [ ] 1.3 Add `source_dataset_idx` and `step_index` fields to `Trace` dataclass for multi-dataset trace provenance
- [ ] 1.4 Add `run_metadata: dict` field to `Dataset` for per-dataset run parameter storage

## 2. Fix step-aware raw file parsing

- [ ] 2.1 Fix LTspice UTF-16 null-byte header parsing in `rawfile.py` — current output has nulls between chars
- [ ] 2.2 Implement per-step data extraction using `get_wave(step=N)` and `get_len(step)` from spicelib
- [ ] 2.3 Parse QSPICE `.step param` and `.param` lines from raw file header when `.log` is unavailable
- [ ] 2.4 Add ngspice vector-name-pattern detection (`vout\d+`, `fft\d+`) in `rawfile.py`
- [ ] 2.5 Expose step count, step parameter names, and per-step parameter values via `RawFile` API

## 3. Multi-dataset UI

- [ ] 3.1 Change `_load_raw_file` to append datasets instead of clearing (`clear_datasets` call removed)
- [ ] 3.2 Add `File > Close Dataset` menu item and handler that removes a dataset and its traces
- [ ] 3.3 Add dataset combo box to `ControlPanel` that switches the active dataset for the variable browser
- [ ] 3.4 Update `_update_variable_combo` to show signals from the active dataset only
- [ ] 3.5 Add status bar hint when a stepped file is opened flat: "N steps detected — File > Open Monte Carlo..."

## 4. Monte Carlo loading UI

- [ ] 4.1 Add `File > Open Monte Carlo...` menu item in `menu_manager.py`
- [ ] 4.2 Create `MCOpenDialog` with source type selector (single stepped file / multiple files / directory)
- [ ] 4.3 Implement step detection preview in the dialog (show step count, parameter names, signal list)
- [ ] 4.4 Implement ngspice pattern configuration in the dialog (naming pattern, run count override)
- [ ] 4.5 Wire dialog result through `_on_session_mutation` to load data as `MCRunCollection`

## 5. MC control bar

- [ ] 5.1 Create `MCControlBar` widget with run count display, display mode selector, sigma spinner, run filter input
- [ ] 5.2 Add nominal run selector (spin box, default 0)
- [ ] 5.3 Add parameter annotation entry (param name + values or file import)
- [ ] 5.4 Show/hide `MCControlBar` based on whether `mc_collection` is set
- [ ] 5.5 Connect control bar changes to `trace_manager` redraw and analysis recomputation

## 6. MC rendering (spaghetti + envelope)

- [ ] 6.1 Add `_create_mc_spaghetti()` method to `TraceManager` — thin semi-transparent curves per run
- [ ] 6.2 Add `_create_mc_envelope()` method — mean line + fill-between for ±Nσ bands
- [ ] 6.3 Implement nominal run highlighting (thicker line, distinct color)
- [ ] 6.4 Implement run-filtered rendering (only selected runs displayed)
- [ ] 6.5 Add `_create_mc_single_run()` method — standard rendering for one run at full opacity
- [ ] 6.6 Integrate MC rendering with existing log-mode transforms (data pre-transformed to log10)
- [ ] 6.7 Apply downsampling per-run (max 500 visible runs, randomly sampled for display)

## 7. Multi-run analysis engine

- [ ] 7.1 Create `pqwave/analysis/multi_run.py` with `compute_cross_run_stats()` — per-timepoint mean, std, min, max
- [ ] 7.2 Add `compute_run_measurements()` — evaluate expression per run, return array of scalars
- [ ] 7.3 Add `compute_yield()` — per-point or scalar yield vs spec limits
- [ ] 7.4 Add `compute_worst_cases()` — top N runs by deviation from nominal
- [ ] 7.5 Add `compute_sensitivity()` — Spearman correlation between params and measurements
- [ ] 7.6 Add `compute_scatter_data()` — measurement vs parameter pairs for scatter plotting

## 8. Multi-run analysis UI

- [ ] 8.1 Add "MC Statistics" action to Analyze menu, calling `mc_stats` on active signal group
- [ ] 8.2 Add "MC Histogram" dialog — measurement expression + bin config, uses existing `compute_histogram`
- [ ] 8.3 Add "MC Yield" dialog — signal, low/high limits, condition
- [ ] 8.4 Add "MC Scatter" dialog — measurement expression + parameter selector
- [ ] 8.5 Add "MC Sensitivity" action — ranks parameters, shows result in a table dialog
- [ ] 8.6 Add "Worst Cases" action — shows top N runs with deviation values and params

## 9. API / REPL commands

- [ ] 9.1 Add multi-dataset commands: `datasets()`, `dataset(idx)`, `unload(idx)` to `SessionAPI`
- [ ] 9.2 Add `mc_load(source)` method to `SessionAPI` — delegates to file loading + run collection creation
- [ ] 9.3 Add `mc_info()`, `mc_style()`, `mc_nominal()`, `mc_filter()`, `mc_param()`, `mc_group()`, `mc_ungroup()` methods
- [ ] 9.4 Add `mc_stats()`, `mc_histogram()`, `mc_yield()`, `mc_scatter()`, `mc_worst()`, `mc_sensitivity()` methods
- [ ] 9.5 Register all new commands with `@api_command` decorator
- [ ] 9.6 Wire all new actions through `MainWindow._on_session_mutation` dispatch
- [ ] 9.7 Update `help()` output to include MC commands
- [ ] 9.8 Update REPL autocomplete to include MC commands

## 10. Tests

- [ ] 10.1 Unit tests for `MCRunCollection` data model
- [ ] 10.2 Unit tests for step-aware parsing (LTspice UTF-16, QSPICE header, ngspice pattern detection)
- [ ] 10.3 Unit tests for multi-run analysis engine (`compute_cross_run_stats`, `compute_yield`, `compute_sensitivity`)
- [ ] 10.4 Integration tests for multi-dataset load/switch/unload flow
- [ ] 10.5 Integration tests for MC load from real example files in `docs/monte_carlo/examples/`
- [ ] 10.6 Integration tests for REPL commands (load → mc_load → mc_stats → mc_histogram)

## 11. Correlation tools (future phase)

> **Deferred**: Correlation tools are explicitly scoped to a future phase per `design.md` Open Questions. The `CorrelationMatrix` data model is implemented and ready; Cholesky decomposition, script generation, and the editor dialog are deferred until the parameter mapping story (Hurdle 4) is solved.

- [x] 11.1 ~~Create `pqwave/analysis/correlation.py`~~ — **Deferred**: future phase per design.md
- [x] 11.2 ~~Create `CorrelationMatrixEditor` dialog~~ — **Deferred**: future phase per design.md
- [x] 11.3 ~~Implement `.model` line parser~~ — **Deferred**: future phase per design.md
- [x] 11.4 ~~Create `MC Script Generator`~~ — **Deferred**: future phase per design.md. Outputs: ngspice `.control` script + simulator-agnostic CSV of per-run parameter values + `.param` snippet (per D7).
- [x] 11.5 ~~Add `mc_correlation_load()`, `mc_correlation_show()`, `mc_generate()`~~ — **Deferred**: future phase per design.md
