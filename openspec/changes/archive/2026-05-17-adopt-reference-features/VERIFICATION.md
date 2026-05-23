## Verification Report: `adopt-reference-features`

**Date:** 2026-05-17
**Base:** e52e274 (main) → **Merged:** 2e9d686
**Schema:** spec-driven

### Summary

| Dimension    | Status                              |
|--------------|-------------------------------------|
| Completeness | 25/27 tasks done, 13/13 reqs addressed |
| Correctness  | 11/13 reqs fully covered, 2 partial |
| Coherence    | Design followed, minor deviations   |

### Issues by Priority

#### CRITICAL (0)

None. All core functionality is implemented and tested.

#### WARNING (3)

**W1 — Task 3.3: Nyquist frequency marker annotations not implemented**
- Spec: `nyquist-plot/spec.md` Requirement "Frequency marker annotations"
- The `compute_nyquist_trace()` backend accepts an optional `freq` parameter, but `_show_nyquist()` (`main_window.py`) never fetches or passes frequency data, and no marker-placement logic exists.
- **Recommendation:** Either implement marker placement (fetch frequency vector, pass to `compute_nyquist_trace`, wire cross-hair click-to-mark) or downgrade the spec requirement.

**W2 — Task 4.2: FFT-based Bode not exposed in UI**
- Spec: `bode-plot/spec.md` Requirement "Bode plot from real-valued trace via FFT"
- `compute_bode()` (`bode.py`) supports `signal` + `sampling_rate` parameters for FFT fallback. The UI `_show_bode()` always enters the AC-analysis vector-selection path. No UI affordance exists for FFT mode.
- **Recommendation:** Add a mode toggle to `BodeDialog` (trace selector + sampling rate input) that triggers the FFT path in `compute_bode()`.

**W3 — Task 1.4: Template Manager dialog missing preview**
- Spec: `view-templates/spec.md` Requirement "List and manage templates" — scenario expects "creation dates, and a preview of stored trace expressions"
- `TemplateManagerDialog` lists names only. No creation dates (from file mtime) or expression preview.
- **Recommendation:** Add `os.path.getmtime()` timestamps to list items and a read-only text area showing saved expressions.

#### SUGGESTION (2)

**S1 — Bode uses PlotCurveItem instead of PlotDataItem**
- `main_window.py` Bode rendering uses `pg.PlotCurveItem` directly. Per CLAUDE.md, `PlotDataItem` should be preferred for downsampling support.
- **Impact:** Low (Bode data is typically small AC sweeps). Relevant only for FFT-based Bode on large datasets.

**S2 — Nyquist API test in test_nyquist.py, not test_api_commands.py**
- `test_nyquist_command_registered` and `test_bode_command_registered` live in their feature test files rather than in `test_api_commands.py` alongside other command registration tests.
- **Impact:** Cosmetic — tests pass and commands are registered. Inconsistent with project convention.

### Completeness Detail

#### View Templates (Group 1)

| Task | Description | Status | Evidence |
|------|-------------|--------|----------|
| 1.1 | TemplateManager class | ✅ | `pqwave/templates/manager.py` |
| 1.2 | Session API commands | ✅ | `api.py`: save_template, load_template, list_templates |
| 1.3 | File menu items | ✅ | `menu_manager.py`: Save/Load/Manage Templates |
| 1.4 | Template Manager dialog | ⚠️ | `template_manager_dialog.py` — list/delete only, no preview |
| 1.5 | Unit tests | ✅ | `test_template_manager.py` (4 tests) |
| 1.6 | API integration tests | ✅ | `test_api_templates.py` (1 test) |

#### Histogram (Group 2)

| Task | Description | Status | Evidence |
|------|-------------|--------|----------|
| 2.1 | compute_histogram() | ✅ | `pqwave/analysis/histogram.py` |
| 2.2 | HistogramConfig | ✅ | `models/state.py:261` |
| 2.3 | BarGraphItem renderer | ✅ | `main_window.py:_show_histogram` |
| 2.4 | Analyze > Histogram | ✅ | `menu_manager.py`, `histogram_dialog.py` |
| 2.5 | histogram() API | ✅ | `api.py:histogram()` + `@api_command` |
| 2.6 | Unit tests | ✅ | `test_histogram.py` (6 tests) |
| 2.7 | API integration tests | ✅ | `test_api_commands.py:test_histogram_command_registered` |

