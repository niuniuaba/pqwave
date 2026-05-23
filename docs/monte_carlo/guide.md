# Monte Carlo Analysis User Guide

pqwave supports comprehensive Monte Carlo (MC) analysis for ngspice, LTspice, and QSPICE simulation output. This guide has two parts: a **feature reference** for quick lookup, and **worked tutorials** that walk through real analysis workflows using the example files in `docs/monte_carlo/examples/`.

> All example files are pre-computed. Open them directly — no simulator required.

## Table of Contents

### Part 1 — Feature Reference
- [Loading Modes](#loading-modes)
- [Display Modes & Control Bar](#display-modes-control-bar)
- [Statistical Analysis](#statistical-analysis-features)
- [Correlation Tools](#correlation-tools)
- [Session API Commands](#session-api-commands)

### Part 2 — Worked Tutorials
- [Example Overview](#example-overview)
- [Example 1: RC Low-Pass Filter](#example-1-rc-low-pass-filter)
- [Example 2: Ring Oscillator](#example-2-ring-oscillator)
- [Example 3: Correlation Matrix Editor](#example-3-correlation-matrix-editor)
- [Example 4: LTspice LC Bandpass Filter](#example-4-ltspice-lc-bandpass-filter)
- [Standalone Scripting Example](#standalone-scripting-example)

---

## Part 1 — Feature Reference

### Loading Modes

Open via **File > Open Monte Carlo**. Three source types are available:

| Mode | Source | Description | API Command |
|------|--------|-------------|-------------|
| Single stepped file | `.step param` simulations (LTspice, QSPICE) | Each step = one MC run. Parameter names and values auto-detected from raw file header. | `mc_load(path, source_type="stepped")` |
| Multiple files | Two or more single-run raw files | Each file = one MC run. Use for batch simulations that save per-run output files. | `mc_load([path1, path2, ...], source_type="multi")` |
| Single file with named runs | Raw files with run-named vectors (vout0, vout1, ...) | Common in ngspice `.control` loop simulations. Enter base name and optional run count. | `mc_load(path, source_type="pattern", grouping_pattern="vout")` |

**After loading**, the MC Control Bar appears at the top of the main window showing the run count and display controls. All panels receive MC rendering.

### Display Modes & Control Bar

The MC Control Bar appears after loading MC data:

| Control | Values | Description | API Command |
|---------|--------|-------------|-------------|
| Run count | Read-only | Shows total loaded runs, e.g. "MC: 21 runs" | `mc_info()` |
| Display mode | `spaghetti`, `envelope`, `single` | How all runs are rendered | `mc_style(mode)` |
| Sigma (σ) | 0.5–6.0 (default 3.0) | Envelope band width in standard deviations | `mc_style(mode, sigma=N)` |
| Nominal | 0 to N−1 (default 0) | Index of the reference run | `mc_nominal(idx)` |
| Run filter | "all" or comma-separated indices | Subset of runs to display, e.g. `0, 5, 10` | `mc_filter("all")` / `mc_filter([0,5,10])` |

**Display modes:**

| Mode | Behavior |
|------|----------|
| **Spaghetti** | All active runs plotted as individual translucent traces. Density patterns reveal outliers. |
| **Envelope** | Nominal run as solid line + shaded bands at ±1σ, ±2σ, ±3σ around the cross-run mean. |
| **Single** | Only the nominal run. Use to focus on the reference waveform. |

### Statistical Analysis Features

All commands in **Analyze** menu. Require an active MC collection.

| Feature | Menu Path | Purpose | API Command |
|---------|-----------|---------|-------------|
| MC Statistics | Analyze > MC Statistics | Per-timepoint mean, std, min, max across all runs. Plotted as additional traces. | `mc_stats(signal)` |
| MC Histogram | Analyze > MC Histogram | Histogram of a scalar measurement across runs. Choose measurement function (max, min, mean, rms, pk_pk) and bin count. | `mc_histogram("max(v(out))", bins=50)` |
| MC Yield | Analyze > MC Yield | Percentage of runs within spec limits. Optional measurement function for scalar yield. | `mc_yield(signal, low, high, condition=None)` |
| Worst Cases | Analyze > Worst Cases | Top N runs with largest deviation from nominal. Metrics: max_abs_diff or rms_diff. | `mc_worst(n=5, metric="max_abs_diff")` |
| MC Sensitivity | Analyze > MC Sensitivity | Ranks parameters by Spearman correlation with a measurement. Requires parameter-annotated runs. | `mc_sensitivity("max(v(out))")` |
| MC Scatter | Analyze > MC Scatter | Scatter plot of measurement vs parameter across runs. Requires parameter-annotated runs. | `mc_scatter("max(v(out))", "Rval")` |

**Measurement functions** (used in histogram, yield, sensitivity, scatter):

| Function | Computes |
|----------|----------|
| `max` | Maximum value of the signal in each run |
| `min` | Minimum value of the signal in each run |
| `mean` | Mean value of the signal in each run |
| `rms` | RMS (root mean square) of the signal in each run |
| `pk_pk` | Peak-to-peak (max − min) of the signal in each run |

**Parameter annotation:** For simulations that don't embed parameter values (ngspice loops), annotate manually:

```
mc_param("Rval", [10000, 1000, 2200, ...])
mc_param("Cval", [10e-9, 10e-9, 1e-9, ...])
```

Companion CSV files (like `rc_filter_params.csv`) list parameter values per run.

### Correlation Tools

**Analyze > MC Correlation** opens the Correlation Matrix Editor — a three-step tool for designing correlated parameter variations.

| Step | Action | Description |
|------|--------|-------------|
| 1. Load Model File | Browse and Parse a `.model` or `.lib` file | Extracts parameter names and nominal values from SPICE `.model` statements. Format: `modelname_paramname`. |
| 2. Correlation Matrix | Edit the matrix table or import/export CSV | Square matrix with 1.0 on diagonal. Upper-triangle cells editable (−1.0 to 1.0). Mirrored to lower triangle. Matrix must be positive definite. |
| 3. Generate Output | Configure runs, seed, format, and output path | Generates correlated parameter sets via Cholesky decomposition. |

**Output formats:**

| Format | Description |
|--------|-------------|
| CSV | `run, param1, param2, ...` — simulator-agnostic |
| TSV | Tab-separated variant of CSV |
| ngspice .control | Complete `.control` script with `altermod` assignments and simulation loop |
| .param snippet | Per-run `.param` lines with baked values |

**Under the hood:** The correlation matrix *R* is decomposed via Cholesky (*R = L × L^T*). Independent standard normals *Z* are multiplied by *L^T* to produce correlated normals *Zc*. Final values = nominal + sigma × *Zc*.

API commands: `mc_correlation_load(path)`, `mc_correlation_show()`, `mc_generate(output_path, format, runs, seed)`.

### Session API Commands

All MC commands available headlessly via `SessionAPI` (REPL: `F6`, batch scripts, external automation).

**Loading & Inspection:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `mc_load` | `mc_load(source, source_type="stepped", grouping_pattern=None)` | Load MC data. Returns `{"status": "ok", "runs": N}`. |
| `mc_info` | `mc_info()` | Current collection state: runs, nominal, mode, sigma, parameters, filter. |

**Display Control:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `mc_style` | `mc_style(mode, sigma=3.0)` | Set mode: "spaghetti", "envelope", or "single". |
| `mc_nominal` | `mc_nominal(idx)` | Set nominal run index. |
| `mc_filter` | `mc_filter(runs)` | `"all"` or `[0, 2, 5]` to show subset. |

**Parameter Annotation & Grouping:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `mc_param` | `mc_param(name, values)` | Annotate runs with parameter values. Required for sensitivity/scatter. |
| `mc_group` | `mc_group(signal, pattern=None)` | Register grouping intent for a signal. |
| `mc_ungroup` | `mc_ungroup(signal)` | Clear MC grouping and collection. |

**Statistical Analysis:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `mc_stats` | `mc_stats(signal)` | Cross-run mean, std, min, max per timepoint. |
| `mc_histogram` | `mc_histogram(measurement, bins=50, range=None)` | Histogram of measurement across runs. |
| `mc_yield` | `mc_yield(signal, low, high, condition=None)` | Yield percentage within spec limits. |
| `mc_worst` | `mc_worst(n=5, metric="max_abs_diff")` | Top N worst runs by deviation. |
| `mc_sensitivity` | `mc_sensitivity(measurement)` | Parameter ranking by Spearman correlation. |
| `mc_scatter` | `mc_scatter(measurement, param)` | Scatter data (x=param values, y=measurements). |

**Correlation Matrix:**

| Command | Signature | Description |
|---------|-----------|-------------|
| `mc_correlation_load` | `mc_correlation_load(path)` | Load correlation matrix from CSV. |
| `mc_correlation_show` | `mc_correlation_show()` | Print current correlation matrix as text. |
| `mc_correlation_edit` | `mc_correlation_edit()` | Open Correlation Matrix Editor dialog (GUI only). |
| `mc_generate` | `mc_generate(output_path, output_format="csv", runs=100, seed=None, nominals=None, sigmas=None)` | Generate correlated parameter values to file. |

---

## Part 2 — Worked Tutorials

### Example Overview

Three pre-computed example files live in `docs/monte_carlo/examples/`. Each demonstrates a different loading mode and set of analysis features:

| Example | File | Circuit | Runs | Loading Mode | Demonstrates |
|---------|------|---------|------|-------------|--------------|
| RC Filter | `ngspice/rc_filter_mc.raw` + `rc_filter_params.csv` | RC low-pass (R=1k–100k, C=1n–100n), AC 100 Hz–1 MHz | 21 | Pattern (base: `vout`) | Loading, display, parameter annotation, sensitivity, scatter, yield, worst-case, API scripting |
| Ring Oscillator | `ngspice/MC_ring.raw` | 25-stage CMOS ring oscillator, transient 0–100 ns | 31 | Pattern (base: `vout`) | Envelope display, cross-run statistics, histogram |
| Correlation Editor | `ngspice/mc_ring_circ.net` | BSIM3 NMOS/PMOS model definitions | — | — | Model parsing, correlation matrix editing, Cholesky-based parameter generation |
| LTspice LC Filter | `ltspice/MonteCarlo.raw` | LC bandpass filter, AC 300 kHz–10 MHz | 21 | Stepped | Stepped loading, auto-detected parameters |

**Prerequisites:** pqwave installed. No simulator required — all raw files are pre-computed.

---

### Example 1: RC Low-Pass Filter

This example demonstrates the full MC workflow from loading through sensitivity analysis. The circuit is a simple RC low-pass filter with AC analysis from 100 Hz to 1 MHz. R and C were varied independently across 21 runs, producing a range of cutoff frequencies.

**Input:**
- Raw file: `docs/monte_carlo/examples/ngspice/rc_filter_mc.raw`
- Companion CSV: `docs/monte_carlo/examples/ngspice/rc_filter_params.csv`
- Circuit: V1 → R1 → out → C1 → GND
- Analysis: AC dec 50, 100 Hz – 1 MHz
- Runs: 21 (R × C combinations)

#### Step 1: Load the Data

1. **File > Open Monte Carlo** to open the MC configuration dialog.
2. Select source type: **Single file with named runs**.
3. Click **Browse** and select `docs/monte_carlo/examples/ngspice/rc_filter_mc.raw`.
   - The dialog preview shows: `vout: 21 runs (vout0..vout20)`.
4. Enter base name: **vout**.
5. Click **OK**.

**Expected output:** The MC Control Bar appears: "MC: 21 runs". A frequency response trace appears on the plot — this is vout0 (nominal run, R=10k, C=10n).

> **Or via API:**
> ```python
> api.mc_load(
>     "docs/monte_carlo/examples/ngspice/rc_filter_mc.raw",
>     source_type="pattern",
>     grouping_pattern="vout"
> )
> # Returns: {"status": "ok", "runs": 21}
> ```

#### Step 2: Explore Display Modes

1. In the MC Control Bar, switch the **Display** dropdown to `envelope`.
2. Set **σ** to `3.0` (default).
3. Observe the plot:
   - The solid center line is run 0 (R=10k, C=10n, nominal).
   - Three shaded bands show ±1σ, ±2σ, ±3σ around the cross-run mean.
   - At 100 Hz: all runs are near gain ≈ 1.0 (passband — capacitor is open circuit).
   - At 1 kHz: the envelope widens dramatically — some runs have already rolled off while others are still near unity gain. Mean gain ≈ 0.19, σ ≈ 0.34.
   - At 10 kHz: most runs are in deep roll-off. Mean gain ≈ 0.10, σ ≈ 0.27.
   - At 100 kHz: all runs are near 0 (stopband).
4. Switch to `spaghetti` mode — 21 translucent traces show the full spread of frequency responses.
5. Switch to `single` mode — only the nominal run is visible.
6. Try the **Run filter**: enter `0, 5, 10, 15, 20` to show every 5th run. Enter `all` to restore.

**Expected output:** Envelope mode reveals that the transition band (~500 Hz to ~50 kHz) has the highest run-to-run variability. The passband and stopband have almost none.

> **Or via API:**
> ```python
> api.mc_style("envelope", sigma=3.0)
> api.mc_filter([0, 5, 10, 15, 20])
> api.mc_style("spaghetti")
> api.mc_filter("all")
> ```

#### Step 3: Annotate Parameters

The raw file contains run outputs but not the R and C values that produced them. The companion CSV `rc_filter_params.csv` lists them:

| run | Rval (Ω) | Cval (F) |
|-----|----------|----------|
| 0 | 10000 | 1e-08 |
| 1 | 1000 | 1e-08 |
| 2 | 2200 | 1e-09 |
| ... | ... | ... |
| 20 | 10000 | 2.2e-08 |

R ranges from 1 kΩ to 100 kΩ (two orders of magnitude). C ranges from 1 nF to 100 nF (two orders of magnitude).

1. Open the REPL (**F6**).
2. Run the following commands to annotate each run with its parameter values:

```python
import csv
with open("docs/monte_carlo/examples/ngspice/rc_filter_params.csv") as f:
    runs = list(csv.DictReader(f))
api.mc_param("Rval", [float(r["Rval"]) for r in runs])
api.mc_param("Cval", [float(r["Cval"]) for r in runs])
api.mc_info()
```

3. `mc_info()` now shows `'parameters': ['Rval', 'Cval']`.

**Expected output:** The MC collection is now parameter-annotated. Sensitivity and scatter analysis are unlocked.

> The unitvec-init workaround: ngspice loop simulations don't embed parameter values in the raw file. Companion CSVs bridge this gap. For `.step param` simulations (LTspice, QSPICE), parameters are auto-detected — skip this step.

#### Step 4: Sensitivity Analysis

Which parameter matters more for the maximum output — R or C?

1. **Analyze > MC Sensitivity**.
2. Enter measurement: `max(v(out))`.
3. Click **OK**.

**Expected output (Spearman rank correlation):**

| Parameter | r (correlation) | p-value | Interpretation |
|-----------|----------------|---------|----------------|
| Cval | −0.208 | 0.366 | Weak negative correlation — larger C reduces max output more |
| Rval | −0.042 | 0.858 | Negligible correlation — R has almost no effect on max output |

The maximum output is always ≈1.0 in the passband, so `max(v(out))` doesn't vary much between runs (range: 0.0000–1.0000). For a more informative sensitivity analysis, use a frequency-domain measurement. Try `mc_histogram` at a specific frequency or measure the −3 dB point.

> **Or via API:**
> ```python
> result = api.mc_sensitivity("max(v(out))")
> for entry in result["sensitivity"]:
>     print(f"  {entry['param']}: r={entry['r']:.3f}, p={entry['p']:.3f}")
> ```

#### Step 5: Scatter Plot

Visualize the relationship between Rval and max output:

1. **Analyze > MC Scatter**.
2. Enter measurement: `max(v(out))`.
3. Enter parameter: `Rval`.
4. Click **OK**.

**Expected output:** A scatter plot with 21 points. Rval on x-axis (1 kΩ – 100 kΩ), max(v(out)) on y-axis (0.0–1.0). Most runs cluster near max=1.0 (good filters) with a few outliers near max=0.0 (runs where the cutoff is so low that even the passband is attenuated).

Repeat with parameter `Cval` to see the C vs max output relationship. The scatter plot for Cval shows a similar pattern — only extreme C values (large C, low cutoff) drop the max output.

> **Or via API:**
> ```python
> api.mc_scatter("max(v(out))", "Rval")
> api.mc_scatter("max(v(out))", "Cval")
> ```

#### Step 6: Yield Analysis

What fraction of runs have acceptable DC gain?

1. **Analyze > MC Yield**.
2. Enter signal: `v(out)`.
3. Low limit: `0.99`, High limit: `1.01`.
4. Leave condition blank (per-timepoint yield).
5. Click **OK**.

**Expected output:** Yield ≈ 14%. Only 3 of 21 runs maintain DC gain above 0.99 across all frequencies. Most runs have rolled off significantly even at 100 Hz because their RC time constant is large.

Try with a measurement condition: set condition to `mean`. This computes the mean gain for each run first, then checks if it's within [0.99, 1.01]. The result will be even lower — most runs have a mean gain far below 0.99.

The −3 dB cutoff frequency varies from 100 Hz to 50.1 kHz across runs (mean: 3.3 kHz). Only 5% of runs have their −3 dB point between 1–10 kHz.

> **Or via API:**
> ```python
> y = api.mc_yield("v(out)", low=0.99, high=1.01)
> print(f"Yield: {y['yield_pct']:.0f}%")
> ```

#### Step 7: Worst-Case Identification

Which runs deviate most from the nominal?

1. **Analyze > Worst Cases**.
2. N = `5`, Metric = `max_abs_diff`.
3. Click **OK**.

**Expected output:**

| Rank | Run | Deviation |
|------|-----|-----------|
| 1 | 20 | 0.9980 |
| 2 | 19 | 0.9980 |
| 3 | 17 | 0.9980 |
| 4 | 16 | 0.9980 |
| 5 | 14 | 0.9978 |

Runs 14–20 deviate most from the nominal — their frequency responses differ substantially due to different R/C combinations (some shift the cutoff higher, some lower). The `max_abs_diff` metric captures any deviation regardless of direction.

> **Or via API:**
> ```python
> worst = api.mc_worst(n=5, metric="max_abs_diff")
> for w in worst["worst"]:
>     print(f"  Run {w['run_index']}: deviation={w['deviation']:.4f}")
> ```

---

### Example 2: Ring Oscillator

This example demonstrates MC analysis on transient (time-domain) data. The circuit is a 25-stage CMOS ring oscillator — a chain of inverters that produces a self-sustaining oscillation. BSIM3 model parameters (vth0, u0, tox, lint, wint for both NMOS and PMOS — 10 parameters total) were varied with Gaussian distributions across 31 runs.

**Input:**
- Raw file: `docs/monte_carlo/examples/ngspice/MC_ring.raw`
- Circuit: 25-stage ring oscillator, BSIM3 models, 3.3 V supply
- Analysis: transient, 0–100 ns, 6668 time points
- Runs: 31 (0 = nominal BSIM3 parameters, 1–30 = perturbed)

#### Step 1: Load the Data

1. **File > Open Monte Carlo**.
2. Select source type: **Single file with named runs**.
3. Browse to `docs/monte_carlo/examples/ngspice/MC_ring.raw`.
   - Preview shows: `vout: 31 runs (vout0..vout30)`.
4. Enter base name: **vout**.
5. Click **OK**.

**Expected output:** MC Control Bar: "MC: 31 runs". The plot shows a 3.3 V square-wave-like oscillation at the buffer output.

> **Or via API:**
> ```python
> api.mc_load(
>     "docs/monte_carlo/examples/ngspice/MC_ring.raw",
>     source_type="pattern",
>     grouping_pattern="vout"
> )
> ```

#### Step 2: Envelope Display

1. Switch display mode to **envelope**.
2. Set σ to **3.0**.
3. Zoom in on the oscillation: the envelope bands show how much the waveform varies at each timepoint.
   - At mid-simulation (~50 ns): mean voltage ≈ 2.12 V, σ ≈ 1.12 V.
   - The envelope is widest during transitions (0→3.3 V and 3.3→0 V) — this is where process variation has the largest timing impact.
   - Flat regions (steady 0 V or 3.3 V) have near-zero σ.

**Expected output:** The envelope bands reveal that process variation primarily affects *timing* (jitter), not *amplitude*. The voltage levels are rail-to-rail regardless of parameter perturbations, but the exact moment of each transition shifts run-to-run.

> The ring oscillator raw file has no embedded parameter values (the BSIM3 variations were applied via `altermod` in an ngspice loop). Parameter annotation is possible if you record the parameter values from the simulation log, but is not demonstrated here. See Example 1 for the full parameter-aware workflow.

#### Step 3: Cross-Run Statistics

1. **Analyze > MC Statistics**.
2. Enter signal: `v(out)`.
3. Click **OK**.

**Expected output:** Four new traces appear: mean, std, min, max of v(out) across all 31 runs at each timepoint. The std trace peaks during signal transitions, confirming that timing variation dominates.

#### Step 4: Histogram of Oscillation Amplitude

1. **Analyze > MC Histogram**.
2. Enter measurement: `pk_pk(v(out))` (peak-to-peak amplitude).
3. Bins: `8`.
4. Click **OK**.

**Expected output (histogram of pk-pk amplitude across 31 runs):**

| Bin (V) | Runs | Distribution |
|----------|------|-------------|
| 3.098–3.105 | 1 | █ |
| 3.105–3.112 | 2 | ██ |
| 3.112–3.119 | 7 | ███████ |
| 3.119–3.126 | 5 | █████ |
| 3.126–3.133 | 4 | ████ |
| 3.133–3.139 | 8 | ████████ |
| 3.139–3.146 | 3 | ███ |
| 3.146–3.153 | 1 | █ |

Amplitude ranges from 3.098 V to 3.153 V (mean: 3.126 V). The distribution is roughly bell-shaped, centered around 3.12–3.14 V. This tight spread (±0.9% of mean) indicates the oscillator amplitude is robust to process variation.

> **Or via API:**
> ```python
> api.mc_stats("v(out)")
> result = api.mc_histogram("pk_pk(v(out))", bins=8)
> ```

---

### Example 3: Correlation Matrix Editor

This example demonstrates the correlation tools using the ring oscillator's BSIM3 model file. You will parse a model file, edit a correlation matrix, and generate a correlated parameter set for a new simulation.

**Input:**
- Model file: `docs/monte_carlo/examples/ngspice/mc_ring_circ.net`
- Contains: NMOS and PMOS BSIM3 model definitions with `agauss()` distribution functions

#### Step 1: Open the Correlation Editor

1. **Analyze > MC Correlation** to open the Correlation Matrix Editor.
2. In **Step 1: Load Model File**, click **Browse** and select `docs/monte_carlo/examples/ngspice/mc_ring_circ.net`.
3. Click **Parse**.

**Expected output:** The status label shows "Parsed 6 parameters from 2 model(s)". The matrix table populates with 6 rows and columns:

| Parameter | Description | Nominal |
|-----------|-------------|---------|
| n1_version | NMOS BSIM3 version | 3.3 |
| n1_Level | NMOS BSIM3 level | 8.0 |
| n1_Vth0 | NMOS threshold voltage | 0.6 V |
| p1_version | PMOS BSIM3 version | 3.3 |
| p1_Level | PMOS BSIM3 level | 8.0 |
| p1_Vth0 | PMOS threshold voltage | −0.6 V |

The diagonal cells are fixed at 1.0 (self-correlation). Upper-triangle cells are blank (0.0 = uncorrelated by default).

> The `n1_version` and `n1_Level` (and their PMOS counterparts) are constants in the model file — they don't have `agauss()` wrappers and won't vary. The meaningful parameters for correlation are `n1_Vth0` and `p1_Vth0`.

#### Step 2: Set Up Correlations

Suppose you want the NMOS and PMOS threshold voltages to be **positively correlated** — when NMOS Vth0 shifts higher, PMOS Vth0 shifts correspondingly. This models a global process skew.

1. Find the cell at row `n1_Vth0`, column `p1_Vth0` (upper triangle).
2. Enter **0.7** (moderate positive correlation).
3. Observe: the mirror cell at `p1_Vth0` × `n1_Vth0` (lower triangle) auto-fills with 0.7.

The matrix now has one off-diagonal correlation:

|   | n1_Vth0 | p1_Vth0 |
|---|---------|---------|
| **n1_Vth0** | 1.0 | 0.7 |
| **p1_Vth0** | 0.7 | 1.0 |

> **Import/Export:** Click **Export Matrix (CSV)** to save this matrix for reuse. Click **Load Matrix (CSV)** to import a pre-computed correlation matrix from another project.

#### Step 3: Generate Correlated Output

1. In **Step 3: Generate Output**:
   - **MC Runs:** `30`
   - **Seed:** `12345`
   - **Format:** `csv — simulator-agnostic (recommended for LTspice/QSPICE)`
   - **Output:** Browse to a convenient location, e.g. `mc_correlated.csv`
2. Click **Generate**.
3. Review the preview dialog — it shows the first 5 rows of generated values.
4. Click **OK** to write the file.

**Expected output:** A CSV file with 30 rows (+ header) and columns `run, n1_Vth0, p1_Vth0, n1_version, n1_Level, p1_version, p1_Level`. The Vth0 columns vary with the specified correlation (r ≈ 0.7 across runs), while the version/Level columns stay at their nominal values.

#### Step 4: Try Other Formats

Experiment with the other output formats:

| Format | Use case |
|--------|----------|
| **ngspice .control** | Generates a complete ngspice script with `altermod` commands and a simulation loop. Requires model name annotations (these are auto-extracted from the parsed model file). |
| **.param snippet** | Per-run `.param` lines for inclusion in a SPICE netlist. |
| **TSV** | Tab-separated CSV variant for tools that expect tabs. |

For the ngspice format, enter a simulation command like `tran 15p 200n 0` to include in the generated control script.

> **Under the hood:** The tool computes the Cholesky decomposition *L* of the correlation matrix *R* (where *R = L × L^T*). It generates independent standard normals *Z*, multiplies by *L^T* to produce correlated normals *Zc*, then scales and shifts: *value = nominal + sigma × Zc*. Sigma defaults to 10% of |nominal| for each parameter.

> **Or via API:**
> ```python
> api.mc_correlation_load("correlation.csv")
> api.mc_generate("mc_correlated.csv", output_format="csv", runs=30, seed=12345)
> api.mc_correlation_show()
> ```

---

### Example 4: LTspice LC Bandpass Filter

This example demonstrates **stepped loading** — the simplest MC loading mode. The raw file was produced by an LTspice simulation with `.step param X 0 20 1`.

**Input:**
- Raw file: `docs/monte_carlo/examples/ltspice/MonteCarlo.raw`
- Circuit: LC bandpass filter (L1, L2, L3, C1, C2, C3) with `mc(val, tol)` random component variation
- Analysis: AC oct 100, 300 kHz – 10 MHz
- Steps: 21

#### Step 1: Load as Stepped File

1. **File > Open Monte Carlo**.
2. Select source type: **Single stepped file**.
3. Browse to `docs/monte_carlo/examples/ltspice/MonteCarlo.raw`.
4. Click **OK**.

**Expected output:** MC Control Bar: "MC: 21 runs". Parameter `x` is auto-detected (values: 0, 1, 2, ..., 20).

> The parameter `x` is a dummy run counter — not a real circuit parameter. LTspice uses `.step param X 0 20 1` to cycle through Monte Carlo iterations because `.step` is the only way to produce multi-run output. The actual component variations happen inside `mc(val, tol)` function calls which are not recorded as parameters. Real stepped simulations (e.g., `.step param R 1k 10k 500`) embed meaningful parameter names that pqwave auto-detects.

#### Step 2: When to Use Each Loading Mode

This example highlights when each loading mode is appropriate:

- **Stepped loading** (used here): Best for `.step param` simulations from LTspice and QSPICE. Parameters and run count are auto-detected — no manual configuration.
- **Pattern loading**: Best for ngspice `.control` loop simulations where outputs are named `vout0..voutN`. LTspice raw files use a different internal structure and won't detect run groups in pattern mode.
- **Multi-file loading**: Best when each run is saved to a separate raw file (e.g., batch simulations).

#### Step 3: Explore

1. Switch display to **envelope** mode (σ=3.0).
2. Observe the bandpass response variation across 21 runs.
3. Run **Analyze > MC Statistics** to see the per-frequency mean and std.

**Key takeaway:** Stepped loading is the preferred mode for LTspice and QSPICE files — it auto-detects both the run count and parameter names without manual configuration.

> **Or via API:**
> ```python
> api.mc_load(
>     "docs/monte_carlo/examples/ltspice/MonteCarlo.raw",
>     source_type="stepped"
> )
> api.mc_style("envelope", sigma=3.0)
> api.mc_stats("v(out)")
> ```

---

### Standalone Scripting Example

This complete script loads the RC filter data, annotates parameters, and runs a full sensitivity + yield analysis — all copy-paste runnable:

```python
"""Complete MC analysis of the RC filter example — headless/scripting mode."""
from pqwave.session.api import SessionAPI
import csv

api = SessionAPI()

# ── Load ────────────────────────────────────────────
print("Loading RC filter MC data...")
result = api.mc_load(
    "docs/monte_carlo/examples/ngspice/rc_filter_mc.raw",
    source_type="pattern",
    grouping_pattern="vout"
)
print(f"  Loaded {result['runs']} runs")

# ── Annotate Parameters ─────────────────────────────
with open("docs/monte_carlo/examples/ngspice/rc_filter_params.csv") as f:
    runs = list(csv.DictReader(f))

api.mc_param("Rval", [float(r["Rval"]) for r in runs])
api.mc_param("Cval", [float(r["Cval"]) for r in runs])

info = api.mc_info()
print(f"  Parameters: {info['parameters']}")
print(f"  Display mode: {info['display_mode']}")

# ── Sensitivity ─────────────────────────────────────
print("\nSensitivity: max(v(out)) vs parameters...")
result = api.mc_sensitivity("max(v(out))")
for entry in result["sensitivity"]:
    direction = "↑" if entry["r"] > 0 else "↓"
    print(f"  {entry['param']}: r={entry['r']:+.3f} {direction}  p={entry['p']:.3f}")

# ── Yield ───────────────────────────────────────────
y = api.mc_yield("v(out)", low=0.99, high=1.01)
print(f"\nYield (DC gain in [0.99, 1.01]): {y['yield_pct']:.0f}%")

# ── Worst Cases ─────────────────────────────────────
print("\nWorst 5 runs (max_abs_diff from nominal):")
worst = api.mc_worst(n=5)
for w in worst["worst"]:
    print(f"  Run {w['run_index']:>2}: deviation = {w['deviation']:.4f}")

# ── Cross-Run Stats ─────────────────────────────────
stats = api.mc_stats("v(out)")
print(f"\nCross-run stats at DC (100 Hz):")
print(f"  mean = {stats['mean'][0]:.4f}")
print(f"  std  = {stats['std'][0]:.4f}")
print(f"  min  = {stats['min'][0]:.4f}")
print(f"  max  = {stats['max'][0]:.4f}")
print("\nDone.")
```

**Expected output:**
```
Loading RC filter MC data...
  Loaded 21 runs
  Parameters: ['Rval', 'Cval']
  Display mode: spaghetti

Sensitivity: max(v(out)) vs parameters...
  Cval: r=-0.208 ↓  p=0.366
  Rval: r=-0.042 ↓  p=0.858

Yield (DC gain in [0.99, 1.01]): 14%

Worst 5 runs (max_abs_diff from nominal):
  Run 20: deviation = 0.9980
  Run 19: deviation = 0.9980
  Run 17: deviation = 0.9980
  Run 16: deviation = 0.9980
  Run 14: deviation = 0.9978

Cross-run stats at DC (100 Hz):
  mean = 0.3154
  std  = 0.4586
  min  = 0.0000
  max  = 1.0000

Done.
```
