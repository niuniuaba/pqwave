# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph

![Version](https://img.shields.io/badge/version-0.3.4-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## ✨ Features

### 🎯 Core Capabilities
- **Multi-format Support**: ngspice/xyce, ltspice, qspice .qraw files
- **Dual Y-Axis**: Independent Y1 and Y2 axes with shared X-axis
- **Mathematical Expressions**: Infix notation with built-in functions

### 🖥️ User Interface
- **Unified Vector Selection**: Single combo box for all variables
- **Expression Support**: Quoted variables and complex expressions

## 📸 Screenshots
![本地图片](./screenshot.png)

## 📦 Installation 
```bash
# Clone repository
git clone https://github.com/niuniuaba/pqwave.git

# Create virtual environment
cd pqwave
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```
## 🚀 Command Line Usage
```bash
# Open a RAW file directly
python pqwave.py simulation.raw

# Show version information
python pqwave.py --version

# Display help
python pqwave.py --help
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `raw_file` | SPICE raw file to open (optional) |
| `--version`, `-v` | Show version and exit |
| `--test` | Run test suites and exit |
| `--debug` | Enable debug-level logging (most verbose) |
| `--verbose` | Enable info-level logging (user feedback) |
| `--quiet` | Suppress all output except errors |
| `--log-file FILE` | Write logs to specified file |
| `--xschem-port PORT` | TCP port for xschem integration server (default: 2026) |
| `--no-xschem-server` | Disable xschem integration server |
| `--xschem-send COMMAND` | Send command to existing xschem server and exit |

**Logging level priority**: `--debug` > `--verbose` > default (WARNING) > `--quiet` (ERROR only)

### Examples

```bash
# Run all tests
python pqwave.py --test

# Open a file with verbose logging to see user feedback messages
python pqwave.py --verbose simulation.raw

# Enable full debug output for troubleshooting
python pqwave.py --debug simulation.raw

# Suppress all non-error output for clean terminal
python pqwave.py --quiet simulation.raw

# Write logs to a file while running GUI
python pqwave.py --debug --log-file pqwave.log simulation.raw
```

### Xschem Integration Examples

```bash
# Start pqwave with xschem server on default port
pqwave --xschem-port 2026

# Start pqwave with xschem server disabled
pqwave --no-xschem-server simulation.raw

# Send command to existing pqwave server
pqwave --xschem-send "table_set /path/to/sim.raw"
```

### Running Tests

```bash
# Run all tests via --test flag
python pqwave.py --test

# Run tests with verbose output
python pqwave.py --test --verbose

# Run tests with debug output
python pqwave.py --test --debug
```

Test results are displayed with pass/fail status for each test file, followed by a summary.

### Basic Workflow
1. **Open File**: Use File → Open or command line
2. **Select Dataset**: Choose from available simulation runs
3. **Choose Variable**: Select from Vector combo box
4. **Set X-Axis**: Click X button to set X-axis variable
5. **Add Traces**: Click Y1 or Y2 to add traces
6. **Adjust View**: Use logarithmic scale or manual ranges as needed

## 🧪 Qucs-S Integration

pqwave integrates with [Qucs-S](https://github.com/ra3xdh/qucs_s) as an automatic waveform viewer. After one-click setup, every simulation you run in Qucs-S opens its results in pqwave — with traceable output files in a `simulation/` directory next to your schematic.

**Key features:**
- **Zero-config simulation hook**: No C++ changes to Qucs-S — uses the existing "Ngspice executable" setting
- **Schematic-traceable outputs**: `bridge.sch` → `simulation/bridge.cir` → `simulation/bridge.tran1.raw`
- **Non-invasive**: Qucs-S's built-in diagrams continue to work normally

**Quick setup:**
1. In pqwave: **File → Qucs-S Bridge → Connect** → OK
2. In Qucs-S: simulate any schematic — pqwave opens automatically

Or via CLI: `pqwave --setup-qucs-integration`

For details, troubleshooting, and manual setup, see [Qucs-S Integration Guide](docs/qucs/user-guide.md).

## 📡 Xschem Integration

pqwave integrates with [xschem](https://xschem.sourceforge.io/) schematic editor as an external waveform viewer. With proper configuration, you can click nets in xschem and send them directly to pqwave for visualization.

**Key features:**
- **Seamless integration**: Appears in xschem's viewer selection dialog (Alt+G)
- **Single-instance server**: Only one pqwave server runs, preventing multiple windows
- **Advanced protocol**: Supports both GAW-style commands and JSON for back-annotation
- **Color-coded traces**: Nets are plotted with distinct colors matching xschem highlighting

**Quick setup:**
1. Add pqwave to `sim(spicewave)` array in your `xschemrc` file
2. Restart xschem
3. Select nets and press Alt+G to choose "pqwave viewer"

For configuration instructions and advanced features like back-annotation, see the [Xschem Bridge](docs/xschem/) documentation and the `XschemCrossProbeClient` class in `pqwave/bridge/xschem/cross_probe.py`.

## 🔧 Architecture

```
pqwave/
├── __init__.py              # package exports (lazy, PEP 562), __version__
├── _version.py              # single source of truth for the version string
├── main.py                  # CLI entry point (argparse, logging, bridges)
├── logging_config.py        # standard logging configuration
├── test_runner.py           # --test : runs each test file under pytest, isolated
├── models/                  # RawFile, Dataset/Variable, Trace, ExprEvaluator,
│                            # ApplicationState, raw_converter, mc_collection,
│                            # vcdfile, fst_adapter, ghw_adapter
├── analysis/                # pure NumPy engines: bode, nyquist, smith, polar,
│                            # histogram, correlation, power_analyzer,
│                            # worst_case, multi_run
├── ui/                      # Qt widgets: MainWindow, PlotWidget, PanelGrid,
│                            # TraceManager, AxisManager, dialogs, REPL
├── bridge/                  # EDA tool integrations
│   ├── xschem/              #   TCP server, cross-probe, control bar, file watcher
│   ├── kicad/               #   IPC API bridge + control bar
│   ├── lepton/              #   Scheme server + cross-probe
│   ├── qucs_s/              #   one-click waveform-viewer hook
│   └── qspice/              #   QSPICE launcher / .qsch handling
├── digital/                 # VCD, eye diagram, bus slicing, threshold config
├── measure/                 # .meas script parser and measure engine
├── session/                 # SessionAPI: Qt-free orchestrator (@api_command)
├── llm/                     # natural-language → command translation
├── templates/               # view-template save/apply
├── utils/                   # ColorManager, LogAxisItem, ThrottledPlotItem, …
└── tests/                   # the test suite (~70 files, ~950 tests)
```

Dependency direction is one-way: **ui → analysis / models / digital / session → utils**.
`models/`, `analysis/` and `session/` stay Qt-free so they work headless and in the REPL.

Simulation result files and the larger performance captures live in the top-level
`tests/` directory (git-ignored, except the small fixtures the suite needs); the
Python test suite itself is `pqwave/tests/`.

## 🧪 Running the tests

```bash
pytest                       # whole suite (testpaths points at pqwave/tests/)
pytest pqwave/tests/test_bode.py -q
python pqwave.py --test      # each test file in its own subprocess
```

`pqwave/tests/conftest.py` provides the single QApplication the suite shares and
resets the `ApplicationState` / `WindowRegistry` singletons between tests, so the
whole suite runs in one process. Bridge tests that need a TCP socket skip with an
explicit reason where binding is not permitted.
