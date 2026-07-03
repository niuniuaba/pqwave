## 1. Data model

- [x] 1.1 Create `RenderStrategy` dataclass with fields: `item_type: str` (`"PlotDataItem"` | `"PlotCurveItem"`), `pen_width: float`, `antialias: bool`, `pre_ds_target: int | None`
- [x] 1.2 Define tier threshold constants: `TIER1_MAX = 50_000`, `TIER2_MAX = 500_000`, `DOWNSAMPLE_TARGET = 1600` (keep existing constant, add new ones)

## 2. Core strategy selection

- [x] 2.1 Implement `_select_render_strategy(trace_points: int, total_visible_points: int) -> RenderStrategy` as a module-level pure function in `pqwave/ui/trace_manager.py`
- [x] 2.2 Tier 1 (`< 50K`): return `RenderStrategy("PlotDataItem", pen_width=2, antialias=True, pre_ds_target=None)`
- [x] 2.3 Tier 2 (`50K–500K`): return `RenderStrategy("PlotDataItem", pen_width=2, antialias=True, pre_ds_target=None)`
- [x] 2.4 Tier 3 (`> 500K`): return `RenderStrategy("PlotCurveItem", pen_width=1, antialias=False, pre_ds_target=1600)`

## 3. TraceManager rendering integration

- [x] 3.1 Update `_create_analog_plot_item()` to call `_select_render_strategy()` and branch on `item_type`
- [x] 3.2 Implement `PlotDataItem` path: create `pg.PlotDataItem(x, y, pen, symbol=None, skipFiniteCheck=True, autoDownsample=True, downsampleMethod='peak', antialias=True)` — no manual downsample
- [x] 3.3 Implement `PlotCurveItem` fallback path: use existing `_downsample()` + `_StaticCurveItem` logic (current behavior, unchanged)
- [x] 3.4 Update `update_traces_for_log_mode()` to use strategy selection instead of hardcoded `DOWNSAMPLE_TARGET`
- [x] 3.5 Update `update_x_variable()` to use strategy selection instead of hardcoded `DOWNSAMPLE_TARGET`
- [x] 3.6 Verify Monte Carlo rendering paths are unchanged (MC has its own specialized rendering)
- [x] 3.7 Verify digital/bus trace rendering paths are unchanged (digital uses separate renderer)

## 4. User notification for Tier 3

- [x] 4.1 Track whether any currently visible trace is in Tier 3 (set flag in `TraceManager` or `PanelState`)
- [x] 4.2 Show status bar toast on first Tier-3 trace: "Large trace detected (N points). Rendering in performance mode. Consider extracting signals of interest before loading." (8 second timeout)
- [x] 4.3 Show persistent "Perf" indicator in status bar while Tier-3 traces are visible
- [x] 4.4 Remove "Perf" indicator when all Tier-3 traces are removed
- [x] 4.5 Suppress duplicate toasts (show only once per session for first Tier-3 entry)

## 5. Default pen width

- [x] 5.1 Change `Trace.line_width` default from `1.0` to `2.0` in `pqwave/models/trace.py`
- [x] 5.2 Update hardcoded `line_width=1.0` in `TraceManager` trace construction (lines ~409, ~544)
- [x] 5.3 Verify session save/load preserves explicit `line_width` values (existing serialized traces at 1.0 stay at 1.0)

## 6. Documentation

- [x] 6.1 Update `CLAUDE.md` Plot Performance Rules section:
  - Remove "Avoid Pen width > 1" rule
  - Replace anti-aliasing silence with "Enable anti-aliasing by default (Qt GPU path is faster)"
  - Replace pre-downsample guidance with tiered strategy summary
  - Keep ViewBox throttle rule (still valid)
  - Keep `skipFiniteCheck=True` rule (still valid)
  - Keep segmented line mode rule for Tier 3 only

## 7. Tests

- [x] 7.1 Unit test `_select_render_strategy` for all tier boundaries: 0 pts, 1K pts, 49,999 pts (Tier 1), 50,000 pts (Tier 2), 50,001 pts (Tier 2), 499,999 pts (Tier 2), 500,000 pts (Tier 3), 500,001 pts (Tier 3), 1M pts (Tier 3)
- [x] 7.2 Unit test `RenderStrategy` dataclass construction and field access
- [x] 7.3 Unit test that strategy selection is importable without QApplication
- [x] 7.4 Unit test `Trace` default `line_width` is 2.0
- [x] 7.5 Integration test: create trace with 4K pts, verify `PlotDataItem` is created with correct parameters
- [x] 7.6 Integration test: create trace with 1M pts, verify `PlotCurveItem` is created and toast fires
- [x] 7.7 Integration test: session load preserves explicit `line_width: 1.0` from old files

## 8. Verification

- [x] 8.1 Run `pytest pqwave/tests/ -x -q` and ensure all existing tests pass
- [x] 8.2 Manually verify visual quality with `tests/bridge.raw` (4K pts, Tier 1): anti-aliased, w=2, smooth on zoom
- [x] 8.3 Manually verify with `tests/cdg_16M.raw` (500K pts, Tier 2/3 boundary): acceptable performance, toast appears
- [x] 8.4 Manually verify with `tests/bridge_big.raw` (16M pts, Tier 3): "Perf" indicator visible
- [x] 8.5 Run `make lint` and ensure no new linting issues
