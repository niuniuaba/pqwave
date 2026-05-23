## ADDED Requirements

### Requirement: Correlation matrix management

The system SHALL support loading, editing, and storing square correlation matrices where rows and columns are labeled with parameter names. Each entry SHALL be a float in [-1, 1] with diagonal forced to 1.0 and symmetry enforced. The `CorrelationMatrix` data model (already implemented in `mc_collection.py`) provides the storage representation.

#### Scenario: Load correlation matrix from CSV file
- **WHEN** a user loads a CSV file (comma-separated, UTF-8) containing a correlation matrix with labeled rows/columns
- **THEN** the system parses the matrix, validates symmetry and diagonal=1, and stores it on the MC collection

#### Scenario: Correlation matrix import is CSV only
- **WHEN** a user attempts to load a correlation matrix in JSON, HDF5, or any non-CSV format
- **THEN** the system returns an error indicating only CSV import is supported

#### Scenario: Edit correlation matrix interactively
- **WHEN** a user opens the Correlation Matrix Editor dialog
- **THEN** the system presents an N×N editable grid with parameter names as row/column headers, diagonal locked to 1.0, and lower triangle mirrored to upper triangle on edit

#### Scenario: Correlation matrix auto-sizes from parameter selection
- **WHEN** a user selects K parameters to vary from the parsed model parameters
- **THEN** the matrix editor resizes to K×K, preserving any existing correlation values for parameters that remain selected

#### Scenario: Export correlation matrix
- **WHEN** a user exports the matrix
- **THEN** the system writes a CSV file with parameter labels in the header row and column

#### Scenario: Reject non-PSD matrix on generate
- **WHEN** a user attempts to generate values from a correlation matrix that is not positive semi-definite
- **THEN** the system returns an error indicating which parameters contribute to the inconsistency

### Requirement: Model file parsing for statistical parameters

The system SHALL parse SPICE `.model` statements to extract model names, parameter names, and nominal values. Parsed parameters SHALL be presented as candidates for variation, with auto-generated logical names of the form `{model}_{param}` (e.g., `n1_vth0`).

#### Scenario: Parse BSIM3/BSIM4 model cards
- **WHEN** a user loads a model file containing `.model n1 nmos level=8 vth0=0.6322 u0=388.32 tox=9e-09`
- **THEN** the system extracts model name `n1`, parameter names `vth0`, `u0`, `tox`, and their nominal values `0.6322`, `388.32`, `9e-09`

#### Scenario: Parse multiple models in one file
- **WHEN** a user loads a model file with both `.model n1 nmos ...` and `.model p1 pmos ...`
- **THEN** the system extracts parameters from both models, disambiguating by model name prefix

#### Scenario: Extract nominal from agauss/gauss function calls
- **WHEN** a model file uses `vth0=agauss(0.6, 0.1, 3)` or `vth0=gauss(0.6, 0.1, 3)`
- **THEN** the system extracts the nominal value `0.6` (the first argument), not the full function call

#### Scenario: Handle continuation lines
- **WHEN** a model file uses `+` continuation lines for long parameter lists
- **THEN** the system correctly parses parameters spread across continuation lines

### Requirement: Cholesky decomposition for correlated value generation

The system SHALL compute the Cholesky decomposition L of the correlation matrix R (R = L·Lᵀ) using `numpy.linalg.cholesky`. For each run, the system SHALL generate an uncorrelated standard normal vector Z and produce the correlated vector Zc = L·Z. The correlated values SHALL be mapped to physical parameter values via Zc·σₚ + μₚ where μₚ and σₚ are the nominal value and absolute variation of parameter p.

#### Scenario: Generate correlated values for 3 parameters, 100 runs
- **WHEN** a user generates values with a 3×3 correlation matrix (params: n1_vth0, n1_u0, p1_vth0) and requests 100 runs
- **THEN** the system outputs 100 rows, each with 3 correlated values, where the sample correlation of the output approximates the input matrix

