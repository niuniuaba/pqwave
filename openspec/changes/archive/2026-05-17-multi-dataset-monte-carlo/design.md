## Context

pqwave currently loads a single simulation file at a time. `File > Open File` clears all existing data before loading the new file. The `RawFile.parse()` method accesses only `_plots[0]` and calls `trace.get_wave()` without a step argument, discarding multi-run step data that spicelib already provides.

Three simulators structure MC results differently:
- **LTspice**: `.step param X 0 20 1` produces stepped data with same variable names across steps. spicelib detects steps via companion `.log` files (21 steps with `{'x': 0}`..`{'x': 20}`).
- **QSPICE**: `.step param run 1 100 1` with `Flags: complex stepped`. Step info is in the raw file header but spicelib fails to extract it without a `.log` file.
- **ngspice**: No `.step` directive. Control language loops produce uniquely named vectors (`vout0`, `vout1`, ... `vout30`) in a single raw file, or multiple raw files (one per run).

The project follows an explicit philosophy (Approach B): users know what they're doing. MC mode is entered intentionally via `File > Open Monte Carlo...`, never through auto-detection.

## Goals / Non-Goals

**Goals:**
- Load multiple simulation files into one session without clearing existing data
- Support step-aware loading for LTspice stepped files, QSPICE stepped files, and ngspice vector-name-pattern files
- Render MC data as spaghetti plots, statistical envelopes, and single-run views
- Provide cross-run analysis: statistics, histograms, yield, scatter, sensitivity
- Expose all functionality through both GUI and REPL/API
- Lay data model groundwork for future correlation tools

**Non-Goals:**
- Running simulations (pqwave is a viewer, not a simulator)
- Auto-detection of MC data (users choose MC mode explicitly)
- Per-device mismatch correlation (process-only for v1)
- Real-time collaborative MC analysis
- Template persistence for MC state (saved for later phase)

## Decisions

### D1: Multi-dataset as foundation, MC as layer on top

**Decision**: Build generic multi-dataset support first. MC mode composes on top — `mc_load()` internally calls multi-dataset primitives, then wraps results in `MCRunCollection`.

**Rationale**: Multi-dataset is independently useful (A/B comparison, corner analysis, calibration). MC mode stays thin — no duplicate file I/O. Clear separation of concerns.

**Alternatives considered**: Building MC directly into the single-dataset model would couple step awareness to file loading at every point. Rejected because it blocks non-MC multi-file use cases.

### D2: Explicit MC mode (Approach B)

**Decision**: `File > Open File` always loads flat, always appends. `File > Open Monte Carlo...` opens a dedicated dialog where users configure MC grouping. No detection logic gates the normal flow. When a stepped file is opened flat, a non-intrusive status bar hint suggests the MC menu item.

