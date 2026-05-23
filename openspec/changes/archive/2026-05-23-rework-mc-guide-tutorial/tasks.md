## 1. Write Part 1 — Feature Reference

- [x] 1.1 Write loading modes reference — compact table of the three source types (stepped, multi-file, pattern) with descriptions, menu paths, and API signatures
- [x] 1.2 Write display and control bar reference — table of display modes (spaghetti, envelope, single), control bar controls (sigma, nominal, filter), and associated `mc_style`, `mc_nominal`, `mc_filter` commands
- [x] 1.3 Write analysis features reference — table of all statistical analysis tools (stats, histogram, yield, worst-case, sensitivity, scatter) with menu paths, purpose, and API signatures
- [x] 1.4 Write correlation tools reference — describe the three-step workflow and output formats with a compact table
- [x] 1.5 Write session API command reference — table of all 17 `mc_*` commands with signature and one-line description

## 2. Write Part 2 — Worked Tutorials

- [x] 2.1 Write introduction and example overview — describe the three example files, what circuits they represent, what MC features each demonstrates, and prerequisites
- [x] 2.2 Write Example 1: RC filter tutorial — loading in pattern mode, exploring display modes, annotating parameters from CSV, sensitivity analysis, scatter plot, yield analysis, worst-case identification; each step with Input/Steps/Expected Output and real numbers, plus inline "or via API" code blocks
- [x] 2.3 Write Example 2: Ring oscillator tutorial — loading MC_ring.raw in pattern mode, envelope display with sigma control, cross-run statistics, histogram of peak-to-peak amplitudes (expected range: 3.10–3.15 V); note absence of parameter annotations and how that limits sensitivity/scatter
- [x] 2.4 Write Example 3: LTspice LC filter tutorial — loading MonteCarlo.raw as stepped, observing auto-detected step count and parameter `x`; contrast with pattern loading
- [x] 2.5 Write standalone scripting example — complete copy-paste runnable script that loads RC filter data, annotates parameters, runs sensitivity, and prints results

## 3. Verify

- [x] 3.1 Verify all example file paths resolve correctly relative to the project root
- [x] 3.2 Cross-check all quoted numbers (gain values, frequencies, correlation coefficients, yield percentages) against the actual raw file data
- [x] 3.3 Verify the rewritten guide renders correctly — open via Help > Monte Carlo Guide and confirm all sections, tables, and code blocks display properly
