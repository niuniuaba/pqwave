# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph

![Version](https://img.shields.io/badge/version-0.2.2.0-blue)
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
git clone https://github.com/yourname/pqwave.git

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

### Basic Workflow
1. **Open File**: Use File → Open or command line
2. **Select Dataset**: Choose from available simulation runs
3. **Choose Variable**: Select from Vector combo box
4. **Set X-Axis**: Click X button to set X-axis variable
5. **Add Traces**: Click Y1 or Y2 to add traces
6. **Adjust View**: Use logarithmic scale or manual ranges as needed

## 🔧 Architecture  

```
pqwave/
├── __init__.py              # Package exports, version
├── main.py                  # Entry point (minimal)
├── models/                  # Data models and business logic
│   ├── __init__.py
│   ├── dataset.py          # Dataset, Variable, Trace classes
│   ├── expression.py       # ExprEvaluator (moved from main)
│   ├── state.py           # ApplicationState singleton
│   └── rawfile.py         # RawFile (moved from main)
├── ui/                     # UI components
│   ├── __init__.py
│   ├── main_window.py     # MainWindow (replaces WaveViewer)
│   ├── plot_widget.py     # Enhanced PlotWidget with cursor support
│   ├── control_panel.py   # Dataset/vector/trace controls
│   ├── menu_manager.py    # Menu and toolbar management
│   ├── trace_manager.py   # Trace lifecycle and styling
│   └── axis_manager.py    # Axis configuration and scaling
├── utils/                  # Utilities
│   ├── __init__.py
│   ├── colors.py          # Color management
│   ├── log_axis.py        # LogAxisItem (moved from main)
│   └── socket_client.py   # Xschem socket communication
├── communication/          # Communication layer
│   ├── __init__.py
│   ├── xschem_client.py   # Xschem protocol implementation
│   └── socket_server.py   # Optional local server
└── tests/                 # Test suite
    ├── __init__.py
    ├── test_models.py
    ├── test_ui.py
    └── test_utils.py
```
