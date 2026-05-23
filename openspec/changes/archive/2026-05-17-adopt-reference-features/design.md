## Context

pqwave currently loads AC analysis data (complex-valued vectors with magnitude/phase or real/imag parts) but has no dedicated visualization for frequency-domain analysis beyond FFT on real-valued traces. Three reference tools (LTspice, QSPICE, Xschem Graph) all provide Bode/Nyquist views. pqwave's multi-panel architecture, expression engine, and FFT infrastructure provide a strong foundation to add these without major architectural changes.

## Goals / Non-Goals

**Goals:**
- Bode plot: auto-detect AC magnitude/phase vectors and render gain (dB) + phase (degrees) in linked panels
- Nyquist plot: complex-plane trace with equal aspect ratio and frequency markers
- Histogram: per-trace distribution with configurable bins and range
- View templates: named, reusable view configs (.json) separate from project files

**Non-Goals:**
- Smith chart (requires specialized coordinate transform library, niche audience)
- 3D surface plots (requires major rendering changes)
- Monte Carlo / temperature sweep analysis (requires simulation engine, not just viewer)
- Template-based report generation (PDF/HTML)
- Jitter analysis from eye diagrams (separate effort)

## Decisions

### Bode Plot: auto-split two panels

Reuse `PanelGrid.split()` to create two vertically-stacked panels sharing the same X-axis (frequency). Top panel shows gain (dB), bottom panel shows phase (degrees).

**Alternatives considered:**
- Single panel with dual Y-axis (gain on Y1, phase on Y2): rejected because gain and phase have fundamentally different units and scales; a shared X-axis with separate Y scales in separate panels is the industry standard.
- Dedicated BodePlotWidget: rejected; adds maintenance burden vs reusing the existing panel infrastructure.

Auto-detection: when the user triggers Bode plot, scan available vectors for `db(...)` / `v(...)_db` or magnitude/phase naming patterns. If AC vectors exist, auto-select them. Otherwise prompt the user to select vectors or enter expressions.

### Nyquist Plot: reuse PlotWidget with equal-aspect-ratio constraint

Add an `equal_aspect` flag to `PlotWidget` that locks the ViewBox aspect ratio to 1:1. Reuse the existing mark/cross-hair system for frequency annotations. Render trace as a parametric curve (real vs imag).

**Alternatives considered:**
- Dedicated Nyquist widget: rejected; the equal-aspect mode is the only difference from a standard X-Y plot.

### Histogram: compute with numpy, render as bar chart

Use `numpy.histogram()` for computation. Render using `pg.BarGraphItem` overlaid on existing plot infrastructure. This avoids introducing a plotting library dependency and stays within the pyqtgraph ecosystem.

Configurable: bin count (auto or manual), range (auto, full data, or user-specified), normalization (count, density, probability).

### View Templates: separate JSON files, no code changes to PlotWidget

Templates store only view configuration (axis ranges, log mode, trace expressions, color assignments, display settings). They do NOT reference specific files or datasets. Stored in `~/.pqwave/templates/` as individual `.json` files.

**Alternatives considered:**
- Extend project files to support partial restore: rejected; project files are full session captures. Templates are intentionally lightweight and data-agnostic.

## Risks / Trade-offs

- **Bode auto-detection may fail for unconventional vector names** → Provide manual vector/expression override in the Bode dialog.
- **Equal-aspect ViewBox may conflict with auto-range** → Lock aspect ratio only after initial auto-range; let ViewBox pad to maintain aspect.
- **Histogram on very large datasets (10M+ points)** → Downsample before histogram computation (reuse existing downsampling threshold).
- **Template proliferation / stale references** → Templates reference expressions by name only; if expression references a missing vector, fail gracefully with a warning.
