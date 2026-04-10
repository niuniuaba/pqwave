# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph
## CHANGELOG.md

### 🔧 v0.2.1.1
- Legend formatted to show variable-Y-axis connection
- Add Open New File from menu
- Add trace properties edit (color, line width)
 
### 🔧 v0.2.1 
- Added X/Y data length check
- Added command line argument support: python pqwave.py name.raw
- Improved log axis tick display: 10^exponent format with superscript exponents
- Disabled autoSIPrefix for log axis mode (no scale factor in axis label)
- UI layout redesign: merged X and Y combos into single Vector combo
- Two-row layout: Dataset/Vector combos + Add Trace with X/Y1/Y2 buttons
- Fixed X-axis variable setting and data range issues
- Enhanced trace expression handling with quote support

### 🔧 v0.1.0 initial release
- multiple spice raw (ngspice/xyce, ltspice, qspice .qraw) 
- Infix expressions
- Auto scale and manual range adjustment
- Logarithmic Y axis
- Scientific notation display


