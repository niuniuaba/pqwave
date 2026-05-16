# API Command Comprehensive Test — Design Spec

**Date**: 2026-05-16
**Status**: Draft
**Scope**: `pqwave/tests/test_api_commands.py` — single new test file

## Goal

Verify that every registered API command in the SessionAPI command registry
responds correctly when invoked through the REPL code path (`ReplExecutor.run_sync()`).
Tests cover both success (round-trip state changes) and error (graceful failure) paths
across multiple dataset types.

## Approach: Hybrid — Scenarios with Independent State Resets

Chosen because it gives per-command pass/fail reporting, exercises real state transitions,
and handles both success and error cases.

Each command category gets its own test class. Within a class, each test method sets up
minimal state via module-scoped fixtures, then runs commands through `run_sync()` with
assertions on both return value shape and state side effects.

## Auto-Discovery Gate

A `COMMAND_SPECS` dictionary in the test file declares what each command needs.
At test collection time, we cross-reference `get_command_registry()` against the specs.
Any registered command without a spec entry generates a **failing test** with a clear
message: `"command 'foo' has no test coverage — add it to COMMAND_SPECS"`.

Adding a new `@api_command` only requires a 1-line entry in `COMMAND_SPECS`.
The framework generates basic smoke + error tests from the spec automatically.

## Test Fixtures

All fixtures use `scope="module"` — each file is loaded once and shared across tests.

| Fixture | File | Type | Used for |
|---------|------|------|----------|
| `session_bridge` | `pqwave/tests/bridge.raw` | transient analog | measurements, FFT, power, export |
| `session_cdg` | `pqwave/tests/cdg.raw` | AC complex | complex-signal FFT, complex handling |
| `session_mixed_raw` | `tests/mixed_signal.raw` | mixed-signal | trace CRUD, bus/digital, varied signal types |
| `session_mixed_vcd` | `tests/mixed_signal.vcd` | VCD | digital-only, bus from VCD |
| `session_eye` | `tests/eyediagram_demo.raw` | eye diagram | eye command |
| `session_empty` | (none) | no file loaded | error handling for missing preconditions |

CDG notes: the default X variable `'yes'` is never used. Tests will `change_x()` to set
a proper x-axis variable. `ac_data` is a complex vector (real = DC-bias voltage,
imag = branch current) used to test complex-signal FFT paths.

## Assertion Strategy

`run_sync(code)` returns `{"ok": True/False, "result": ..., "error": "..."}`.
Assertions match the test intent:

| Test type | Assertion | Example |
|-----------|-----------|---------|
| Smoke | `result["ok"] is True` | Command executes |
| Return shape | `isinstance(result["result"], list)` | `signals()` returns list |
| State change | Chain two commands | `add('x')` then `info()` shows `n_traces >= 1` |
| Error path | `result["ok"] is False` + error message present | Wrong args |
| Round-trip | Cmd A creates state, Cmd B reads it | `cursor_xa("1m")` → `cursor()` returns xa |

No assertions on exact numerical values — those belong in unit tests for the
computation engines. This test only verifies the API command dispatch layer.

## Output

Standard pytest stdout — no log file. Assertions are on structured return dicts,
not on printed output.

## Command Coverage by Category

### File I/O & Info (any loaded fixture)
`load`, `signals`, `info`, `help`

- Round-trip: `load()` returns file metadata matching what `info()` and `signals()` report
- Error: load nonexistent file, load unsupported format, info/signals with empty session

### Trace CRUD (mixed_raw — varied signal types)
`add`, `show`, `hide`, `remove`, `add_all`, `show_all`, `hide_all`, `remove_all`, `show_matching`

- Round-trip: add traces → info reflects count → hide/remove → info reflects delta →
  show/hide_all → all state flips
- Glob expansion: `show_matching("v(q*)")` adds matching signals
- Range expansion: `add("q1~q4")` expands if signals match
- Error: add nonexistent signal, add with no file loaded, remove nonexistent

### Measurements (bridge — clean transient data)
`measure`, `measure_script`

