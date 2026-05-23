## 1. SPICE model file parser

- [ ] 1.1 Create `pqwave/analysis/correlation.py` with `parse_model_file(path)` — parses `.model` statements, extracts model name, parameter names, and nominal values (handles `+` continuation lines, `agauss()`/`gauss()` nominal extraction, multi-model files). Does NOT handle `.lib` includes (future task).
- [ ] 1.4 **Future**: Add `.lib` include traversal to model file parser, resolving include paths relative to the parsed file's directory
- [ ] 1.2 Return structured data: `list[dict]` where each dict has `{model, param, nominal, logical_name}` with `logical_name` defaulting to `{model}_{param}`
- [ ] 1.3 Test against ngspice example files in `docs/monte_carlo/examples/ngspice/` (MC_ring.sp has complex BSIM3 model cards)

## 2. Cholesky decomposition engine

- [ ] 2.1 Add `compute_cholesky(correlation_matrix: CorrelationMatrix) -> np.ndarray` to `correlation.py` — returns lower-triangular L matrix
- [ ] 2.2 Add `generate_correlated_values(L, nominals, sigmas, n_runs, seed=None) -> np.ndarray` — returns `(n_runs, n_params)` array of correlated physical values
- [ ] 2.3 Validate correlation matrix is positive semi-definite before Cholesky; raise clear error if not
- [ ] 2.4 Support deterministic output via numpy seed parameter

## 3. Multi-format output generator

- [ ] 3.1 Add `generate_control_script(params, nominals, L, output_path, sim_command)` — writes ngspice `.control` script with `sgauss(0)` + Cholesky `let` expressions + `altermod` loop
- [ ] 3.2 Add `generate_csv(values, param_names, output_path, delimiter=",")` — writes simulator-agnostic CSV with header and per-run rows. Supports comma (default) and tab (`delimiter="\t"`) delimiters.
- [ ] 3.3 Add `generate_param_snippet(values, param_names, output_path)` — writes `.param` lines with baked correlated values
- [ ] 3.4 All generators share `generate_correlated_values()` as the common computation core (per D5)

## 4. Correlation Matrix Editor dialog

- [ ] 4.1 Create `pqwave/ui/correlation_editor.py` with `CorrelationMatrixEditor(QDialog)` — N×N editable grid, labeled rows/columns, locked diagonal=1.0, symmetric mirroring
- [ ] 4.2 Add "Load Model File..." button that triggers `.model` parsing and auto-populates the parameter list
- [ ] 4.3 Add "Load Matrix..." (CSV only) / "Export Matrix..." (CSV) buttons for correlation matrix import/export
- [ ] 4.4 Wire dialog into `menu_manager.py` under Analyze menu as "MC Correlation..."
- [ ] 4.5 Dialog stores result on `ApplicationState().mc_collection` as a `CorrelationMatrix` instance

## 5. Generation dialog

- [ ] 5.1 Create generation settings panel (number of runs, sigma/absolute variation per param, seed, output format selector, output path)
- [ ] 5.2 Wire "Generate" button to call the appropriate output formatter from task group 3
- [ ] 5.3 Show preview of first 5 rows before writing full output
- [ ] 5.4 Recommend CSV format when target is LTspice or QSPICE (per spec scenario)

## 6. REPL/API commands

- [ ] 6.1 Add `mc_correlation_load(path)` — loads correlation matrix from CSV, stores on mc_collection
- [ ] 6.2 Add `mc_correlation_show()` — prints current correlation matrix as formatted table
- [ ] 6.3 Add `mc_correlation_edit()` — opens the CorrelationMatrixEditor dialog
- [ ] 6.4 Add `mc_generate(output_path, format="csv", runs=100, seed=None)` — generates values using current correlation matrix and parameter annotations
- [ ] 6.5 Register all commands with `@api_command` decorator, wire through `MainWindow._on_session_mutation`
- [ ] 6.6 Update REPL autocomplete to include correlation commands

## 7. Tests

- [ ] 7.1 Unit tests for `parse_model_file()` — BSIM3 cards, continuation lines, agauss nominals, multi-model files
- [ ] 7.2 Unit tests for `compute_cholesky()` — valid PSD matrix, identity matrix, non-PSD rejection
- [ ] 7.3 Unit tests for `generate_correlated_values()` — verify output shape, approximate correlation recovery, seed determinism
- [ ] 7.4 Unit tests for output formatters — verify `.control` script syntax, CSV round-trip, `.param` format
- [ ] 7.5 Integration test: parse model file → build correlation matrix → generate CSV → verify correlation in output
- [ ] 7.6 Integration test: full REPL flow — `mc_correlation_load` → `mc_correlation_show` → `mc_generate`