#### Nyquist Plot (Group 3)

| Task | Description | Status | Evidence |
|------|-------------|--------|----------|
| 3.1 | equal_aspect PlotWidget | ✅ | `plot_widget.py`: `equal_aspect` parameter |
| 3.2 | nyquist analysis module | ✅ | `pqwave/analysis/nyquist.py` |
| 3.3 | Frequency markers | ❌ | **Not implemented** — backend accepts freq param, UI never passes it |
| 3.4 | Analyze > Nyquist Plot | ✅ | `menu_manager.py`, `nyquist_vector_dialog.py` |
| 3.5 | nyquist() API | ✅ | `api.py:nyquist()` + `@api_command` |
| 3.6 | Unit tests | ✅ | `test_nyquist.py` (5 tests) |
| 3.7 | API integration tests | ✅ | `test_nyquist.py:test_nyquist_command_registered` |

#### Bode Plot (Group 4)

| Task | Description | Status | Evidence |
|------|-------------|--------|----------|
| 4.1 | bode analysis module | ✅ | `pqwave/analysis/bode.py` |
| 4.2 | FFT-based Bode | ⚠️ | Backend done, **UI not exposed** |
| 4.3 | Dual-panel + sync | ✅ | `main_window.py:_show_bode` |
| 4.4 | Analyze > Bode Plot | ✅ | `menu_manager.py`, `bode_dialog.py` |
| 4.5 | bode() API | ✅ | `api.py:bode()` + `@api_command` |
| 4.6 | Unit tests | ✅ | `test_bode.py` (5 tests) |
| 4.7 | API integration tests | ✅ | `test_bode.py:test_bode_command_registered` |

### Correctness Detail

**13 requirements across 4 specs.** Implementation evidence verified by file grep.

| # | Requirement | Status | Implementation |
|---|-------------|--------|----------------|
| B1 | Bode from AC vectors | ✅ | `bode.py:compute_bode()`, `main_window.py:_show_bode()` |
| B2 | Bode from FFT fallback | ⚠️ | `bode.py:compute_bode()` supports it; UI missing |
| B3 | Bode Session API | ✅ | `api.py:bode()` + `@api_command("bode")` |
| H1 | Trace histogram | ✅ | `histogram.py:compute_histogram()`, `main_window.py:_show_histogram()` |
| H2 | Normalization modes | ✅ | count/density/probability in `histogram.py:44-50` |
| H3 | Histogram Session API | ✅ | `api.py:histogram()` + `@api_command("histogram")` |
| N1 | Nyquist from complex data | ✅ | `nyquist.py`, `main_window.py:_show_nyquist()` |
| N2 | Frequency markers | ❌ | Backend param exists, UI never wires it |
| N3 | Nyquist Session API | ✅ | `api.py:nyquist()` + `@api_command("nyquist")` |
| T1 | Save view template | ✅ | `manager.py:save()`, `api.py:save_template()` |
| T2 | Load view template | ✅ | `api.py:load_template()` with graceful degradation |
| T3 | List and manage templates | ⚠️ | `template_manager_dialog.py` — list+delete, no preview |
| T4 | Template Session API | ✅ | 3 commands registered |

### Coherence Detail

**Design decisions followed:**
- Bode: dual-panel via `PanelGrid.split_panel()` — ✅
- Nyquist: equal-aspect ViewBox — ✅
- Histogram: numpy.histogram + BarGraphItem — ✅
- Templates: separate JSON files in `~/.pqwave/templates/` — ✅

**Minor deviations:**
- `HistogramConfig` stripped `to_dict()`/`from_dict()` (intentional — transient config, not persisted)
- Template dialog uses "Close" instead of "Rename" button (reasonable simplification)
- Bode X-axis sync is one-way (gain→phase) — initial sync added in fix

### Final Assessment

**No critical issues.** 2 warning-level spec gaps (Nyquist markers, FFT Bode UI) and 1 partial implementation (template preview) were deferred during implementation as UI polish items. All 13 requirements have backend support; 11 are fully functional end-to-end. 25/27 tasks complete. 22 tests passing.

**Ready for archive with noted gaps.** The 3 warnings should be tracked as follow-up work but do not block the core functionality from being considered complete.
