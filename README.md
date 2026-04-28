# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph

![Version](https://img.shields.io/badge/version-0.2.3-blue)
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

For complete configuration instructions and advanced features like back-annotation, see [Xschem Integration Documentation](docs/xschem_integration.md).

## 🔧 Architecture  

```
pqwave/
├── __init__.py              # Package exports, version
├── main.py                  # CLI entry point (argparse, logging, test runner)
├── logging_config.py        # Standard logging configuration
├── test_runner.py           # Test discovery and execution engine
├── models/                  # Data models and business logic
│   ├── __init__.py
│   ├── dataset.py           # Dataset class
│   ├── expression.py        # ExprEvaluator for math expressions
│   ├── rawfile.py           # RawFile parser for SPICE formats
│   ├── state.py             # ApplicationState singleton
│   └── trace.py             # Trace data model
├── ui/                      # UI components
│   ├── __init__.py
│   ├── main_window.py       # MainWindow (composes all UI components)
│   ├── plot_widget.py       # Enhanced PlotWidget with dual Y-axis & cursors
│   ├── control_panel.py     # Dataset/vector/trace controls
│   ├── menu_manager.py      # Menu bar and toolbar management
│   ├── trace_manager.py     # Trace lifecycle, color assignment, legend
│   ├── axis_manager.py      # Axis configuration, scaling, log mode
│   └── settings_widget.py   # Application settings dialog
├── utils/                   # Utilities
│   ├── __init__.py
│   ├── colors.py            # Color management for traces
│   └── log_axis.py          # LogAxisItem for logarithmic axis display
├── communication/           # Xschem integration layer
│   ├── __init__.py
│   ├── xschem_server.py     # TCP server for xschem commands
│   ├── command_handler.py   # Command parsing and signal emission
│   └── window_registry.py   # Window management for multi-instance support
└── tests/                   # Test suite (16+ test files)
    ├── __init__.py
    ├── test_basic.py
    ├── test_expr_evaluator.py
    ├── test_imports.py
    ├── test_instantiate.py
    ├── test_integration.py
    ├── test_log_axis.py
    ├── test_models.py
    ├── test_mouse_coords.py
    ├── test_mouse_gui.py
    ├── test_plot_widget_mouse.py
    ├── test_rawfile.py
    ├── test_settings.py
    ├── test_trace_manager.py
    ├── test_trace_prop.py
    ├── test_trace_prop_fixed.py
    └── test_ui_integration.py
```
