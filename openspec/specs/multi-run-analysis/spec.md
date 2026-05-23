## ADDED Requirements

### Requirement: Cross-run statistics

The system SHALL compute per-timepoint statistics across all runs (or filtered subset) for a given signal group. Statistics SHALL include mean, standard deviation, minimum, and maximum at each time or frequency point. Results SHALL be returned as numpy arrays suitable for rendering as envelope traces.

#### Scenario: Compute statistics across all runs
- **WHEN** a user executes `mc_stats("v(out)")` on a 21-run MC collection
- **THEN** the system returns `{mean: array, std: array, min: array, max: array}` with one value per timepoint, computed across all 21 runs

#### Scenario: Statistics respect run filter
- **WHEN** run filter is set to `[0, 1, 2]` and user executes `mc_stats("v(out)")`
- **THEN** statistics are computed across runs 0, 1, and 2 only

### Requirement: Scalar measurement histogram across runs

The system SHALL evaluate a measurement expression (e.g., `max(V(out))`, `rms(I(R1))`) on each run individually and plot the resulting scalar values as a histogram. The histogram SHALL use the existing `compute_histogram` analysis function.

#### Scenario: Histogram of max values
- **WHEN** a user executes `mc_histogram("max(v(out))")` on a 30-run MC collection
- **THEN** the system evaluates `max(v(out))` for each run, producing 30 scalar values, and renders a histogram of those values

#### Scenario: Histogram with custom bins
- **WHEN** a user executes `mc_histogram("max(v(out))", bins=50, range=(400M, 500M))`
- **THEN** the histogram uses 50 bins over the specified frequency range

### Requirement: Yield analysis

The system SHALL compute the percentage of runs that satisfy a user-specified condition at each time or frequency point. The condition SHALL support comparison operators against a scalar threshold. The result SHALL be a per-point yield percentage.

#### Scenario: Yield against upper and lower limits
- **WHEN** a user executes `mc_yield("v(out)", low=-3.0, high=3.0)`
- **THEN** the system returns a per-timepoint array of yield percentages: the fraction of runs where v(out) is within [-3.0, 3.0] at each point

#### Scenario: Yield with measurement condition
- **WHEN** a user executes `mc_yield("v(out)", low=-3.0, high=3.0, condition="max")`
- **THEN** the system computes `max(v(out))` per run, counts how many runs have max within [-3.0, 3.0], and returns a single yield percentage

### Requirement: Scatter plot of measurement vs parameter

The system SHALL produce a scatter plot of a scalar measurement value vs a parameter value, with one point per run. The scatter plot SHALL be rendered using the existing histogram panel pattern (new panel with PlotDataItem).

#### Scenario: Scatter measurement vs parameter
- **WHEN** a user executes `mc_scatter("max(v(out))", "C1")` and runs are annotated with C1 parameter values
- **THEN** the system plots one point per run: C1 value on X axis, max(v(out)) on Y axis

#### Scenario: Scatter requires parameter annotation
- **WHEN** a user executes `mc_scatter("max(v(out))", "C1")` but no C1 parameter values are annotated
- **THEN** the system returns an error indicating that parameter "C1" has no data

### Requirement: Worst-case extraction

The system SHALL identify and return the N runs with the largest deviation from the nominal run, measured by a user-specified metric (max absolute difference, RMS difference, or peak difference at a specific X value).

#### Scenario: Worst-case by max deviation
- **WHEN** a user executes `mc_worst(5)` with metric "max_abs_diff" on the active signal group
- **THEN** the system returns the 5 run indices with the largest maximum absolute difference from the nominal run

#### Scenario: Worst-case returns enough context to display
- **WHEN** `mc_worst(3)` is executed
- **THEN** the returned data includes run indices, deviation values, and parameter values for each worst-case run

### Requirement: Sensitivity ranking

The system SHALL rank parameters by their impact on a scalar measurement, using Spearman or Pearson correlation between each parameter's values across runs and the measurement values across runs. The result SHALL list parameters in descending order of absolute correlation coefficient.

#### Scenario: Sensitivity ranking by correlation
- **WHEN** a user executes `mc_sensitivity("max(v(out))")` with parameters C1, L1, C2, L2, L3, C3 annotated
- **THEN** the system returns parameters ranked by |correlation coefficient| with the measurement, e.g., `[{param: "C3", r: 0.87}, {param: "L3", r: -0.62}, ...]`

#### Scenario: Sensitivity requires parameter annotation
- **WHEN** a user executes `mc_sensitivity("max(v(out))")` but no parameters are annotated
- **THEN** the system returns an error indicating that parameter metadata is required

### Requirement: REPL commands for multi-run analysis

The system SHALL provide `mc_stats`, `mc_histogram`, `mc_yield`, `mc_scatter`, `mc_worst`, and `mc_sensitivity` commands via the REPL/API, following the existing `@api_command` registration pattern.

#### Scenario: All analysis commands accessible from REPL
- **WHEN** a user types `mc_` in the REPL and presses tab
- **THEN** the system shows all available MC analysis commands in the autocomplete list
