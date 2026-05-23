## Context

The multi-dataset Monte Carlo change (archived) laid the full foundation: `MCRunCollection`, step-aware parsing, MC rendering (spaghetti/envelope/single-run), multi-run analysis (stats, histogram, yield, scatter, sensitivity, worst-cases), and REPL commands. Task 11 "Correlation tools" was explicitly deferred — the `CorrelationMatrix` data model was implemented and tested, but the generation pipeline (model file parser, Cholesky engine, script generator, editor dialog) was deferred pending resolution of the parameter mapping story.

The mapping problem: a correlation matrix uses logical names ("vth_nmos"), but generated SPICE scripts must reference `@n1[vth0]` (model-qualified SPICE names), and model files define the nominal values. Three name spaces that need bridging.

The QSPICE community has an identical unmet need — users want to feed pre-generated correlated values into simulations but have no native tooling (Qorvo forum thread #22321).

pgwave's stance: it is a viewer and (with this change) a value generator. It does NOT run simulations.

## Goals / Non-Goals

**Goals:**
- Parse SPICE `.model` statements to extract model names, parameter names, and nominal values
- Provide an interactive editor for square correlation matrices with labeled rows/columns
- Compute Cholesky decomposition L from correlation matrix R (R = L·Lᵀ)
- Generate correlated parameter values from uncorrelated standard normals via L·Z
- Output in three formats: ngspice `.control` script, simulator-agnostic CSV, `.param` snippet
- Expose all functionality through GUI (dialog) and REPL/API (`@api_command`)
- Support deterministic output given a seed

**Non-Goals:**
- Running simulations (pqwave is a viewer, not a simulator)
- Auto-detecting which parameters to vary (user chooses)
- Per-instance mismatch (process variation only for v1)
- ngspice `TRACK()` function implementation (pqwave generates scripts, doesn't modify ngspice)
- Template persistence for correlation state (saved for later phase)

## Decisions

### D1: Auto-populated rows as the mapping

**Decision**: The `.model` file parser produces rows `{model, param, nominal, logical_name}` where `logical_name` defaults to `{model}_{param}`. This single row IS the full mapping — no separate mapping step or dialog.

**Rationale**: IHP SG13G2's open PDK already uses a flat naming convention (`sg13g2_lv_nmos_vfbo_norm`) that embeds device+param identity in the name. Following this pattern avoids the three-name-space problem entirely. The user can rename the logical name if desired, but the default works out of the box.

**Alternatives considered**: A separate mapping dialog with logical→SPICE name pairs would add a UI step and conceptual overhead. Rejected as unnecessary indirection.

### D2: Per-simulator random functions in generated output

**Decision**: Output formats use each simulator's native random function. ngspice `.control` scripts use `sgauss(0)` as the raw σ=1 normal source with Cholesky L coefficients in `let` expressions. CSV output pre-generates values in Python using `numpy.random.normal` — no simulator random function needed. `.param` snippets bake final physical values (no random function at all).

**Rationale**: No cross-simulator standard random function exists. LTspice uses `mc(x,y)`/`gauss()`, QSPICE uses `random()`/`gauss()`, ngspice uses `sgauss()`/`sunif()`. Only ngspice exposes a raw standard-normal primitive suitable for Cholesky multiplication. For other simulators, pre-computed CSV values are the universal path.

| Random source | `.control` script | CSV | `.param` snippet |
|---|---|---|---|
| Generator | `sgauss(0)` (ngspice) | `numpy.random.normal` (Python) | None (pre-baked values) |
| Works with | ngspice only | Any simulator | LTspice, QSPICE |

### D3: Cholesky as the sole correlation method

**Decision**: Use Cholesky decomposition (`numpy.linalg.cholesky`) exclusively for generating correlated values. No eigen decomposition or copula methods.

**Rationale**: Cholesky is the standard method documented in literature (Champac & Gervacio, 2018) and directly maps to the `L·Z` multiplication that ngspice `let` expressions can express. The correlation matrix must be positive semi-definite for Cholesky to succeed — the editor validates this.

**Alternatives considered**: Eigen decomposition would handle non-PSD matrices gracefully but produces expressions that are harder to express in ngspice `let` statements. Copula methods add complexity without benefit for Gaussian process variation.

### D4: `CorrelationMatrix` on `MCRunCollection`

**Decision**: The `CorrelationMatrix` instance is stored on `MCRunCollection` (already has the dataclass), not as a separate top-level field on `ApplicationState`.

**Rationale**: Consistent with the existing pattern — `parameters`, `display_mode`, `run_filter` all live on the collection. Correlation is a property of the run set, not the session.

### D5: Output formats share a common generation core

**Decision**: All three output formats call the same `generate_correlated_values()` function that produces an `(n_runs, n_params)` NumPy array. Each output formatter serializes differently.

**Rationale**: Avoids duplicating the Cholesky math. The CSV formatter writes numbers directly. The `.control` formatter writes `sgauss(0)` + `let` expressions that produce the same distribution at runtime. The `.param` formatter writes per-run `.param` lines with baked values.

## Risks / Trade-offs

- **`.param` snippet limited utility**: LTspice evaluates `.param` once at startup, so a snippet can't express multi-run MC without `.step` + per-step param tables. → Document this clearly; CSV + external script is the recommended universal path for non-ngspice simulators.
- **Correlation matrix must be PSD**: Non-positive-semidefinite matrices (from inconsistent user input) will fail Cholesky. → Validate before generating; show clear error with guidance.
- **ngspice `let` expression limits**: Very large correlation matrices produce long `let` expressions that may hit ngspice line-length limits. → Unlikely in practice (typical matrices are <10 params); document limit.
- **Model file format variance**: `.model` syntax varies across PDKs (BSIM3, BSIM4, PSP, etc.). → Parser handles the common `+param=value` continuation-line format; test against IHP SG13G2 and the ngspice example files in `docs/monte_carlo/examples/`.

## Open Questions

1. **Should the `.model` parser also handle `.lib` includes?** No for v1. Single-file parsing only. `.lib` traversal is explicitly noted as a future task (see tasks.md).

2. **CSV delimiter and encoding**: Comma-separated UTF-8 is the default. Tab-separated (TSV) is supported as an option via a delimiter parameter on the parser and formatter.

3. **Correlation matrix import formats**: CSV only. No JSON, HDF5, or other formats. CSV is the most common format in PDK documentation and the simplest interchange format.
