## Why

pqwave's multi-run analysis can measure observed correlations between parameters and performance (via Spearman sensitivity ranking), but users cannot go the other direction: specify intended correlations and generate simulation inputs that realize them. Commercial PDKs ship correlation matrices alongside their statistical models, yet no open-source tool bridges the gap from a correlation matrix to correlated SPICE simulations. With multi-dataset MC now complete, pqwave can own this niche — generating correlated parameter values that users feed to their simulator of choice.

## What Changes

- **Correlation matrix management**: Load/edit/store square correlation matrices with labeled rows/columns. Interactive editor dialog with symmetry enforcement and auto-sizing from parameter selection. (The `CorrelationMatrix` dataclass in `mc_collection.py` is already implemented.)
- **SPICE model file parser**: Parse `.model` statements to extract model names, parameter names, and nominal values. Auto-populate parameter rows with `{model}_{param}` logical names — the row IS the mapping, no separate mapping step needed.
- **Cholesky decomposition engine**: Compute `L = chol(R)` from correlation matrix `R`. Generate correlated random vectors using `L·Z` where `Z` is independent standard normals.
- **Multi-format output**: Generate (a) ngspice `.control` scripts using `sgauss(0)` + Cholesky `let` expressions + `altermod` loops, (b) simulator-agnostic CSV files with per-run parameter values, (c) `.param` snippets for copy-paste into LTspice/QSPICE netlists. pqwave does NOT run simulations — it produces input values only.
- **REPL/API commands**: `mc_correlation_load`, `mc_correlation_show`, `mc_correlation_edit`, `mc_generate` registered via `@api_command`.

## Capabilities

### New Capabilities

- `correlation`: Correlation matrix management, SPICE `.model` file parsing, Cholesky decomposition for correlated parameter value generation, and multi-format output (ngspice `.control` script, simulator-agnostic CSV, `.param` snippet). Parameter mapping via auto-populated `{model}_{param}` rows — no separate mapping UI. pqwave generates values only; it does not run simulations.

### Modified Capabilities

None — this is net-new functionality layered on existing MC infrastructure.

## Impact

- **Analysis engine**: New `pqwave/analysis/correlation.py` with `compute_cholesky()`, `generate_correlated_values()`, `generate_control_script()`, `generate_csv()`, `generate_param_snippet()`
- **Models**: `CorrelationMatrix` dataclass already exists in `mc_collection.py` — no changes needed
- **UI**: New `CorrelationMatrixEditor` dialog, model file parser integration with MC open dialog or standalone
- **API**: Four new `@api_command` registrations in session/api.py
- **Dependencies**: `numpy.linalg.cholesky` (already available — numpy is a core dependency)