**Rationale**: pqwave users are domain experts who know whether they ran Monte Carlo. Auto-detection creates false positives (stepped parameter sweeps that aren't statistical) and false negatives (ngspice files without step metadata). Explicit mode puts the user in control.

**Alternatives considered**: Auto-detection with a "this file contains N runs" dialog was rejected because it interrupts normal workflow and conflates data structure detection with user intent.

### D3: Two ingestion strategies for three simulator formats

**Decision**: Support both step-based and name-pattern-based ingestion:
- **Step-based**: Use `get_wave(step=N)` for per-step slicing. Fix LTspice UTF-16 null-byte parsing and QSPICE step extraction from header `.step param` / `.param` lines.
- **Name-pattern**: Group traces matching `vout\d+`, `fft\d+`, etc. into MC runs when the user specifies a naming pattern.

**Rationale**: ngspice cannot produce step metadata — it has no `.step` directive. The `vout0..voutN` naming convention is its only mechanism for multi-run output. Supporting both covers all major simulators.

**Alternatives considered**: Requiring ngspice users to write separate raw files per run was rejected as user-hostile — the existing ngspice MC examples all use the single-file naming convention.

### D4: Cholesky decomposition for correlation script generation

**Decision**: Pre-compute the Cholesky factor L of the correlation matrix in Python (`numpy.linalg.cholesky`), then bake L as hardcoded `let` expressions in the generated ngspice `.control` script.

**Rationale**: ngspice has no matrix operations — no multiply, no inverse, no Cholesky. It can only do element-wise vector arithmetic. Pre-computing L means the generated script uses only `sgauss(0)` and `let` statements, which ngspice handles natively.

**Alternatives considered**: Adding matrix operations to ngspice upstream was rejected as out of scope. Implementing TRACK() in ngspice C source was considered but requires fork maintenance.

### D5: Parameter metadata as the analysis-generation bridge

**Decision**: `mc_param()` annotates runs with per-parameter values. All analysis commands (`mc_scatter`, `mc_sensitivity`) consume this metadata. Correlation generation (`mc_generate`) is a separate downstream that reads the same metadata.

**Rationale**: Analysis works on any multi-run data regardless of origin (MC, sweep, corners, manual batch). Decoupling analysis from generation keeps the code modular and the API surface clean.

### D6: MC state lives on ApplicationState

**Decision**: `ApplicationState` gains a single `mc_collection: MCRunCollection | None` field. MC display mode, run filter, envelope sigma are stored on the collection, not per-panel.

**Rationale**: Consistent with how `histogram_config` and `fft_config` are stored as single instances. MC is a session-level concept — all panels view the same run set. Per-panel MC state (e.g., different panels showing different signal groups) can be added later if needed.

### D7: Multi-simulator output formats

**Decision**: The correlation script generator produces simulator-agnostic CSV parameter files alongside ngspice-specific `.control` scripts. pqwave does NOT execute simulations — it only generates the input values.

**Rationale**: QSPICE and LTspice users have the same unmet need (pre-generated correlated parameter values) but no native Cholesky support. A CSV of per-run parameter values is universally consumable — users feed it into any simulator via external scripting (PyQspice, Python batch, shell loops). ngspice gets the richer `.control` script output because its control language can express the full generation + simulation loop inline, but the core value (the correlated numbers) is format-agnostic.

**Output formats:**

| Format | Target | Content |
|--------|--------|---------|
| `.control` script | ngspice | Full loop with `altermod` + Cholesky L + `tran`/`ac` + `write` |
| CSV | QSPICE, LTspice, any | One row per run, one column per varied parameter + seed |
| `.param` snippet | LTspice, QSPICE | Per-run `.param` lines with correlated values, paste into netlist |

**Alternatives considered**: Generating only ngspice scripts would limit the feature to ngspice users. Building simulator-specific runners for each engine would violate pqwave's viewer-only scope.

## Risks / Trade-offs

- **LTspice UTF-16 parsing fragility**: LTspice raw files use UTF-16 LE encoding with null bytes between ASCII characters. spicelib handles this internally but pqwave's own header parser may need updates. → Test against real LTspice MC files from the examples directory.
- **ngspice naming pattern ambiguity**: `vout0..vout10` could be 11 MC runs of the same signal or 11 genuinely different output nodes. → The MC dialog lets users confirm or override the inferred grouping before any data is loaded.
- **Performance with large run counts**: 1000+ runs × spaghetti plot = 1000 PlotCurveItems. → Apply run-level downsampling (max 500 visible runs, randomly sampled for display). Statistics always use full data.
- **Parameter name mapping**: Correlation matrix entries use logical names (`vth0_nmos`), netlists use SPICE names (`@n1[vth0]`). → The MC script generator provides a mapping UI; initial version accepts user-provided name pairs.
- **`load` command behavior change**: Changing `load` from clear-and-load to append-and-load is **BREAKING** for scripts that depend on the clear behavior. → Documented in release notes. A new `reload` command (or `load --clear`) provides the old behavior explicitly.

## Open Questions

1. **Should `mc_load` accept a directory glob for ngspice multi-file MC (Example 3 style)?** Tentative yes — `mc_load("results/mc_run_*.raw")` — but deferred to a later iteration.
2. **Template persistence for MC state**: Should the template system save/restore MC configuration? Deferred to a later phase.
3. **Per-panel MC views**: Should different panels be able to show different run subsets or display modes? Deferred — v1 uses session-level MC state.
