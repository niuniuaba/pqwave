# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

`pqwave` — a SPICE waveform viewer (PyQt6 + pyqtgraph) that reads `.raw`/`.qraw`
simulation data from ngspice, LTspice, QSPICE and Xyce, plus mixed-signal
`.vcd`/`.fst`/`.ghw`. It is also an analysis frontend (Bode, Nyquist, Smith, polar,
FFT, power, Monte Carlo, worst-case) and an EDA bridge hub (KiCad, xschem, Lepton
EDA, Qucs-S, QSPICE).

Version: **0.3.4**, defined once in `pqwave/_version.py`. MIT licensed.
Single author; `main` is the only branch.

## Environment

- Use the checked-out virtualenv: `./venv/bin/python` (Python 3.14.4).
  Rule: *if a `venv/` directory exists, use its interpreter.*
- Verified installed: PyQt6, pyqtgraph, numpy, scipy, spicelib, eyediagram,
  pytest 9.0.3, pytest-qt 4.5.0, flake8, mypy, **black 26.5.1**.
- GUI work needs `QT_QPA_PLATFORM=offscreen`; `pqwave/tests/conftest.py` sets it
  before anything imports Qt, so a bare `pytest` needs no shell setup.
- User state lives outside the repo: `~/.pqwave/{prefs.json,keybindings.json,templates.yaml}`,
  `~/.pqwave/templates/`, and the Qucs-S bridge edits `~/.config/qucs/qucs_s.conf`
  (backed up as `*.pqwave_backup`). Under a read-only home these log
  "Read-only file system" warnings — expected noise, not a bug.

## Commands

```bash
pytest                                    # whole suite; testpaths is set in pyproject
pytest pqwave/tests/test_bode.py -q       # one file
pytest -k "monte carlo" -q                # by keyword
./venv/bin/python pqwave.py --test        # each test file in its own subprocess (69 files)
./venv/bin/python pqwave.py [file.raw]    # run the app
make lint                                 # flake8 + mypy (both now actually run)
make format                               # black — see "Formatting backlog" before using
make test                                 # alias for pytest
```

A full suite run is ~950 tests in about 11 seconds.

### Useful CLI flags (`pqwave/main.py`)

`--version` `--test` `--debug` `--verbose` `--quiet` `--log-file FILE`
`--xschem-port PORT` `--no-xschem-server` `--xschem-send CMD` `--xschem-ba-port PORT`
`--extract` `--convert` `--qspice-bridge` `--sch-path` `--qucs-bridge`
`--setup-qucs-integration` `--connect` `--exec` `--setup-llm` `--help-commands`

## Test-suite architecture

`pqwave/tests/conftest.py` is load-bearing. It:

1. **Creates the one QApplication.** Qt permits exactly one per process. 14 test
   modules used to construct a second one, which destroys the first one's event
   dispatcher and kills the interpreter with a segfault ~12% into a run. New tests
   must reuse it: `QApplication.instance() or QApplication(sys.argv)`, or the
   session-scoped `qapp` / `app` fixtures.
2. **Resets the two process-wide singletons around every test** — `ApplicationState`
   (datasets, traces, per-panel state) and `WindowRegistry` (client-address → window
   mappings). Skipping this makes tests pass alone and fail in a full run; a complete
   `ApplicationState._initialize()` is deliberately *not* used because several
   modules build shared state at import time on purpose.
3. Exposes `fixture_path("tests/foo.raw")`, which **skips** rather than fails when a
   git-ignored data capture is absent.

Conventions and traps:

- **A test must not return a value.** `return False` does *not* fail a test — pytest
  only warns — so every check in such a function passes vacuously. `pyproject.toml`
  now sets `filterwarnings = ["error::pytest.PytestReturnNotNoneWarning"]`. Legacy
  bool-returning helpers are wrapped by the `_check_x()` + `def test_x(): assert
  _check_x() is True` adapter pattern; keep that shape when touching those files.
- **`MainWindow(path)` does not load the file eagerly** — it schedules
  `_load_initial_files()` on a `QTimer.singleShot(100, ...)`. One
  `app.processEvents()` will not fire it. Call `window._load_initial_files()`
  explicitly in fixtures.
- **`edit_trace_properties()` is non-blocking** (ends in `dialog.show()`). A dialog
  dismissed from `QTimer.singleShot` never fires before the assertions run — that
  bug made a whole trace-property test verify nothing. Drive the buttons directly
  (`button.click()`), which is both deterministic and fast.
