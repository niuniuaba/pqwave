# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tool Rules

- Never use the built-in `WebFetch` tool — its domain safety check fails on most sites. Use `curl` via Bash instead.

## Commands

```bash
# Run the application
python pqwave.py [file.raw]               # Open a file directly
python pqwave.py --debug file.raw         # Debug logging
python pqwave.py --test                   # Run all test suites

# Testing
pytest pqwave/tests/                      # Run all tests via pytest
pytest pqwave/tests/test_basic.py         # Run a single test file
pytest pqwave/tests/test_trace_manager.py -k "test_add"  # Run matching tests

# Code quality
make lint        # flake8 + mypy
make format      # black
make test        # pytest (via Makefile)
```

## Architecture

**Layer map** (top to bottom, dependency direction →):
- **UI** (`pqwave/ui/`) — Qt widgets. Depends on `models` and `utils`. Never imported by models.
- **Analysis** (`pqwave/analysis/`) — Pure NumPy engines (Bode, Nyquist, histogram, power, Monte Carlo multi-run). No Qt.
- **Models** (`pqwave/models/`) — `RawFile` (spicelib wrapper), `Dataset`/`Variable`, `Trace` dataclass, `ExprEvaluator` (~90 functions, recursive-descent infix parser), `ApplicationState` (singleton).
- **Communication** (`pqwave/communication/`) — `XschemServer` (TCP) + `CommandHandler` for xschem schematic editor integration.
- **Digital** (`pqwave/digital/`) — VCD file support, digital/eye rendering, bus slicing, threshold config.
- **Session** (`pqwave/session/`) — `SessionAPI`: Qt-free orchestrator with `@api_command` decorator for REPL/headless use.
- **LLM** (`pqwave/llm/`) — AI backends for natural-language-to-command translation.
- **Utils** (`pqwave/utils/`) — `ColorManager`, `LogAxisItem`, `ThrottledPlotItem`.

**Core data flow**:
1. `RawFile` parses `.raw`/`.qraw` files into datasets (list of dicts: `variables` + `data` matrix).
2. `Dataset` wraps a dataset dict, exposes `Variable` objects with lazy column references (NumPy views, not copies).
3. `ExprEvaluator` evaluates infix expressions against a dataset.
4. `Trace` is a dataclass holding `x_data`/`y_data` arrays, axis assignment, color, metadata.
5. `ApplicationState` (singleton) holds datasets, per-panel `PanelState` (traces, axis configs), and UI prefs.

**Multi-panel system**: `PanelGrid` manages up to 4 `Panel` widgets via recursive `QSplitter`. Each `Panel` owns a `PlotWidget` (dual Y-axis, cursors, marks), `TraceManager` (trace lifecycle, log transforms, downsampling to 1600 target), and `AxisManager`. `ApplicationState.traces`/`.axis_configs` route through the active panel's `PanelState`.

## Plot Performance Rules

### Tiered rendering strategy

Traces use a three-tier strategy selected by `_select_render_strategy()` based on
per-trace point count:

| Tier | Points | Item type | AA | Width | Downsampling |
|------|--------|-----------|-----|-------|-------------|
| 1 (quality) | < 50K | `PlotDataItem` | ON | 2 | autoDownsample (adaptive) |
| 2 (balanced) | 50K–500K | `PlotDataItem` | ON | 2 | autoDownsample (adaptive) |
| 3 (perf) | > 500K | `PlotCurveItem` (`_StaticCurveItem`) | OFF | 1 | manual pre-ds to 1600 |

### Rules

1. Use `_select_render_strategy()` to determine rendering parameters — do not
   hardcode `DOWNSAMPLE_TARGET` or pen width in new rendering paths.
2. Reuse plot objects — call `setData()` rather than creating new objects.
3. On log mode switch, reuse objects and only transform data.
4. Set all styles/options at object creation; afterwards only update data.
5. Enable anti-aliasing by default on all `PlotDataItem` and `PlotCurveItem`
   instances (set `antialias=True`). The Qt raster engine's AA path uses SIMD-
   optimised subpixel rendering and avoids a pathological overhead in the
   non-AA `PlotCurveItem` segmented-line path.
6. Pass NumPy ndarrays to `setData`, not Python lists.
7. Set `skipFiniteCheck=True` (validation belongs in simulation, not rendering).
8. Keep the ViewBox throttle at 30ms (`_VB_THROTTLE_MS` in `plot_widget.py`) —
   this prevents wasted paint cycles during rapid pan/zoom regardless of data size.

## Coordinate Systems

pyqtgraph in log mode: the viewbox coordinate system is log10 space. mapSceneToView returns exponent values (e.g., 3.0 not 1000.0). Distinguish:

