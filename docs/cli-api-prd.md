# PRD: CLI API & Chat REPL for pqwave

## Status: Draft
## Target: pqwave v0.4.0

---

## 1. Problem Statement

pqwave is a powerful SPICE waveform viewer, but its only interface today is a GUI driven by mouse and keyboard shortcuts. This creates three gaps:

- **Automation gap**: users who want to script repetitive workflows (load file → measure 5 signals → export plot) must do it manually every time
- **Discoverability gap**: new users face a blank window with menus; there's no way to express intent directly ("show me the FFT of vout")
- **Integration gap**: external tools (schematic editors, simulators, CI pipelines) can only launch pqwave with a file path — no programmatic control

The existing `--extract` and `--convert` headless modes prove the data layer is ready. The missing piece is an **orchestrator that exposes every GUI operation as a callable command**, and a **REPL surface** that makes those commands accessible to both power users and AI.

## 2. User Personas

| Persona | Typical scenario |
|----------|-----------------|
| **Analog IC designer** | Runs the same 5 measurements on every simulation run; wants a script that loads the fresh `.raw`, runs `.meas`, exports a CSV, and opens the GUI for exploration |
| **Power engineer** | Uses a schematic tool that launches pqwave; wants to send commands over TCP to add traces and zoom to a region |
| **Student / educator** | New to SPICE; doesn't know pqwave's menu structure; wants to type "show me the rise time" and get a result |
| **CI/CD pipeline operator** | Wants `pqwave --exec '...'` to produce a plot PNG for automated design review |
| **Scripting power user** | Wants a Python REPL attached to the live GUI so they can drive analysis with numpy/scipy while seeing plots update in real time |

## 3. Scope

### 3.1 In Scope (v0.4.0)

**P0 — Session API**
- **P0.1** Qt-free `SessionAPI` class: orchestrates file load, trace add/remove, measure, FFT, power analysis, CSV/plot export
- **P0.2** `@api_command` decorator: each feature module registers its own commands; auto-discovered by REPL and AI translator
- **P0.3** CLI entry point: `--exec <code>` for headless JSON output; `pqwave script.py` launches GUI with preset state

**P1 — Chat Panel (Python REPL)**
- **P1.1** Bottom panel widget (`ChatPanel`): slides open/close with `Ctrl+\``, monospace output area + input line
- **P1.2** Python REPL (`ReplExecutor`): `code.InteractiveInterpreter`-based, tab-completion for signal names and commands, command history
- **P1.3** Live GUI sync: a REPL command that adds a trace updates the plot immediately

**P2 — AI REPL**
- **P2.1** `/ai` mode switch: in AI mode, all input is natural language, sent directly to LLM for translation → Python code execution. No quoting or prefix. `/python` returns to Python REPL.
- **P2.2** Three LLM backends: local URL (Ollama/LM Studio), downloaded Qwen2.5-0.5B via llama.cpp, external API (OpenAI/Anthropic)
- **P2.3** LLM setup wizard: guided configuration for each backend, including model download with progress

**P3 — Script Launcher**
- **P3.1** `pqwave script.py`: executes a Python script that sets up traces/measurements, then opens the GUI with that state
- **P3.2** `.meas` compatibility: existing `measure_script_parser.py` usable from scripts via `measure_script(...)`

### 3.2 Out of Scope (v0.4.0)

- Multi-window chat sessions (one REPL driving multiple windows)
- Agent-style multi-turn LLM conversations (translator is single-turn: NL → code)
- Built-in LLM model bundling (pqwave offers download setup, never ships a model)
- TCP client for remote pqwave control (Phase 1 is in-process API; TCP protocol can layer on top later)
- GUI automation recording (macro record/playback)
- Notebook-style mixed code+plot output (single output area, not inline plots)

## 4. Functional Requirements

### FR-1: Session API

The `SessionAPI` class is the single entry point for all programmatic interaction. It is Qt-free so it works without QApplication.