- **Never write to the developer's home from a test.** Use `tmp_path` and
  `monkeypatch.setenv("HOME", ...)` / module-level path constants (see
  `cross_probe.GUILE_CCACHE_ROOT`).
- Fixtures the suite opens are tracked: `bridge.raw`, `cdg.raw`, `mixed_signal.raw`,
  `mixed_signal.vcd`, `eyediagram_demo.raw`, `eyediagram_demo.json`. Everything else
  under `tests/` (including the 100–450 MB performance captures) stays git-ignored
  on purpose; the big files are used only by the `profile_*.py` scripts.
- Non-test utilities live here too (`profile_*.py`, `cpu_profile.py`,
  `xschem_send_manual.py`). Anything in `pqwave/tests/` that is not an automated
  test must not start with `test_`, or `--test` will run it as one.
- Bridge tests that bind TCP are guarded by the `require_loopback` fixture and skip
  with a stated reason when the sandbox denies sockets — a skip there is correct,
  not a failure to chase.
- There is still no shared fixture layer beyond conftest: no `pytest-cov`,
  `pytest-timeout`, or `pytest-xdist` in the venv.

## Lint and type baselines

`make lint` runs and reports honestly, but **neither tool is clean — do not chase**.

- flake8: **482 findings**, of which ~328 are pure whitespace/blank-line formatting
  that `black` owns (E302 148, E231 68, W293 45, E127 18, E305 11, E128 10, E306 9).
  The rest: E501 92 (long strings, black cannot split these), F841 28 (unused locals
  inside `tests/` and `profile_*.py`), F401 23 (multi-name and deferred imports that
  need case-by-case judgement), F811 9 (intentional function-local re-imports),
  E402 1.
- All genuine bug classes are clear: F821 undefined names, F541 f-strings without
  placeholders, W292 missing final newline, E712 `== True`, E741 ambiguous `l`.
- mypy: **206 errors in 32 files** (203 sources checked), dominated by 77
  `assignment` + 42 `union-attr` — the pervasive `self.widget = None` in `__init__`
  then attribute access later. Fixing these needs `QStatusBar | None`-style
  annotations across 30+ files: its own project, not a drive-by.
- Verify your own change adds zero new findings: `flake8 -j 1 pqwave/ | wc -l`.
- Sandbox notes: pass `-j 1` to flake8 (its multiprocessing forkserver cannot bind);
  never hand mypy `pqwave.py` together with `pqwave/` (duplicate module name aborts
  the run — the Makefile is already fixed, keep it that way).

### Formatting backlog

`make format` works but has **never been run**: black would reformat essentially
every file. Do not fold that into a feature or fix commit. If the user wants it,
make it a single standalone `style: run black` commit.

## Architecture

Dependency direction is one-way: **ui → analysis / models / digital / session /
bridge → utils**. `models/`, `analysis/` and `session/` stay Qt-free so they work
headless and in the REPL.

| Layer | Path | Notes |
|---|---|---|
| UI | `pqwave/ui/` (42 files) | Qt widgets; never imported by the layers below |
| Analysis | `pqwave/analysis/` | Pure NumPy: bode, nyquist, smith, polar, histogram, correlation, power_analyzer, worst_case, multi_run |
| Models | `pqwave/models/` | `RawFile`, `Dataset`/`Variable`, `Trace`, `ExprEvaluator`, `ApplicationState`, `mc_collection`, `raw_converter`, `fst_adapter`, `ghw_adapter`, `vcdfile` |
| Bridge | `pqwave/bridge/` | `xschem/`, `kicad/`, `lepton/`, `qucs_s/`, `qspice/`, `schem_bridge.py`, `netlist_postprocessor.py` |
| Digital | `pqwave/digital/` | VCD, eye diagram, bus slicing, threshold config, trace-type detection |
| Session | `pqwave/session/api.py` | `SessionAPI`: Qt-free orchestrator; `@api_command` registers commands for the REPL and the LLM prompt |
| LLM | `pqwave/llm/` | natural-language → command translation, template backends |
| Measure | `pqwave/measure/` | `.meas` script parser + measure engine |
| Templates | `pqwave/templates/` | view-template save/apply |
| Utils | `pqwave/utils/` | `ColorManager`, `LogAxisItem`, `ThrottledPlotItem`, `impedance_format` |

