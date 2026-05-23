## ADDED Requirements

### Requirement: Correlation matrix management

The system SHALL support loading, editing, and storing square correlation matrices where rows and columns are labeled with parameter names. Each entry SHALL be a float in [-1, 1] with diagonal forced to 1.0 and symmetry enforced. The `CorrelationMatrix` data model (already implemented) provides the storage representation.

#### Scenario: Load correlation matrix from structured file
- **WHEN** a user loads a CSV or JSON file containing a correlation matrix with labeled rows/columns
- **THEN** the system parses the matrix, validates symmetry and diagonal=1, and stores it on the MC collection

#### Scenario: Edit correlation matrix interactively
- **WHEN** a user opens the Correlation Matrix Editor dialog
- **THEN** the system presents an N×N editable grid with parameter names as row/column headers, diagonal locked to 1.0, and lower triangle mirrored to upper triangle on edit

#### Scenario: Correlation matrix auto-sizing from parameter selection
- **WHEN** a user selects K parameters to vary (e.g., via checkboxes from the .model file parse)
- **THEN** the matrix editor resizes to K×K, preserving any existing values for parameters that remain selected

#### Scenario: Export correlation matrix
- **WHEN** a user exports the matrix
- **THEN** the system writes a CSV or JSON file with parameter labels

### Requirement: Model file parsing for statistical parameters

The system SHALL parse SPICE `.model` statements to extract model names, parameter names, and nominal values. Parsed parameters SHALL be presented as candidates for variation, with auto-generated logical names of the form `{model}_{param}` (e.g., `n1_vth0`).

#### Scenario: Parse BSIM3/BSIM4 model cards
- **WHEN** a user loads a model file containing `.model n1 nmos level=8 vth0=0.6322 u0=388.32 tox=9e-09`
- **THEN** the system extracts model name `n1`, parameter names `vth0`, `u0`, `tox`, and their nominal values `0.6322`, `388.32`, `9e-09`

#### Scenario: Parse multiple models in one file
- **WHEN** a user loads a model file with both `.model n1 nmos ...` and `.model p1 pmos ...`
- **THEN** the system extracts parameters from both models, disambiguating by model name prefix

#### Scenario: Handle agauss/gauss nominal values
- **WHEN** a model file uses `vth0=agauss(0.6, 0.1, 3)`
- **THEN** the system extracts the nominal value `0.6` (the first argument), not the full function call

#### Scenario: Model file with no statistical parameters
- **WHEN** a user loads a model file containing only fixed-value parameters (no variation intent)
- **THEN** the system presents all extracted parameters as available; the user decides which to vary

### Requirement: Cholesky decomposition for correlated value generation

The system SHALL compute the Cholesky decomposition L of the correlation matrix R (R = L·Lᵀ) using `numpy.linalg.cholesky`. For each run, the system SHALL generate an uncorrelated standard normal vector Z (via `sgauss(0)` semantics) and produce the correlated vector Zc = L·Z. The correlated values SHALL be mapped to physical parameter values via Zc·σₚ + μₚ where μₚ and σₚ are the nominal and absolute variation of parameter p.

#### Scenario: Generate correlated values for 3 parameters, 100 runs
- **WHEN** a user generates values with a 3×3 correlation matrix (params: n1_vth0, n1_u0, p1_vth0) and requests 100 runs
- **THEN** the system outputs 100 rows, each with 3 correlated values, where the sample correlation of the output approximates the input matrix

#### Scenario: Identity correlation matrix produces independent values
- **WHEN** the correlation matrix is identity (all off-diagonals = 0)
- **THEN** the generated values are independent — equivalent to calling `agauss(nom, abs_var, sigma)` separately per parameter

#### Scenario: Fully correlated parameters move together
- **WHEN** the off-diagonal entry between n1_vth0 and p1_vth0 is 1.0
- **THEN** their generated values across runs have a Spearman correlation of approximately 1.0

### Requirement: Multi-format output

The system SHALL output generated parameter values in three formats. The system SHALL NOT execute simulations — pqwave is a viewer and value generator, not a simulator runner.

#### Scenario: Generate ngspice .control script
- **WHEN** a user generates an ngspice output targeting model parameters with nominal values
- **THEN** the system writes a `.control` script containing: distribution function definitions (`define agauss(...)`), nominal value capture (`let n1vth0=@n1[vth0]`), a `dowhile` loop applying `altermod` with Cholesky-derived correlated expressions, a simulation command placeholder (`tran` or `ac`), and a `write` command to save results

#### Scenario: Generate simulator-agnostic CSV
- **WHEN** a user generates CSV output for K parameters and N runs
- **THEN** the system writes a CSV with header row `run,{param1},{param2},...,{paramK}` and N data rows, each containing the run index and the correlated parameter values for that run

#### Scenario: Generate .param snippet
- **WHEN** a user generates a `.param` snippet for LTspice or QSPICE
- **THEN** the system writes per-run `.param` lines that the user can copy into their netlist, e.g., `.param n1_vth0=0.6382 n1_u0=375.1 p1_vth0=-0.681`

#### Scenario: Generated values are deterministic given a seed
- **WHEN** the user provides the same seed and correlation matrix
- **THEN** the system produces identical output values, enabling reproducible simulations

### Requirement: Parameter mapping via auto-populated rows

The system SHALL bridge correlation matrix names to SPICE model parameters by auto-populating parameter rows from the parsed `.model` file. Each row SHALL contain: model name, SPICE parameter name, nominal value, and an auto-generated logical name (`{model}_{param}`). The logical name MAY be user-editable. This single-row structure IS the mapping — no separate mapping step or dialog is required.

#### Scenario: Auto-populated row provides complete mapping
- **WHEN** a `.model n1 nmos vth0=0.6322` is parsed
- **THEN** the row `{model: n1, param: vth0, nominal: 0.6322, logical: n1_vth0}` captures all information needed for both correlation matrix labeling and script generation

#### Scenario: User renames a logical name
- **WHEN** a user renames `n1_vth0` to `vth_nmos`
- **THEN** the correlation matrix label updates, and the generated script still correctly references `@n1[vth0]`

### Requirement: Correlation API commands

The system SHALL provide `mc_correlation_load`, `mc_correlation_show`, `mc_correlation_edit`, and `mc_generate` commands via the REPL/API, following the existing `@api_command` registration pattern.

#### Scenario: Load correlation matrix via REPL
- **WHEN** a user executes `mc_correlation_load("correlation.csv")` in the REPL
- **THEN** the system parses the file, stores the matrix on the active MC collection, and prints a summary (N×N matrix with parameter names)

#### Scenario: Generate values via REPL
- **WHEN** a user executes `mc_generate("output", format="csv", runs=100)` in the REPL with an active correlation matrix
- **THEN** the system writes `output.csv` with 100 rows of correlated parameter values

#### Scenario: Generate without a loaded correlation matrix
- **WHEN** a user executes `mc_generate(...)` but no correlation matrix is loaded
- **THEN** the system returns an error indicating that a correlation matrix must be loaded first