| Command | Signature | Description |
|---------|-----------|-------------|
| `load` | `load(path: str)` | Load raw/vcd/json file into session |
| `signals` | `signals()` | List available signal names |
| `show` | `show(expr: str \| list[str])` | Add trace(s) to active panel |
| `hide` | `hide(trace_id: str)` | Remove a trace |
| `measure` | `measure(expr: str, **kwargs)` | Evaluate scalar measurement |
| `measure_script` | `measure_script(text: str)` | Batch execute .meas script |
| `fft` | `fft(signal: str, window="hann", **kwargs)` | Compute and display FFT |
| `power` | `power(v: str, i: str)` | Compute and display instantaneous power |
| `range` | `range(xmin=None, xmax=None, ymin=None, ymax=None)` | Set view range |
| `log_x` | `log_x(on: bool)` | Toggle X log mode |
| `log_y` | `log_y(on: bool)` | Toggle Y log mode |
| `export_csv` | `export_csv(path: str, signals=None)` | Export traces as CSV |
| `export_plot` | `export_plot(path: str)` | Export current view as PNG/SVG |
| `info` | `info()` | Return session metadata dict |
| `help` | `help()` | List all registered commands |

**FR-1.1** Commands auto-register via `@api_command(name, signature, help)` decorator on the implementing function. The decorator stores metadata in a module-level `_COMMAND_REGISTRY` dict.

**FR-1.2** When a SessionAPI method is called, it updates `ApplicationState` and emits Qt signals (if QApplication exists) so the GUI refreshes.

**FR-1.3** `SessionAPI.execute(code: str)` parses and executes a single line of Python using `code.InteractiveInterpreter`, with `self` available as the session object.

### FR-2: Command Registration (Decorator Pattern)

```python
from pqwave.session.api import api_command

@api_command("bode", "bode(signal, fmin, fmax, points=100)", "Frequency response")
def cmd_bode(session, signal, fmin, fmax, points=100):
    ...
```

**FR-2.1** The decorator registers the function in a global command table discoverable by the REPL and AI translator.

**FR-2.2** Each feature module (e.g., `power_analyzer.py`) is responsible for importing and registering its own commands. No central command catalog needs manual updating.

**FR-2.3** Commands are registered at module import time. The Session API imports all feature modules that register commands.

### FR-3: Chat Panel

**FR-3.1** The panel is inserted into MainWindow's vertical layout between the PanelGrid and ControlPanel, with stretch factor 0.

**FR-3.2** Default state is hidden. `Ctrl+\`` toggles visibility with a slide animation (QPropertyAnimation on maximumHeight).

**FR-3.3** Panel contains: (top to bottom)
- A small toolbar with "Configure AI..." gear button
- A read-only QPlainTextEdit for output (monospace, dark background)
- A QLineEdit for input (with placeholder text)

**FR-3.4** Input history navigable with Up/Down arrow keys.

**FR-3.5** Panel visibility is persisted in global preferences, following the existing pattern of `status_bar_visible`.

### FR-4: Python REPL

**FR-4.1** Input lines are executed by `code.InteractiveInterpreter` running in a QThread.

**FR-4.2** Tab-completion queries `SessionAPI` for signal names and registered command names.

**FR-4.3** Mode switching via `/` meta-commands:
- `/ai` → enters AI mode (prompt changes to `ai> `). All subsequent input is natural language, sent directly to the translator with no quoting or prefix.
- `/python` → enters Python mode (prompt returns to `pqwave> `). Standard Python REPL.
- `/` prefix is reserved for meta-commands (`/help`, `/clear`, `/ai`, `/python`).

**FR-4.4** Results are formatted and appended to the output area. Scalars print inline. Trace additions show a confirmation message like "Added trace: vout (Y1 axis)".

**FR-4.5** `help` and `help("command_name")` list available commands with signatures.

### FR-5: AI Translator

**FR-5.1** In AI mode, every input line is sent as raw natural language to the configured LLM backend. No quoting, prefix, or special syntax required. "measure rise time of vout" just works.