- Round-trip: add signal → measure avg/rms/rise_time/pp/min/max → results are floats
- measure_script: multi-line .meas script → named results
- Error: measure missing signal, malformed expression, from_/to with no matching range

### Analysis (bridge, cdg, eye fixtures)
`fft`, `power`, `eye`, `fft_config`

- fft on transient data (bridge): returns freq/mag/phase arrays
- fft on complex data (cdg): mag() auto-wrapping when signal is complex
- power: two signals → P(t) = V*I result
- eye: valid eye diagram data → returns dict with eye signal
- fft_config: set/get window/fft_size/representation
- Error: fft/power/eye with missing signal, fft with bad window name

### View Control (any loaded fixture)
`range`, `log_x`, `log_y`, `grid`, `legend`, `cross_hair`, `title`, `zoom_fit`, `auto_range_x`, `auto_range_y`

- Smoke: each command returns `ok=True` (headless no-ops are acceptable)
- Round-trip: `log_x(True)` → `info()` reflects log state (if state tracks it)
- Error: range with non-numeric values

### Cursors (any loaded fixture)
`cursor_xa`, `cursor_xb`, `cursor_ya`, `cursor_yb`, `cursor`, `cursor_delta`, `cursor_*_visible`

- Round-trip: `cursor_xa("1m")` → `cursor()` returns xa value
- Visibility toggles: `cursor_xa_visible(False)` returns ok
- cursor_delta: returns dict after setting both cursors
- Error: cursor with invalid value format

### Export (bridge)
`export_csv`, `export_plot`

- export_csv: writes file to tmp path, returns signals_exported count
- export_plot: headless no-op (delegates to GUI callback), returns ok
- Error: export_csv with unwritable path

### Bus/Digital (mixed_vcd, mixed_raw)
`bus`, `expand`, `collapse`, `digital`

- bus: group signals → returns bus name and signal list
- expand/collapse: toggle bus display
- digital: toggle digital/analog view
- Error: bus with nonexistent signals, expand/collapse nonexistent bus

### Panel / Zoom / Misc (any loaded fixture)
`split_horizontal`, `split_vertical`, `close_panel`, `zoom_in`, `zoom_out`, `theme`, `reload`, `change_x`, `set_trace`

- Smoke: each returns `ok=True` (headless no-ops are acceptable for GUI-bound commands)
- change_x round-trip: `change_x("frequency")` → info/state reflects new x var
- set_trace: set alias/color on existing trace
- reload: returns ok
- Error: change_x with nonexistent variable, set_trace on nonexistent trace

### Error Handling — Cross-Cutting
- No file loaded: any signal-dependent command returns error
- Wrong argument count: TypeError or ok=False
- Bad argument type: TypeError or ok=False
- Nonexistent signal: KeyError or ok=False with descriptive message
- JSON project file load: returns unsupported error (not a crash)

## Test File Structure

```
pqwave/tests/test_api_commands.py

COMMAND_SPECS = {...}                  # Auto-discovery gate

class TestFileIOAndInfo:               # load, signals, info, help
class TestTraceCRUD:                   # add, show, hide, remove, add_all, etc.
class TestMeasurements:                # measure, measure_script
class TestAnalysis:                    # fft, power, eye, fft_config
class TestViewControl:                 # range, log_*, grid, legend, etc.
class TestCursors:                     # cursor_*, cursor visibility
class TestExport:                      # export_csv, export_plot
class TestBusDigital:                  # bus, expand, collapse, digital
class TestPanelZoomMisc:               # split_*, close_panel, zoom_*, theme, etc.
class TestErrorHandling:               # cross-cutting error cases
class TestCommandCoverage:             # auto-discovery completeness check
```

## What This Test Does NOT Cover

- Exact numerical correctness of measurements, FFT, or power analysis
- GUI rendering (Qt widgets, plot curves, viewbox transforms)
- AI translator output (template/LLM code generation)
- Xschem integration or TCP server commands
- CLI `--exec` mode (which uses `SessionAPI.execute()` directly — separate path)
