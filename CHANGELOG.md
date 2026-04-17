# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph
## CHANGELOG.md

###  v0.2.2 — CPU performance optimization
- **PlotDataItem → PlotCurveItem**: Pre-downsample to 1600pts at trace creation time using peak method (min/max per bin). Eliminates per-paint autoDownsample rebuild, updateItems, and dataBounds nanmin/nanmax overhead. **18x faster** per paint event
- **_StaticCurveItem**: Custom PlotCurveItem subclass that permanently caches boundingRect and skips viewTransformChanged invalidation during pan/zoom. **22% faster** by avoiding redundant bounds recalculation
- **Segmented line mode**: `setSegmentedLineMode('on')` uses `drawLines()` instead of `drawPath()`, reducing QPainter rendering overhead
- **ViewBox translateBy/scaleBy throttle**: Coalesce rapid pan/zoom calls into single paint every 30ms. **2.6x fewer paints** during real mouse drag
- **BoundingRectViewportUpdate**: Reduced repaint region size for better performance
- **Removed debug logging**: Stripped `logger.debug` from hot-path functions (`_on_mouse_moved`, `LogAxisItem.tickStrings/setLogMode`)
- **Results** (rc_100M.raw, 22 traces, 636K pts each): CPU during mouse interaction dropped from **120-140% to ~5-10%**, matching xschem performance
- **Benchmark** (200 translateBy events): Before 0.703s → After 0.009s (**78x faster** in tight loop)
- **Log mode bug fixes**:
  - Fixed double-log corruption: removed `ViewBox.setLogMode()` calls — data is pre-transformed by TraceManager, ViewBox must stay in linear mode
  - Fixed incorrect tick display when adding new traces in log mode: `_create_plot_item` now applies log10 transform when log mode is already enabled
  - Fixed `_StaticCurveItem` boundingRect cache not invalidating on `setData()` during log mode toggle

###  v0.2.2
- **Float32 migration**: all in-memory real data migrated from float64 to float32, complex data from complex128 to complex64 (~2× memory reduction for data matrix). LTspice stores float32 on disk; xschem offers float option — double precision is overkill for transient/DC SPICE data
- **Release spicelib cache**: set `self.raw_data = None` after parse completes, freeing ~2.4 GB for rc_ltspice.raw. All data retained in memmap/column_stack matrix
- **Zero-copy Variable access**: Dataset Variables now reference columns from the memmap/column_stack matrix directly (numpy views), sharing a single underlying memory allocation instead of creating per-variable copies
- **LRU cache on get_variable_data()**: repeated calls for the same variable return the identical numpy view object, eliminating redundant allocations
- **Updated profiling scripts**: `memory_profile.py`, `memory_profile_light.py`, and `cpu_profile.py` rewritten for the optimized pipeline — removed spicelib-internal profiling, added Dataset/cache verification stages, general-purpose for any raw file

###  v0.2.2
- Added viewbox theme selector (Dark/Light) in Plot Settings: Dark mode uses pure black background (#000000) with light foreground (#E0E0E0), Light mode uses white background with black foreground. Theme applies to viewbox, axis pens, grid lines, axis labels, title text, mark scatter, and mark tooltips
- Removed system-theme-following behavior: plot colors are no longer tied to QApplication.palette()
- Added "Convert Raw Data..." under File menu: convert loaded raw data between SPICE/ngspice, LTspice, and QSPICE formats via a dialog with format selection and save-to-file
- Fixed source format detection in Convert dialog: now uses spicelib's `raw_data.dialect` property instead of unreliable file-extension-based heuristics
- **Known Limitation — QSPICE AC file conversion**: spicelib always treats the first variable in QSPICE complex/AC files as the frequency axis (stored as `float64`, not `complex128`). This means converting AC files to QSPICE format may produce incorrect data if the first variable is not a frequency axis. Typical AC analysis files (with frequency as the first variable) convert correctly. This is a spicelib design choice, not a bug in pqwave.
- Fixed Issue #8: Mark Data widget now reappears when placing new marks after closing it via window close button; previous marks are preserved
- Fixed Issue #9: QSPICE special characters (Greek letters α β γ, dagger †, etc.) in variable names now display correctly by parsing raw file bytes directly instead of relying on spicelib's character-by-character header reading
- **Memory and CPU optimization**: Fixed O(N×filesize) memory and I/O in RawFile.parse() by calling spicelib's `read_trace_data()` once with all variable names instead of N individual `get_trace()` calls. In NormalAccess mode (QSPICE default), each `get_trace()` was re-reading the entire binary data section, accumulating ~3.9 GB of intermediate buffers for a 120 MB file. After fix: RSS reduced from ~4.4 GB to ~689 MB (6.4×), parse CPU time from 1.9s to 0.5s (3.8×). Added reusable memory and CPU profiling scripts (`pqwave/tests/memory_profile.py`, `pqwave/tests/cpu_profile.py`).

###  v0.2.2
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