**Core data flow:** `RawFile` parses `.raw`/`.qraw` into dataset dicts → `Dataset`
wraps one, exposing `Variable` objects that are *lazy NumPy column views, never
copies* → `ExprEvaluator` evaluates infix expressions against a dataset → `Trace`
holds `x_data`/`y_data` + axis/color/metadata → `ApplicationState` (singleton) holds
datasets, per-panel `PanelState`, UI prefs.

**Multi-panel:** `PanelGrid` manages up to 4 `Panel`s via recursive `QSplitter`; each
owns a `PlotWidget` (dual Y-axis, cursors, marks), a `TraceManager` and an
`AxisManager`. `ApplicationState.traces`/`.axis_configs` proxy to the **active**
panel's `PanelState`.

**Import graph:** `pqwave/__init__.py` and `pqwave/ui/__init__.py` both resolve
public names lazily (PEP 562). Keep them that way — eager `ui/__init__` imports of
`MainWindow` created a real circular import, because `measure_engine` needs
`pqwave.ui.measure_registry`, `ui/__init__` pulled in `main_window`, and
`main_window` imports `measure_engine` back. `pqwave/ui/measure_registry.py` and
`function_registry.py` are pure data tables despite living in `ui/`.

`pqwave/ui/main_window.py` (~8000 lines) and `pqwave/session/api.py` (~2900) are
god-files. Put new commands on `SessionAPI` (Qt-free and testable through
`ReplExecutor.run_sync`) and have `MainWindow` call them, rather than adding
UI-only logic to `main_window.py`.

## Rendering invariants (violating these causes visible bugs)

### Tiered render strategy
Chosen by `_select_render_strategy()` (`ui/trace_manager.py:1457`) from the per-trace
point count. Never hardcode `DOWNSAMPLE_TARGET` (`trace_manager.py:35`, 1600) or a
pen width in a new rendering path.

| Tier | Points | Item | AA | Width | Downsampling |
|---|---|---|---|---|---|
| 1 quality | < 50K | `PlotDataItem` | ON | 2 | autoDownsample (adaptive) |
| 2 balanced | 50K–500K | `PlotDataItem` | ON | 2 | autoDownsample (adaptive) |
| 3 perf | > 500K | `PlotCurveItem` (`_StaticCurveItem`) | **OFF** | 1 | manual pre-ds to 1600 |

- Reuse plot objects: call `setData()`, never recreate; set style/options at creation.
- On a log-mode toggle, reuse objects and transform only the data.
- Pass ndarrays to `setData`, not Python lists; keep `skipFiniteCheck=True`
  (validation belongs in simulation, not rendering).
- Anti-aliasing stays ON by default: the Qt raster *non-AA* `PlotCurveItem`
  segmented-line path is pathologically slow. Tier 3 opts out because manual
  downsampling has already removed the point-count cost.
- Keep the ViewBox throttle at 30 ms (`_VB_THROTTLE_MS`, `ui/plot_widget.py:30`) —
  it prevents wasted paint cycles during pan/zoom regardless of data size.

### Log mode: data is pre-transformed, the ViewBox is not
`TraceManager` applies `np.log10(np.abs(x) + 1e-300)`; **the ViewBox stays linear**.
Never call `vb.setLogMode()` — that double-logs and oscillates the range.

```python
self.getAxis('bottom').setLogMode(x=log_mode)   # correct
self.plotItem.vb.setLogMode('x', log_mode)      # WRONG — double-log
```

- `LogAxisItem.setLogMode` deliberately detaches the linked ViewBox around its
  `super()` call and restores it afterwards; `test_log_axis.py`
  ::`test_linked_viewbox_is_never_put_into_log_mode` guards this.
- New traces must check `x_log`/`y_log` in `_create_plot_item()` and transform first.
- `update_traces_for_log_mode()` must read `state.traces` (original linear data),
  never an already-transformed item.
- `mapSceneToView()` yields **log10 exponents** (3.0, not 1000.0). Exponents for
  anything added to the plot; linear values for anything the user sees. Convert with
  `10.0 ** value`; keep both for dual-use objects such as marks.
- `TraceManager.clear_traces()` resets `x_log`/`y1_log`/`y2_log` but not *axis* log
  mode — after opening a file, restore via `_update_trace_manager_log_modes()`.

