## 1. View Templates

- [ ] 1.1 Create `pqwave/templates/` module with `TemplateManager` class (save/load/list/delete template JSON files in `~/.pqwave/templates/`)
- [ ] 1.2 Add `save_template()`, `load_template()`, `list_templates()` to Session API
- [ ] 1.3 Add "File > Save View Template" and "File > Load View Template" menu items with dialogs
- [ ] 1.4 Create Template Manager dialog (list, preview, rename, delete templates)
- [ ] 1.5 Write unit tests for TemplateManager (save, load, list, delete, missing-file handling)
- [ ] 1.6 Write API integration tests for template commands

## 2. Histogram

- [ ] 2.1 Create `pqwave/analysis/histogram.py` with `compute_histogram()` using `numpy.histogram()` (auto bins via Sturges' rule, custom bins, range, normalization modes)
- [ ] 2.2 Add `HistogramConfig` dataclass to `models/state.py` (bins, range, normalization)
- [ ] 2.3 Create histogram renderer using `pg.BarGraphItem` in a new panel
- [ ] 2.4 Add "Analyze > Histogram" action (`Ctrl+Shift+H`) and configuration dialog
- [ ] 2.5 Add `histogram()` to Session API
- [ ] 2.6 Write unit tests for histogram computation
- [ ] 2.7 Write API integration tests for histogram command

## 3. Nyquist Plot

- [ ] 3.1 Add `equal_aspect` mode to `PlotWidget` (lock ViewBox aspect ratio to 1:1 after auto-range)
- [ ] 3.2 Create `pqwave/analysis/nyquist.py` with vector detection (real/imag pair or single complex vector extraction)
- [ ] 3.3 Integrate frequency marker annotations on Nyquist curve (reuse cross-hair mark system, snap to nearest frequency point)
- [ ] 3.4 Add "Analyze > Nyquist Plot" action and vector selection dialog
- [ ] 3.5 Add `nyquist()` to Session API
- [ ] 3.6 Write unit tests for Nyquist vector detection and equal-aspect viewbox
- [ ] 3.7 Write API integration tests for nyquist command

## 4. Bode Plot

- [ ] 4.1 Create `pqwave/analysis/bode.py` with AC vector auto-detection (db/magnitude + phase pattern matching, fallback to manual selection)
- [ ] 4.2 Implement FFT-based Bode fallback for real-valued traces (reuse `fft_engine.py`)
- [ ] 4.3 Implement dual-panel rendering via `PanelGrid.split()` with synchronized X-axis (frequency)
- [ ] 4.4 Add "Analyze > Bode Plot" action and vector/expression selection dialog
- [ ] 4.5 Add `bode()` to Session API
- [ ] 4.6 Write unit tests for Bode vector detection and FFT fallback
- [ ] 4.7 Write API integration tests for bode command
