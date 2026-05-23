## Context

The current `docs/monte_carlo/guide.md` (333 lines, ~12 KB) is organized as a feature reference: five sections each listing capabilities with parameter tables and API signatures. It documents what exists but doesn't teach how to use it.

The `docs/monte_carlo/examples/` directory contains three real MC datasets ready to load:
- `ngspice/rc_filter_mc.raw` + `rc_filter_params.csv` — 21-run AC analysis of an RC low-pass filter
- `ngspice/MC_ring.raw` — 31-run transient simulation of a 25-stage ring oscillator
- `ltspice/MonteCarlo.raw` — 21-step AC analysis of an LC bandpass filter

These cover all three loading modes (pattern, stepped) and provide real data for every analysis feature.

## Goals / Non-Goals

**Goals:**
- Rewrite `docs/monte_carlo/guide.md` in two parts: a compact feature reference followed by three worked tutorials
- Feature reference gives users a quick lookup of all MC capabilities with menu paths and API signatures
- Tutorials provide concrete, numbered steps anchored to specific example files
- Each tutorial step shows: exact input (file path, menu item, dialog value), action description, expected output (real numbers, described plot appearance)
- API equivalents shown inline as "or via API:" code blocks within tutorial sections

**Non-Goals:**
- Adding new example files
- Changing any code or menu wiring
- Interactive elements (the guide remains static Markdown)
- Screenshots (described plots suffice; screenshots rot faster than text)

## Decisions

1. **Structure: Feature Reference → Worked Tutorials**
   - Part 1 — tables of loading modes, display modes, control bar controls, analysis features, API commands (compact, skimmable)
   - Part 2 — three worked examples using real files, following Input → Steps → Expected Output
   - Rationale: users who know what they need can jump to the reference; new users can follow the tutorials linearly

2. **Input → Steps → Output pattern for every tutorial section**
   - Each workflow is a self-contained recipe users can copy-paste-follow
   - Real numbers extracted from the actual raw files (e.g., "DC gain mean = 0.315, std = 0.459", "worst run 20: deviation = 0.998")
   - Rationale: users trust concrete results more than abstract descriptions

4. **Markdown only, rendered in QTextBrowser**
   - Same delivery mechanism as before (no code changes needed)
   - Tables, code blocks, and structured text — no images
   - Rationale: QTextBrowser handles basic Markdown; avoiding images keeps the guide maintainable

## Risks / Trade-offs

- **Guide length** — three worked examples may produce a longer file than the current 333 lines → Use clear headings and a table of contents; users can jump to specific examples
- **Parameter-data gap for ring oscillator** — MC_ring.raw has no embedded parameter values → Acknowledge this in the guide, show that some analyses require parameter annotation which the RC filter example already demonstrates
- **LTspice step parameter is a dummy counter** — `x` (0..20) is not a real circuit parameter → Note this honestly; the value of Example 3 is demonstrating the stepped loading flow, not the parameter content
