## Why

Comparing pqwave against LTspice, QSPICE, and Xschem Graph reveals gaps in AC analysis visualization and statistical display. pqwave already loads AC analysis data and has a strong expression/FFT engine — adding Bode, Nyquist, and histogram views would close the most impactful gaps without requiring simulation engine changes.

## What Changes

- **Bode plot**: Dual-panel gain (dB) and phase (degrees) vs frequency, reusing the existing multi-panel and expression infrastructure. Supports magnitude/phase vectors from AC analysis or computed from real-valued traces via FFT.
- **Nyquist plot**: Complex-plane trace display (real vs imaginary), with equal-aspect-ratio option and frequency-annotated markers. Natural complement to Bode for stability analysis.
- **Histogram**: Per-trace histogram with configurable bin count, range, and normalization. Reuses existing trace data pipeline. Accessible from the Analyze menu and the Session API.
- **Template system**: Save/load named view templates (axis config, trace expressions, display settings) that can be applied to different datasets, distinct from the existing full-session project save/restore.

## Capabilities

### New Capabilities
- `bode-plot`: Gain/phase vs frequency display for AC analysis, with auto-detection of magnitude/phase vectors and dB conversion.
- `nyquist-plot`: Complex-plane trace rendering with equal-aspect-ratio option and frequency marker annotations.
- `histogram`: Trace histogram with configurable bins, range, normalization, and Session API support.
- `view-templates`: Named, reusable view configuration templates (axes, styles, expressions) applicable across datasets.

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- **UI**: New Analyze menu items and toolbar buttons for Bode, Nyquist, Histogram. New Template Manager dialog.
- **API**: New Session API commands: `bode()`, `nyquist()`, `histogram()`, `save_template()`, `load_template()`, `list_templates()`.
- **Rendering**: Nyquist requires equal-aspect-ratio viewbox mode (new constraint on Panel/PlotWidget). Bode reuses existing multi-panel infrastructure. Histogram reuses the bar-graph rendering already used for eye diagram persistence.
- **Storage**: Template files (~/.pqwave/templates/) in JSON format, separate from project files.
