# pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph

![Version](https://img.shields.io/badge/version-0.2.1.1-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

Wave Viewer is a professional waveform visualization tool for SPICE simulation data. It supports multiple RAW file formats and provides advanced features for circuit analysis and data exploration.

## 📋 Table of Contents
- [Features](#-features)
- [Screenshots](#-screenshots)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage Guide](#-usage-guide)
- [Technical Details](#-technical-details)
- [Version History](#-version-history)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

### 🎯 Core Capabilities
- **Multi-format Support**: ngspice/xyce, ltspice, qspice .qraw files
- **Dual Y-Axis**: Independent Y1 and Y2 axes with shared X-axis
- **Mathematical Expressions**: Infix notation with built-in functions
- **Logarithmic Scales**: Professional log axis display with superscript exponents
- **Auto/Manual Scaling**: Intelligent range adjustment
- **Multiple Traces**: Simultaneous display of multiple variables

### 🖥️ User Interface
- **Two-Row Layout**: Compact and efficient interface
- **Unified Vector Selection**: Single combo box for all variables
- **Expression Support**: Quoted variables and complex expressions
- **System Theme**: Automatic adaptation to system color scheme
- **Clear Legend**: Automatic trace labeling

### 🔧 Technical Excellence
- **Robust Data Validation**: X/Y length consistency checks
- **Professional Log Display**: 10^exponent format with superscripts
- **Error Handling**: Defensive programming with clear error messages
- **High Performance**: PyQtGraph-based rendering
- **Command Line Support**: Direct file opening from terminal

## 📸 Screenshots

### Main Interface
```
┌─────────────────────────────────────────────────────────────┐
│ Dataset: [Transient Analysis]     Vector: [v(out)]          │
│ Add Trace: ["v(out)"]             [X] [Y1] [Y2]             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    Waveform Display Area                    │
│                                                             │
│  Y1: v(out) ──────────────●─────────────●─────────────●    │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Logarithmic Scale Display
- **Linear**: 0.1, 1.0, 10.0, 100.0
- **Logarithmic**: 10⁻¹, 10⁰, 10¹, 10² (with superscript exponents)

## 📦 Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Dependencies
```bash
# Core dependencies
pip install numpy pyqtgraph PyQt6

# Optional: For additional RAW file support
pip install spicelib
```

### Installation Methods

#### Method 1: Direct Run
```bash
cd /path/to/pqwave
python pqwave.py
```

#### Method 2: System Installation (Optional)
```bash
# Make executable
chmod +x pqwave.py
# Create symbolic link
sudo ln -s /path/to/pqwave/pqwave.py /usr/local/bin/pqwave
```

## 🚀 Quick Start

### Command Line Usage
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

## 📖 Usage Guide

### Interface Overview

#### Top Controls (Two Rows)
```
Row 1: Dataset: [Dropdown]     Vector: [Dropdown]
Row 2: Add Trace: [Text Input] [X] [Y1] [Y2]
```

#### Control Descriptions
- **Dataset**: Select simulation dataset (transient, AC, DC, etc.)
- **Vector**: Choose any variable from the simulation
- **Add Trace**: Expression input (supports quotes and multiple variables)
- **X Button**: Set selected variable as X-axis
- **Y1 Button**: Add trace to left Y-axis
- **Y2 Button**: Add trace to right Y-axis

### Expression Syntax

#### Basic Variables
```python
"v(out)"      # Voltage at node 'out'
"i(r1)"       # Current through resistor r1
"time"        # Time variable (for transient analysis)
```

#### Mathematical Expressions
```python
"v(out)*1000"                 # Multiplication
"v(out)/v(in)"                # Division
"abs(v(out))"                 # Absolute value
"log10(v(out))"               # Base-10 logarithm
"sin(2*pi*frequency*time)"    # Trigonometric function
```

#### Multiple Variables
```python
"v(out)" "v(in)"              # Two separate traces
"v(out)" "v(out)*0.5"         # Original and scaled
```

### Logarithmic Scales

#### Enabling Log Mode
1. Right-click on Y-axis
2. Select "Logarithmic Scale" from context menu
3. Data automatically transforms to log10 space

#### Log Scale Features
- **Professional Display**: 10^exponent format (e.g., 10⁻³, 10⁰, 10³)
- **Superscript Exponents**: Clean mathematical notation
- **Non-positive Handling**: Automatic adjustment for log(≤0)
- **No Scale Factor**: Clean axis labels without (x1eN) notation

### Dual Y-Axis Usage

#### Adding Y2 Traces
1. Select variable from Vector combo
2. Click Y2 button
3. Right Y-axis automatically appears
4. Trace appears in different color

#### Y1/Y2 Coordination
- **Shared X-axis**: Both axes use same X data
- **Independent Scaling**: Each Y-axis auto-scales independently
- **Color Differentiation**: Automatic color assignment

## 🔧 Technical Details

### Architecture
```
pqwave.py (2293 lines)
├── LogAxisItem    # Custom logarithmic axis display
├── RawFile        # SPICE RAW file parser
├── ExprEvaluator  # Mathematical expression evaluator
└── WaveViewer     # Main application and UI
```

### Key Classes

#### 1. LogAxisItem
- Custom AxisItem for professional log scale display
- Shows actual values instead of exponents
- Supports superscript exponent formatting
- Disables autoSIPrefix in log mode

#### 2. RawFile
- Multi-format SPICE RAW file parser
- Uses spicelib for file reading
- Extracts variables and datasets
- Handles complex and real data types

#### 3. ExprEvaluator
- Token-based expression parser
- Supports infix notation with operator precedence
- Built-in mathematical functions
- Variable substitution and evaluation

#### 4. WaveViewer
- PyQt6-based main application
- Dual Y-axis viewbox management
- Trace and legend handling
- UI event processing

### Data Flow
```
RAW File → RawFile.parse() → Variable List → User Selection → 
ExprEvaluator → Data Arrays → Length Validation → 
Log Transformation → PyQtGraph Plotting
```

### Error Handling
- **X/Y Length Check**: Ensures data consistency before plotting
- **Non-positive Values**: Handles log10(≤0) with intelligent replacement
- **Missing Variables**: Clear error messages for invalid selections
- **Expression Errors**: Detailed parsing and evaluation feedback

## 📈 Version History

### Version 0.2.1.1 (Current)
- Legend display format changed to "trace_name @ Yx" format
- File menu improvements: "Open" renamed to "Open Raw File", added "Open New Window"
- Edit menu improvements: "Edit Trace Aliases" upgraded to "Edit Trace Properties" with Color and Line width controls
- Fixed log mode auto range calculation issues
- Fixed trace disappearance when switching from log to linear mode

### Version 0.2.1
- Added X/Y data length consistency check
- Added command line argument support
- Improved log axis tick display (10^exponent with superscripts)
- Disabled autoSIPrefix for log axis mode
- UI layout redesign (merged X/Y combos, two-row layout)
- Fixed X-axis variable setting and data range issues
- Enhanced trace expression handling with quote support

### Version 0.2.0
- Fixed Y1/Y2 axis tick display consistency
- Improved non-positive value handling for log scale

### Version 0.1.0
- Multi-format SPICE RAW file support
- Infix expression evaluation
- Auto and manual range adjustment
- Logarithmic Y-axis
- Scientific notation display

## 🤝 Contributing

### Development Setup
```bash
# Clone repository
git clone https://github.com/niuniuaba/pqwave.git
cd pqwave

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install development dependencies
pip install -r requirements.txt
```

### Code Structure
- Follow existing code style and conventions
- Add comprehensive docstrings for new functions
- Include error handling and validation
- Update version history in file header

### Testing
- Test with various SPICE RAW file formats
- Verify logarithmic scale functionality
- Check expression evaluation accuracy
- Test edge cases and error conditions

### Pull Request Process
1. Fork the repository
2. Create a feature branch
3. Make changes with clear commit messages
4. Update documentation as needed
5. Submit pull request with description

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **PyQtGraph Team**: For the excellent plotting library
- **SPICE Community**: For simulation standards and formats
- **Contributors**: All who have helped improve Wave Viewer

## 📞 Support

### Issues and Questions
- **GitHub Issues**: [Report bugs or request features](https://github.com/niuniuaba/pqwave/issues)
- **Documentation**: Check this README and code comments
- **Examples**: See the `examples/` directory for sample files

### Getting Help
1. Check the [Troubleshooting](#-troubleshooting) section below
2. Search existing issues
3. Create a new issue with detailed information

## 🔍 Troubleshooting

### Common Issues

#### 1. "No module named 'spicelib'"
```bash
pip install spicelib
# or run without spicelib (limited functionality)
```

#### 2. "X and Y data length mismatch"
- Ensure you're using variables from the same dataset
- Check that expressions evaluate to correct length
- Verify RAW file integrity

#### 3. Logarithmic scale shows incorrect values
- Right-click axis and ensure "Logarithmic Scale" is checked
- Check terminal for transformation messages
- Verify data doesn't contain only non-positive values

#### 4. Y2 axis not appearing
- Ensure you're clicking the Y2 button (not Y1)
- Check that right axis is enabled in View menu
- Verify trace was successfully added (check legend)

### Performance Tips
- Use simpler expressions for large datasets
- Close unused traces to free memory
- Adjust plot resolution in View menu if needed

---

**Wave Viewer** - Making SPICE data visualization simple and powerful since Version 0.1.0