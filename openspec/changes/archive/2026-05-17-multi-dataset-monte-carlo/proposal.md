## Why

pqwave is currently limited to a single simulation file with a single flat dataset. Users doing Monte Carlo analysis, parameter sweeps, corner comparisons, or A/B testing must open files sequentially and mentally compare results. Meanwhile, the open-source EDA stack (ngspice + sky130 + xschem) has no tool for correlated MC analysis — commercial PDK correlation matrices and TRACK()-style variation cannot be expressed in ngspice's control language. pqwave can own this niche by becoming the bridge between PDK statistical intent and simulator capability.

## What Changes

- **Multi-dataset support**: Load multiple simulation files simultaneously. Traces from different datasets coexist in panels. Dataset combo switches the variable browser. `File > Open File` appends instead of replacing. New `File > Close Dataset` removes one. **BREAKING**: `load` API command now appends datasets rather than clearing.
- **Explicit Monte Carlo mode** (Approach B): `File > Open Monte Carlo...` opens a configuration dialog for step-aware multi-run loading. No auto-detection — users choose MC mode intentionally. Supports LTspice/QSPICE stepped files and ngspice vector-name-pattern files.
- **MC rendering**: Spaghetti plot (all runs overlaid), statistical envelope (mean ± Nσ), single-run isolation, nominal run highlighting, run filtering.
- **Multi-run analysis**: Per-timepoint statistics (mean, std, min, max across runs), scalar measurement histogram across runs, yield vs spec limits, scatter of measurement vs parameter, worst-case extraction, sensitivity ranking.
- **Correlation tools** (future phase): Load/edit correlation matrices, generate correlated parameter values via Cholesky decomposition. Output as ngspice `.control` scripts, simulator-agnostic CSV files, and `.param` snippets. pqwave does not run simulations — it produces the input values that users feed to their simulator of choice.
- **REPL/API**: Full command surface — `mc_load`, `mc_style`, `mc_stats`, `mc_histogram`, `mc_yield`, `mc_scatter`, `mc_param`, and multi-dataset primitives (`datasets`, `unload`).

## Capabilities

### New Capabilities

- `multi-dataset`: Load and manage multiple simulation datasets in one session. Dataset switching, cross-dataset trace coexistence, dataset removal.
- `monte-carlo`: Step-aware MC data loading (LTspice stepped files, QSPICE stepped files, ngspice vector-name-pattern files). Run grouping, MC display modes (spaghetti, envelope, single-run), nominal designation, run filtering, parameter annotation.
- `multi-run-analysis`: Cross-run statistics and visualization — per-timepoint mean/std/min/max, scalar measurement histograms, yield analysis, scatter plots, sensitivity ranking, worst-case extraction.
- `correlation`: (future phase) Correlation matrix management, SPICE `.model` file parsing, Cholesky decomposition for correlated parameter value generation, and multi-format output (ngspice `.control` script, simulator-agnostic CSV, `.param` snippet). Parameter mapping via auto-populated model_param rows — no separate mapping UI needed. pqwave generates values only; it does not run simulations.

### Modified Capabilities

None — all existing capabilities retain their current behavior. `File > Open File` changes implementation (append instead of clear) but preserves its specification: open a simulation file and make its variables available.

## Impact

- **Data model**: New `MCRunCollection`, `MCRun`, `CorrelationMatrix` types in `models/`. `ApplicationState` gains `mc_collection` field. `Dataset` gains run metadata.
- **File parsing**: `rawfile.py` — fix step-aware parsing for LTspice (UTF-16 null bytes, step slicing), add step extraction from QSPICE header (`.step param` and `.param` lines), add ngspice vector-name-pattern detection.
- **UI**: New `File > Open Monte Carlo...` menu item, MC configuration dialog, MC control bar in `control_panel.py`, spaghetti/envelope rendering in `trace_manager.py`, multi-run analysis dialogs.
- **API**: New `mc_*` commands registered via `@api_command`, multi-dataset commands (`datasets`, `unload`). Existing `load` command gains append behavior.
- **IPC**: Optional extension to xschem protocol for netlist/model forwarding (future phase).
- **Dependencies**: `numpy.linalg.cholesky` for correlation script generation (already available in project venv).