- **ViewBox coordinates** (exponent values): use for all visual elements added to the plot (InfiniteLine, ScatterPlotItem, PlotCurveItem, setXRange/setYRange, etc.).
- **Linear space values** (actual data values): use for all user-facing values (status bar, data panel, exports).

When a value serves both rendering and display (e.g., marks), keep both representations.

## Log Mode Implementation

Data is pre-transformed to log10 by TraceManager; the ViewBox stays linear. Never set ViewBox log mode — that causes double-log.

### 1. Never set ViewBox log mode
```python
# Correct — log mode only on the axis (for tick generation)
self.getAxis('bottom').setLogMode(x=log_mode)
self.getAxis('left').setLogMode(y=log_mode)

# Wrong — causes double-log
self.plotItem.vb.setLogMode('x', log_mode)
self.plotItem.vb.setLogMode('y', log_mode)
```

### 2. New traces must check current log mode
In `_create_plot_item()`, apply log10 transform based on x_log/y_log before rendering:
```python
x = np.log10(np.abs(x_data) + 1e-300) if self.x_log else x_data
y = np.log10(np.abs(y_data) + 1e-300) if y_log else y_data
```

### 3. Log mode toggle reads from original (linear) data
`update_traces_for_log_mode()` must read from `state.traces`, never from a PlotCurveItem (already-transformed), to avoid double-log:
```python
trace = self.state.traces[i]
x = np.log10(np.abs(trace.x_data) + 1e-300) if self.x_log else trace.x_data.copy()
y = np.log10(np.abs(trace.y_data) + 1e-300) if y_log else trace.y_data.copy()
```

### 4. Coordinate conversion
ViewBox is linear but data is log10, so mapSceneToView returns log10-space values. Convert to linear for display:
```python
def _log_to_linear(value: float) -> float:
    return 10.0 ** value  # 3.0 → 1000.0
```

### 5. clear_traces() resets log flags
`TraceManager.clear_traces()` resets x_log/y1_log/y2_log to False but leaves axis log mode unchanged. After opening a new file, restore log mode from ApplicationState via `_update_trace_manager_log_modes()`.

## Development Workflow

### Python Rules
1. Use the venv Python interpreter if a venv directory exists.
2. Move verified test scripts into pqwave/tests/.
3. Run only relevant tests, not the full suite, unless asked.

### Task Boundaries
Do not auto-fix issues from issues.md or TODO.md unless asked.

### Code Review Focus for Self-Learner
- Focus on spec compliance: does the code do exactly what the spec says?
- Check for hidden assumptions or incomplete error handling.
- For learning purposes, explain *why* a suggestion improves quality.
- Ignore style preferences unless they affect readability.

### Feature Development (5 Phases, No Skipping)

When the user says "New feature:" or "Develop:", follow these phases in strict order. Pause and wait for user confirmation after each phase.

**Phase 1: Specification (OpenSpec)**
- Run `/opsx:propose`
- Generate `proposal.md`, `specs/`, `design.md`, `tasks.md`
- **PAUSE**: "Specification generated. Please confirm by replying 'spec confirmed'"

**Phase 2: Planning (Superpowers Writing Plans)**
- After user confirmation, run `/superpowers:writing-plans`
- Read `tasks.md` and break it down into `plan.md` (2–5 minute granularity)
- **PAUSE**: "Implementation plan generated. Please confirm by replying 'plan confirmed'"

**Phase 3: Implementation (Superpowers Subagent-Driven + TDD)**
- After user confirmation, invoke the `subagent-driven-development` skill
- Each task MUST follow TDD: write failing test → implement → pass test
- After each subtask, output a summary of test results
- **PAUSE**: "Task X completed. Reply 'continue' or 'modify'"

**Phase 4: Review (Superpowers Requesting Code Review)**
- After all implementation tasks are complete and before any merge or archive, invoke the `requesting-code-review` skill.
- The review MUST follow two stages:
  1. **Spec Compliance Review**: Verify implementation against `specs/*.md`.
  2. **Code Quality Review**: After spec compliance passes, review code structure, style, performance, and security.
- The reviewer runs in a separate subagent with focused context.
- After review completes, present findings with severity levels (CRITICAL, HIGH, etc.).
- **PAUSE**: "Code review completed. Reply 'fix' to address issues, 'continue' to proceed, or 'review' to discuss findings."

**Phase 5: Verification & Archive**
- After review passes, run `/opsx:verify` to validate requirements against implementation
- After verification passes, run `/opsx:archive`
- Output final report: "Feature development completed and archived"

### Prohibitions
- Never use `/opsx:apply` directly
- Never skip `writing-plans` and go straight to coding
- Never write implementation code without a failing test first
- Never skip `requesting-code-review` before verification and archive
