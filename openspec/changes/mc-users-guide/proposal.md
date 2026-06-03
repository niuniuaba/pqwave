## Why

pqwave's Monte Carlo analysis is the most feature-rich part of the application — spanning multi-format data loading, statistical analysis (yield, sensitivity, worst-case), and a unique correlation matrix editor with Cholesky-based parameter generation. Yet there is no user-facing documentation beyond raw simulator reference pages and scattered plan notes. Users discover MC features by accident, if at all. A comprehensive guide lowers the barrier to entry, demonstrates pqwave's unique value compared to other waveform viewers, and gives the Help menu real content.

## What Changes

- Write `docs/monte_carlo/guide.md` — a comprehensive user's guide covering the full MC workflow: loading data, navigating display modes, running statistical analyses, using the correlation editor, and understanding output formats.
- Add a "Monte Carlo Guide" action to the Help menu that opens the guide.
- The guide is read-only rendered content (Markdown shown in a QTextBrowser dialog), matching the existing Help menu pattern.

## Capabilities

### New Capabilities

- `monte-carlo-user-guide`: A comprehensive Markdown document covering all MC features — loading, display modes, statistical analysis (cross-run stats, yield, worst-case, sensitivity, histogram, scatter), and correlation matrix tools (model parsing, Cholesky decomposition, output formats). Plus a Help menu entry to open it.

### Modified Capabilities

<!-- None — this is purely additive documentation. No existing spec requirements change. -->

## Impact

- New file: `docs/monte_carlo/guide.md` (~10-15 KB of documentation)
- Modified: `pqwave/ui/menu_manager.py` — add Help menu action
- Modified: `pqwave/ui/main_window.py` — wire the action callback to open the guide
