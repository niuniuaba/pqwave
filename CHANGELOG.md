# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph
## CHANGELOG.md

###  v0.2.2.0
- Restructured project from monolithic to modular architecture
- Added tooltips for trace expression input: "Add Trace:" label, expression field, and X/Y1/Y2 buttons show "Expressions must be quoted inside \"\" or ''" on hover
- Implemented trace property editor with color and line width selection
- Implemented Settings widget according to specifications in settings_widget.md
- Updated version to 0.2.2.0 across all package files
- Modular package structure:

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

###  v0.2.1.2
- Added View menu with toggleable toolbar/status bar, grid toggle, zoom controls
- Added toolbar with buttons: Open File, Open New Window, zoom in/out/full, auto-range X/Y axes, zoom box, grid toggle
- Added status bar showing mouse coordinates and active dataset
- Fixed grid toggle ValueError by properly using pyqtgraph's showGrid() method
- Added mouse coordinate tracking
- Added zoom methods (zoom in/out/fit)
- Added zoom box mode
- Synchronized grid toggle state between menu, toolbar, and context menu

###  v0.2.1.1
- Legend formatted to show variable-Y-axis connection
- Add Open New File from menu
- Add trace properties edit (color, line width)
 
###  v0.2.1 
- Added X/Y data length check
- Added command line argument support: python pqwave.py name.raw
- Improved log axis tick display: 10^exponent format with superscript exponents
- Disabled autoSIPrefix for log axis mode (no scale factor in axis label)
- UI layout redesign: merged X and Y combos into single Vector combo
- Two-row layout: Dataset/Vector combos + Add Trace with X/Y1/Y2 buttons
- Fixed X-axis variable setting and data range issues
- Enhanced trace expression handling with quote support

###  v0.1.0 initial release
- multiple spice raw (ngspice/xyce, ltspice, qspice .qraw) 
- Infix expressions
- Auto scale and manual range adjustment
- Logarithmic Y axis
- Scientific notation display