### Raw format handling
`FORMAT_CONFIG` in `models/raw_converter.py` holds per-simulator encoding and dtypes,
and is the only place format differences may be resolved. Asymmetries: LTspice is
`utf_16_le` with `float32` data and `float64` time; QSPICE is `utf_8` `float64`; AC
quantities are `complex128` (complex stored as two float64).

## Working conventions

- **Target Python is 3.8+** (`requires-python`) while the dev venv is 3.14. This
  matters: Python 3.14 evaluates annotations **lazily** (PEP 649), so an undefined
  name in an annotation is invisible here but a hard `NameError` at import time on
  3.8–3.13. `menu_manager.py` shipped exactly that bug (used `Optional[dict]`
  without importing it). Either import annotation names for real or guard them with
  `TYPE_CHECKING`.
- **Version**: change `pqwave/_version.py` only. `pyproject.toml` reads it via
  `tool.setuptools.dynamic`, and `pqwave --version` / `pqwave.__version__` both
  derive from it. `setup.py` is a metadata-free shim. `test_imports.py` fails if the
  installed distribution drifts — after a version change re-run
  `./venv/bin/python -m pip install -e . --no-build-isolation`, and delete a stale
  root `pqwave.egg-info/` (an old `setup.py develop` leftover that shadows the real
  dist metadata).
- **Conventional commits**, lowercase imperative, scope in parentheses:
  `feat: add Smith chart analysis module (...)`,
  `fix: guard WC subprocess against TimeoutExpired`. Also `chore:`, `test:`, `docs:`.
  Review fixes read `fix: address <reviewer> review findings`.
- **Do not auto-fix items from `issues.md` or `TODO.md`** unless asked. Both are
  long-lived user-authored backlogs (`issues.md` is ~59 KB and mostly already-fixed
  reports); treat them as a ledger, not a task queue.
- **Run only relevant tests** unless asked for the whole suite.

### Feature development: 5 phases, no skipping
Entered when the user says "New feature:" or "Develop:". Pause for explicit
confirmation at every `PAUSE`; never chain phases unprompted.

1. **Spec (OpenSpec)** — `/opsx:propose` → `proposal.md`, `specs/`, `design.md`,
   `tasks.md` under `openspec/changes/<name>/`. *PAUSE for "spec confirmed".*
2. **Planning** — `superpowers:writing-plans`, expanding `tasks.md` into a
   2–5-minute-granularity `plan.md`. *PAUSE for "plan confirmed".*
3. **Implementation** — `superpowers:subagent-driven-development` + strict TDD:
   failing test → implement → pass. *PAUSE after each task.*
4. **Review** — `superpowers:requesting-code-review` in a separate focused-context
   subagent, in two stages: (a) spec compliance vs `specs/*.md`, then (b) code
   quality. Report findings as CRITICAL/HIGH/… *PAUSE.*
5. **Verify & archive** — `/opsx:verify`, then `/opsx:archive`.

Prohibited: `/opsx:apply`; going from spec straight to code; implementation code
before a failing test; skipping review before verify/archive.

## Where the reference material lives

- `openspec/specs/` — accepted capability specs; current truth for behaviour.
- `openspec/changes/{archive/,<active>}/` — per-feature proposal/design/tasks/
  VERIFICATION. Active: `mc-users-guide`, `qspice-bridge`, `smart-render-strategy`,
  `streamline-eda-integrations`. An archived `VERIFICATION.md` shows how that
  feature was validated.
- `docs/superpowers/plans/` — dated implementation plans; `specs/` — design notes.
- `docs/{kicad,lepton,xschem,qucs,monte_carlo,qspice}/` — per-tool guides plus example
  netlists/schematics. Read `docs/kicad/lessons-learned.md` before touching
  `bridge/kicad/`.
- `pqwave/tests/test_measure_comprehensive.py` and `test_api_commands.py` are the
  densest behavioural references for the measure engine and the session API.
  `test_api_commands.py::COMMAND_SPECS` is a registry-coverage gate: add an entry for
  every new `@api_command` or `test_all_commands_have_spec` fails.

## Instruction files

This file is the canonical agent guide and is **not** git-ignored. `CLAUDE.md` is
git-ignored (developer-local); it predates this file, still names the removed
`pqwave/communication/` package, and its example test commands point at scripts that
now collect real tests — prefer this file on conflict, and leave `CLAUDE.md` alone
unless asked to sync it.
