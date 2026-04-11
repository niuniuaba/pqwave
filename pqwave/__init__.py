"""
pqwave - A Wave Viewer for SPICE raw data using spicelib and PyQtGraph
"""

__version__ = "0.2.2.0"
__author__ = "niuniuaba"

# Export main classes and functions (conditional imports)
try:
    from .models.rawfile import RawFile
    HAS_RAWFILE = True
except ImportError:
    RawFile = None
    HAS_RAWFILE = False

try:
    from .models.expression import ExprEvaluator
    HAS_EXPR = True
except ImportError:
    ExprEvaluator = None
    HAS_EXPR = False

# Import MainWindow from ui module
try:
    from .ui.main_window import MainWindow
    HAS_MAINWINDOW = True
except ImportError:
    MainWindow = None
    HAS_MAINWINDOW = False

# Import main function from main module
try:
    from .main import main
    HAS_MAIN = True
except ImportError:
    main = None
    HAS_MAIN = False

# Define __all__ based on what's available
__all__ = ['__version__', '__author__']
if HAS_RAWFILE:
    __all__.append('RawFile')
if HAS_EXPR:
    __all__.append('ExprEvaluator')
if HAS_MAINWINDOW:
    __all__.append('MainWindow')
if HAS_MAIN:
    __all__.append('main')