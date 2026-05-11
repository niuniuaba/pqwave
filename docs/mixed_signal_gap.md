# Mixed-Signal PRD Gap Analysis

Audit of `docs/mixed_signal_prd.md` against current pqwave implementation (2026-05-11).

## Done

| FR | Feature | Notes |
|---|---|---|
| FR-1 | Signal type system (analog/digital/bus) | `Trace.trace_type`, `TraceTypeManager` |
| FR-2.1 | Logic threshold presets | TTL, CMOS-3.3V/5V/1.8V/1.2V, LVDS, Auto (20%/80%) |
| FR-2.2 | Digital colors per-trace | Uses `ColorManager` per-trace colors via `_StaticCurveItem` with `stepMode='center'` |
| FR-3.1 | Bus bit-order auto-inference | `_extract_bit_suffix` / `_reorder_by_bit_suffix` in `trace_type_manager.py` |
| FR-3.3 | Bus expand/collapse | `toggle_bus_expand()` in `TraceManager`; context menu wired |
| FR-4.1 | VCD parser | `vcdfile.py` wraps vcdvcd |
| FR-4.2 | Raw + VCD sync overlay | `vcd_time_aligner.py`, `np.searchsorted` ZOH |
| FR-4.3 | VCD-only mode | `vcd_only=True` path in `_load_vcd()` |
| FR-5.1 | Eye diagram generation | `eye_renderer.py` + eyediagram `grid_count` |
| FR-5.2 | Overlay + persistence rendering | `render_overlay`, `render_persistence` |
| FR-5.3 | Eye metrics overlay | `compute_eye_metrics` + `_add_metrics_overlay` |
| FR-6.1 | Multi-panel with shared X-axis | `PanelGrid`, `_sync_split_x_axes` |
| FR-6.2 | Legend with [D]/[BUS:N] suffixes | `trace_manager.py:574-579` |
| FR-6.3 | Right-click context menu | Plot area menu + per-trace menu (analog/digital/bus) |
| FR-6.4 | Threshold preview line | Opt-in checkbox in `ThresholdDialog` |

## Open

_All PRD requirements for v0.3.0 are now implemented._
