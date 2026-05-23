## Why

The current `docs/monte_carlo/guide.md` is a feature reference — it lists capabilities and API signatures but doesn't show users how to actually perform an analysis. A user opening the guide has no clear path from "I have simulation data" to "I understand which components matter most." The example files in `docs/monte_carlo/examples/` are real, pre-computed, and cover all three loading modes — they should drive the narrative.

## What Changes

- Rewrite `docs/monte_carlo/guide.md` in two parts:
  - **Part 1 — Feature Reference**: Concise descriptions of all MC features (loading modes, display modes, control bar, statistical analyses, correlation tools, session API). Each feature is described in a compact table/section with its purpose, menu location, and API command signature.
  - **Part 2 — Worked Tutorials**: Concrete step-by-step workflows using the three real example files. Each follows the **Input → Steps → Expected Output** pattern with real numbers from the examples.
- The three examples anchor the tutorials:
  - **RC filter** (`rc_filter_mc.raw` + `rc_filter_params.csv`) — loading, display modes, parameter annotation, sensitivity, scatter, yield, worst-case, API scripting
  - **MC ring oscillator** (`MC_ring.raw`) — pattern loading, envelope display, cross-run statistics, histogram
  - **LTspice LC filter** (`MonteCarlo.raw`) — stepped loading, auto-detected parameters
- The feature reference includes a compact session API command table; tutorials include API snippets inline as "or via API:" code blocks alongside GUI steps.
- Update the Help menu callback if the guide filename or structure changes.

## Capabilities

### New Capabilities

- `mc-tutorial-guide`: A tutorial-driven Monte Carlo user guide that walks users through concrete analysis workflows using the provided example files. Each workflow specifies the input file, step-by-step actions (GUI and API), and the expected output with real numbers from the examples.

### Modified Capabilities

- `monte-carlo-user-guide`: The existing guide document is replaced entirely by the new tutorial-driven version. The Help menu entry and wiring remain the same; only the content changes.

## Impact

- Rewritten: `docs/monte_carlo/guide.md`
- Unchanged: `pqwave/ui/menu_manager.py`, `pqwave/ui/main_window.py` (same Help menu entry, same callback — just points to the rewritten file)
- Unchanged: all example files in `docs/monte_carlo/examples/`