**FR-5.2** The system prompt includes:
- The list of all registered `@api_command` entries with full signatures and help text
- Current session state (loaded files, available signal names)
- Instruction: "Convert the user's request into pqwave Session API Python code. Output only the code, no explanation."

**FR-5.3** The LLM response is displayed in the output area (so the user sees what code was generated), then executed.

**FR-5.4** Three backend options, all implementing the same `LLMBackend` protocol:

| Backend | Config | When to use |
|---------|--------|-------------|
| Local URL | `endpoint` (URL), `model` (name) | User already runs Ollama/LM Studio |
| Downloaded Model | `model_path` (GGUF file) | User wants fully local, no server |
| External API | `endpoint` (URL), `api_key`, `model` | User has OpenAI/Anthropic/anything-llm |

**FR-5.5** Config stored at `~/.pqwave/llm_config.json`. API keys are never logged.

**FR-5.6** If no backend is configured, entering AI mode shows a message: "No AI backend configured. Run pqwave --setup-llm or click the gear icon."

### FR-6: Script Launcher

**FR-6.1** When `pqwave` receives a single positional argument ending in `.py`, it treats it as a script: exec the script's code with `SessionAPI` methods available as top-level names, then construct MainWindow with the resulting ApplicationState.

**FR-6.2** Scripts are plain Python. `SessionAPI` method names are injected as global names so scripts read naturally: `load("circuit.raw")` not `session.load("circuit.raw")`.

**FR-6.3** The script sets up initial state; the GUI opens afterward for interactive exploration. This is a launcher, not a batch processor.

**FR-6.4** For batch processing without GUI, use `pqwave --exec '...'`.

### FR-7: LLM Setup Wizard

**FR-7.1** `LLMSetupDialog(QDialog)` with three tabs, one per backend.

**FR-7.2** Tab 1 (Local URL): URL field + model name + "Test Connection" button that sends a minimal chat request.

**FR-7.3** Tab 2 (Downloaded Model): offers to `pip install llama-cpp-python` and download Qwen2.5-0.5B-Q4_K_M.gguf from HuggingFace. Shows download progress. pqwave does NOT bundle the model.

**FR-7.4** Tab 3 (External API): endpoint URL + API key (password field) + model name.

**FR-7.5** Accessible from ChatPanel gear button or `pqwave --setup-llm`.

## 5. Non-Functional Requirements

| NFR | Constraint |
|-----|-----------|
| **NFR-1** | SessionAPI must remain Qt-free — importable without QApplication |
| **NFR-2** | Chat panel must not steal focus from plot keyboard shortcuts when closed |
| **NFR-3** | REPL execution must not block the GUI thread (QThread or async) |
| **NFR-4** | No new mandatory dependencies in Phase 1-3, 5 |
| **NFR-5** | `httpx` is optional dependency for Phase 4 (HTTP backends) |
| **NFR-6** | `llama-cpp-python` is optional dependency for Phase 4 (downloaded model backend) |
| **NFR-7** | AI translator must never send raw waveform data to LLM — only signal names and command schemas |
| **NFR-8** | LLM API keys stored with file permissions 600 |
| **NFR-9** | Existing test suite must pass after each phase |

## 6. Success Criteria

| # | Criterion | Measured by |
|---|-----------|-------------|
| SC-1 | A user can run `pqwave --exec 'load("file.raw"); print(measure("avg(vout)"))'` and get a JSON result without a GUI | Manual smoke test |
| SC-2 | Pressing Ctrl+` opens/closes the chat panel with smooth animation | Manual visual test |
| SC-3 | Typing `show("vout")` in the REPL adds a trace to the plot in <200ms | Manual timing |
| SC-4 | Switching to `/ai` and typing `measure rise time of vout` generates executable Python and returns a correct measurement | Manual test with configured backend |
| SC-5 | `pqwave script.py` opens the GUI with all traces pre-loaded from script | Manual smoke test |
| SC-6 | Configuring AI backend via setup wizard survives restart | Read `~/.pqwave/llm_config.json` after wizard |
| SC-7 | Existing test suite passes with zero regressions | `pytest pqwave/tests/ -x -q` |