#### Scenario: Identity matrix produces independent values
- **WHEN** the correlation matrix is identity (all off-diagonals = 0)
- **THEN** the generated values are independent — statistically equivalent to calling each simulator's native random function separately per parameter

#### Scenario: Fully correlated parameters move together
- **WHEN** the off-diagonal entry between n1_vth0 and p1_vth0 is 1.0
- **THEN** their generated values across runs have a Spearman correlation of approximately 1.0

#### Scenario: Deterministic output given a seed
- **WHEN** the user provides the same seed and correlation matrix
- **THEN** the system produces identical output values, enabling reproducible simulations

### Requirement: Multi-format output

The system SHALL output generated parameter values in three formats: ngspice `.control` script, simulator-agnostic CSV, and `.param` snippet. The system SHALL NOT execute simulations — pqwave generates input values only.

#### Scenario: Generate ngspice .control script
- **WHEN** a user generates an ngspice output targeting K model parameters with nominal values
- **THEN** the system writes a `.control` script containing: `define agauss(...)` distribution wrappers, `let` statements capturing nominals from `@model[param]`, `sgauss(0)` uncorrelated draws multiplied by Cholesky L coefficients, a `dowhile` loop with `altermod` commands, and `write` to save results

#### Scenario: Generate simulator-agnostic CSV
- **WHEN** a user generates CSV output for K parameters and N runs
- **THEN** the system writes a CSV with header row `run,{param1},...,{paramK}` and N data rows, each containing the run index and the correlated parameter values for that run

#### Scenario: Generate .param snippet
- **WHEN** a user generates a `.param` snippet for LTspice or QSPICE
- **THEN** the system writes per-run `.param` lines with baked correlated values that the user can copy into a netlist

#### Scenario: CSV is the recommended format for non-ngspice simulators
- **WHEN** a user targets LTspice or QSPICE
- **THEN** the system recommends CSV output, providing guidance that the user feeds values via external scripting (PyQspice, Python batch, shell loop)

#### Scenario: Tab-separated CSV output
- **WHEN** a user generates CSV output with `delimiter="\t"` (TSV)
- **THEN** the system writes tab-separated values instead of comma-separated, preserving the same header+rows structure

### Requirement: Parameter mapping via auto-populated rows

The system SHALL bridge correlation matrix names to SPICE model parameters by auto-populating parameter rows from the parsed `.model` file. Each row SHALL contain model name, SPICE parameter name, nominal value, and an auto-generated logical name (`{model}_{param}`). The logical name MAY be user-editable. This single-row structure IS the mapping — no separate mapping step or dialog is required.

#### Scenario: Auto-populated row provides complete mapping
- **WHEN** `.model n1 nmos vth0=0.6322` is parsed
- **THEN** the row `{model: n1, param: vth0, nominal: 0.6322, logical_name: n1_vth0}` captures all information needed for both correlation matrix labeling and script generation

#### Scenario: User renames a logical name
- **WHEN** a user renames `n1_vth0` to `vth_nmos`
- **THEN** the correlation matrix label updates, and the generated script still correctly references `@n1[vth0]`

### Requirement: Correlation REPL/API commands

The system SHALL provide `mc_correlation_load`, `mc_correlation_show`, `mc_correlation_edit`, and `mc_generate` commands via the REPL/API, following the existing `@api_command` registration pattern.

#### Scenario: Load correlation matrix via REPL
- **WHEN** a user executes `mc_correlation_load("correlation.csv")` in the REPL
- **THEN** the system parses the file, stores the matrix on the active MC collection, and prints a summary (N×N matrix with parameter names)

#### Scenario: Generate values via REPL
- **WHEN** a user executes `mc_generate("output", format="csv", runs=100)` in the REPL with an active correlation matrix and parameter annotations
- **THEN** the system writes `output.csv` with 100 rows of correlated parameter values

#### Scenario: Generate without a loaded correlation matrix
- **WHEN** a user executes `mc_generate(...)` but no correlation matrix is loaded
- **THEN** the system returns an error indicating that a correlation matrix must be loaded or created first
