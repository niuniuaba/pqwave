#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pqwave - a Wave Viewer for SPICE raw data using spicelib and PyQtGraph
- History: CHANGELOG.md
- TODO: TODO.md

Version 0.2.1.1
- Legend formatted to show variable-Y-axis connection
- Add Open New File from menu
- Add trace properties edit (color, line width)

Version 0.2.1
- Added X/Y data length check
- Added command line argument support: python pqwave.py name.raw
- Improved log axis tick display: 10^exponent format with superscript exponents
- Disabled autoSIPrefix for log axis mode (no scale factor in axis label)
- UI layout redesign: merged X and Y combos into single Vector combo
- Two-row layout: Dataset/Vector combos + Add Trace with X/Y1/Y2 buttons
- Fixed X-axis variable setting and data range issues
- Enhanced trace expression handling with quote support

Version 0.2.0
- Fixed Y1/Y2 axis tick display consistency
- Improved non-positive value handling for log scale

Version 0.1.0  
Supports:
- multiple spice raw (ngspice/xyce, ltspice, qspice .qraw) 
- Infix expressions
- Auto scale and manual range adjustment
- Logarithmic Y axis
- Scientific notation display
"""

import sys
import re
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMenuBar, QMenu,
    QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton, QLineEdit,
    QLabel, QCheckBox, QDoubleSpinBox, QGridLayout, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
from pyqtgraph import AxisItem

class LogAxisItem(AxisItem):
    """Custom AxisItem for log scale that shows actual values instead of exponents"""
    def __init__(self, orientation='left', log_mode_changed_callback=None, **kwargs):
        super().__init__(orientation, **kwargs)
        self.log_mode = False
        self.log_mode_changed_callback = log_mode_changed_callback
        # Initially enable auto SI prefix (for linear mode)
        # It will be disabled when log mode is enabled
        self.enableAutoSIPrefix(True)



    
    def setLogMode(self, x=None, y=None):
        """Set log mode for this axis
        
        Args:
            x: Whether X-axis is in log mode (for bottom axis)
            y: Whether Y-axis is in log mode (for left/right axis)
        """
        print(f"\n=== LogAxisItem.setLogMode called: orientation={self.orientation}, x={x}, y={y} ===")
        
        # Store old log mode for comparison
        old_log_mode = self.log_mode
        
        # Update log_mode based on orientation
        if self.orientation in ['left', 'right'] and y is not None:
            self.log_mode = y
            print(f"  Updated log_mode from {old_log_mode} to: {y} (Y-axis)")
        elif self.orientation == 'bottom' and x is not None:
            self.log_mode = x
            print(f"  Updated log_mode from {old_log_mode} to: {x} (X-axis)")
        
        # Enable/disable auto SI prefix based on log mode
        # For log mode, disable auto SI prefix (we show exponents directly)
        # For linear mode, enable auto SI prefix for large/small numbers
        new_mode = y if self.orientation in ['left', 'right'] else x
        if new_mode is not None:
            if new_mode:  # Log mode
                self.enableAutoSIPrefix(False)
                print(f"  Disabled auto SI prefix for log mode")
            else:  # Linear mode
                self.enableAutoSIPrefix(True)
                print(f"  Enabled auto SI prefix for linear mode")
        
        # Also call parent's setLogMode to ensure pyqtgraph internal state is updated
        try:
            super().setLogMode(x=x, y=y)
            print(f"  Called parent setLogMode")
        except Exception as e:
            print(f"  Parent setLogMode failed: {e}")
        
        # If log mode changed, call callback if provided
        if new_mode is not None and new_mode != old_log_mode:
            print(f"  Log mode changed from {old_log_mode} to {new_mode}")
            if self.log_mode_changed_callback:
                print(f"  Calling log_mode_changed_callback with orientation={self.orientation}, log_mode={new_mode}")
                try:
                    self.log_mode_changed_callback(self.orientation, new_mode)
                except Exception as e:
                    print(f"  Callback failed: {e}")
    
    def tickStrings(self, values, scale, spacing):
        """Convert tick values to strings"""
        print(f"\n=== LogAxisItem.tickStrings ===")
        print(f"  orientation: {self.orientation}")
        print(f"  log_mode: {self.log_mode}")
        print(f"  values: {values}")
        
        strings = []
        for v in values:
            if self.log_mode:
                # For log scale, show 10^v with superscript exponent
                print(f"  Processing value v={v}")
                
                # Format exponent with superscript
                formatted = self._format_exponent_with_superscript(v)
                strings.append(formatted)
                print(f"    Formatted as: '{formatted}'")
            else:
                # For linear scale, use default formatting
                default_str = super().tickStrings([v], scale, spacing)[0]
                strings.append(default_str)
                print(f"  Linear mode: v={v} -> '{default_str}'")
        
        print(f"  Returning strings: {strings}")
        return strings
    
    def _format_exponent_with_superscript(self, exponent):
        """Format exponent with superscript characters
        
        Examples:
        1.0 -> "10¹"
        2.0 -> "10²"
        -1.0 -> "10⁻¹"
        1.5 -> "10¹·⁵"
        -2.3 -> "10⁻²·³"
        """
        # Round to reasonable precision
        if abs(exponent) < 0.001:
            exponent_str = "0"
        elif abs(exponent - round(exponent)) < 0.001:
            # Integer exponent
            exponent_str = str(int(round(exponent)))
        else:
            # Decimal exponent, round to 1 decimal place
            exponent_str = f"{exponent:.1f}"
        
        # Convert to superscript
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
            '-': '⁻', '.': '·'
        }
        
        superscript_str = ''.join(superscript_map.get(ch, ch) for ch in exponent_str)
        
        return f"10{superscript_str}"

class RawFile:
    """Parse NGSPICE raw files using spicelib"""
    def __init__(self, filename):
        self.filename = filename
        self.datasets = []
        self.raw_data = None
        self.parse()
    
    def parse(self):
        """Parse the raw file using spicelib"""
        try:
            from spicelib import RawRead
            self.raw_data = RawRead(self.filename)
            
            # Get raw properties from spicelib
            raw_props = self.raw_data.get_raw_properties()
            
            # Create a dataset structure compatible with the existing code
            dataset = {
                'title': raw_props.get('Title', ''),
                'date': raw_props.get('Date', ''),
                'plotname': raw_props.get('Plotname', ''),
                'flags': raw_props.get('Flags', ''),
                'variables': [],
                'data': None
            }
            
            # Get trace names
            trace_names = self.raw_data.get_trace_names()
            
            # Create variables list
            variables = []
            for i, name in enumerate(trace_names):
                var = {
                    'index': i,
                    'name': name,
                    'type': 'voltage' if name.startswith('v(') else 'current' if name.startswith('i(') else 'time' if name == 'time' else 'unknown'
                }
                variables.append(var)
            
            # Get data for all traces
            data_list = []
            valid_variables = []
            for i, name in enumerate(trace_names):
                try:
                    trace = self.raw_data.get_trace(name)
                    if trace is not None:
                        # Convert TraceRead object to numpy array
                        try:
                            if hasattr(trace, 'get_wave'):
                                data = trace.get_wave()
                            else:
                                data = np.array(trace)
                            data_list.append(data)
                            # Add to valid variables only if we can get the data
                            var = {
                                'index': len(valid_variables),
                                'name': name,
                                'type': 'voltage' if name.startswith('v(') else 'current' if name.startswith('i(') else 'time' if name == 'time' else 'frequency' if name.lower() in ['freq', 'frequency', 'hz'] else 'unknown'
                            }
                            valid_variables.append(var)
                        except Exception as e:
                            print(f"Warning: Could not convert trace {name} to numpy array: {e}")
                except Exception as e:
                    print(f"Warning: Could not get trace {name}: {e}")
                    # Skip this trace if we can't get it (e.g., alias not supported)
                    continue
            
            # Convert to numpy array (each column is a trace)
            if data_list:
                data = np.column_stack(data_list)
            else:
                data = np.array([])
            
            dataset['variables'] = valid_variables
            dataset['data'] = data
            self.datasets.append(dataset)
            
        except Exception as e:
            raise Exception(f"Error parsing file {self.filename}: {e}")
    
    def get_variable_names(self, dataset_idx=0):
        """Get variable names for a dataset"""
        if dataset_idx < len(self.datasets):
            var_names = [var['name'] for var in self.datasets[dataset_idx]['variables']]
            # Add derived variables for complex vectors
            derived_vars = []
            for var_name in var_names:
                # Check if this is a complex vector (based on plotname or flags)
                dataset = self.datasets[dataset_idx]
                plotname = dataset.get('plotname', '').lower()
                flags = dataset.get('flags', '').lower()
                if 'ac' in plotname or 'complex' in flags:
                    # Add derived variables
                    derived_vars.extend([
                        f'mag({var_name})',
                        f'real({var_name})',
                        f'imag({var_name})',
                        f'ph({var_name})'
                    ])
            return var_names + derived_vars
        return []
    
    def get_variable_data(self, var_name, dataset_idx=0):
        """Get data for a variable"""
        if dataset_idx < len(self.datasets) and self.raw_data:
            # Check if it's a derived variable for complex vector
            if var_name.startswith('mag(') and var_name.endswith(')'):
                base_var = var_name[4:-1]
                return self._get_complex_magnitude(base_var, dataset_idx)
            elif var_name.startswith('real(') and var_name.endswith(')'):
                base_var = var_name[5:-1]
                return self._get_complex_real(base_var, dataset_idx)
            elif var_name.startswith('imag(') and var_name.endswith(')'):
                base_var = var_name[5:-1]
                return self._get_complex_imag(base_var, dataset_idx)
            elif var_name.startswith('ph(') and var_name.endswith(')'):
                base_var = var_name[3:-1]
                return self._get_complex_phase(base_var, dataset_idx)
            
            # Regular variable - use spicelib's get_trace method
            trace = self.raw_data.get_trace(var_name)
            if trace is not None:
                # Convert TraceRead object to numpy array
                try:
                    # Try to get the wave data
                    if hasattr(trace, 'get_wave'):
                        data = trace.get_wave()
                        return data
                    else:
                        # Try to convert to numpy array
                        return np.array(trace)
                except Exception as e:
                    print(f"Error converting trace {var_name} to numpy array: {e}")
                    return None
        return None
    
    def _get_complex_magnitude(self, var_name, dataset_idx=0):
        """Get magnitude of complex vector"""
        if self.raw_data:
            # Try to get the trace directly
            trace = self.raw_data.get_trace(var_name)
            if trace is not None:
                # Convert to numpy array first
                data = self.get_variable_data(var_name, dataset_idx)
                if data is not None:
                    # Check if data is complex
                    if np.iscomplexobj(data):
                        return np.abs(data)
                    else:
                        # If not complex, return absolute value of real data
                        return np.abs(data)
        return None
    
    def _get_complex_real(self, var_name, dataset_idx=0):
        """Get real part of complex vector"""
        if self.raw_data:
            # Try to get the trace directly
            trace = self.raw_data.get_trace(var_name)
            if trace is not None:
                # Convert to numpy array first
                data = self.get_variable_data(var_name, dataset_idx)
                if data is not None:
                    # Check if data is complex
                    if np.iscomplexobj(data):
                        return np.real(data)
                    else:
                        # If not complex, return the data as is
                        return data
        return None
    
    def _get_complex_imag(self, var_name, dataset_idx=0):
        """Get imaginary part of complex vector"""
        if self.raw_data:
            trace = self.raw_data.get_trace(var_name)
            if trace is not None:
                # Convert to numpy array first
                data = self.get_variable_data(var_name, dataset_idx)
                if data is not None:
                    # Check if data is complex
                    if np.iscomplexobj(data):
                        return np.imag(data)
                    else:
                        # If not complex, return zeros
                        return np.zeros_like(data)
        return None
    
    def _get_complex_phase(self, var_name, dataset_idx=0):
        """Get phase of complex vector (in radians)"""
        if self.raw_data:
            trace = self.raw_data.get_trace(var_name)
            if trace is not None:
                # Convert to numpy array first
                data = self.get_variable_data(var_name, dataset_idx)
                if data is not None:
                    # Check if data is complex
                    if np.iscomplexobj(data):
                        return np.angle(data)
                    else:
                        # If not complex, return zeros
                        return np.zeros_like(data)
        return None
    
    def get_num_points(self, dataset_idx=0):
        """Get number of points in a dataset"""
        if dataset_idx < len(self.datasets) and self.raw_data:
            # Get the first trace to determine the number of points
            trace_names = self.raw_data.get_trace_names()
            if trace_names:
                trace = self.raw_data.get_trace(trace_names[0])
                if trace is not None:
                    return len(trace)
        return 0

class ExprEvaluator:
    """Infix expression evaluator for SPICE raw data"""
    
    def __init__(self, raw_file, dataset_idx):
        self.raw_file = raw_file
        self.dataset_idx = dataset_idx
        self.n_points = raw_file.get_num_points(dataset_idx)
    
    def tokenize(self, expr):
        """Tokenize expression"""
        tokens = []
        i = 0
        while i < len(expr):
            c = expr[i]
            
            if c.isspace():
                i += 1
                continue
            
            if c.isdigit() or (c == '.' and i + 1 < len(expr) and expr[i+1].isdigit()):
                start = i
                while i < len(expr) and (expr[i].isdigit() or expr[i] == '.' or expr[i] in 'eE+-'):
                    i += 1
                num_str = expr[start:i]
                val = float(num_str)
                tokens.append(('NUMBER', val))
            elif c.isalpha() or c == '_':
                start = i
                while i < len(expr) and (expr[i].isalnum() or expr[i] == '_' or expr[i] == '.'):
                    i += 1
                name = expr[start:i]
                lower = name.lower()
                
                if i < len(expr) and expr[i] == '(':
                    # Check if it's a complex-related function
                    if lower in ['real', 'imag', 'mag', 'ph']:
                        # Find the matching closing parenthesis
                        paren_count = 1
                        end = i + 1
                        while end < len(expr) and paren_count > 0:
                            if expr[end] == '(':
                                paren_count += 1
                            elif expr[end] == ')':
                                paren_count -= 1
                            end += 1
                        if paren_count == 0:
                            # Extract the entire function call as a variable
                            var_name = expr[start:end]
                            tokens.append(('VARIABLE', var_name))
                            i = end
                        else:
                            raise ValueError("Unmatched '(' in function call")
                    elif self.is_function_name(lower):
                        tokens.append(('FUNCTION', lower))
                        tokens.append(('LPAREN', None))
                        i += 1
                    elif self.is_constant_name(lower):
                        tokens.append(('CONSTANT', lower))
                    else:
                        var_start = start
                        while i < len(expr) and expr[i] != ')':
                            i += 1
                        if i >= len(expr):
                            raise ValueError("Unmatched '(' in variable name")
                        i += 1
                        var_name = expr[var_start:i]
                        tokens.append(('VARIABLE', var_name))
                else:
                    if self.is_function_name(lower):
                        tokens.append(('FUNCTION', lower))
                    elif self.is_constant_name(lower):
                        tokens.append(('CONSTANT', lower))
                    else:
                        tokens.append(('VARIABLE', name))
            elif c == '(':
                tokens.append(('LPAREN', None))
                i += 1
            elif c == ')':
                tokens.append(('RPAREN', None))
                i += 1
            elif c in '+-*/^':
                tokens.append(('OPERATOR', c))
                i += 1
            else:
                raise ValueError(f"Unexpected character: {c}")
        return tokens
    
    def is_function_name(self, name):
        """Check if name is a function"""
        functions = ['sin', 'cos', 'tan', 'abs', 'sqrt', 'log', 'log10', 'exp', 'min', 'max', 'asin', 'acos', 'atan', 'mag', 'real', 'imag', 'ph']
        return name in functions
    
    def is_constant_name(self, name):
        """Check if name is a constant"""
        constants = ['pi', 'e']
        return name in constants
    
    def evaluate(self, expr):
        """Evaluate expression"""
        tokens = self.tokenize(expr)
        pos = 0
        result, _ = self.eval_expression(tokens, pos)
        return result
    
    def eval_expression(self, tokens, pos):
        """Evaluate expression"""
        left, pos = self.eval_term(tokens, pos)
        
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR':
                op = tokens[pos][1]
                if op in '+-':
                    pos += 1
                    right, pos = self.eval_term(tokens, pos)
                    left = self.apply_op_vector(left, right, op)
                else:
                    break
            else:
                break
        return left, pos
    
    def eval_term(self, tokens, pos):
        """Evaluate term"""
        left, pos = self.eval_power(tokens, pos)
        
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR':
                op = tokens[pos][1]
                if op in '*/':
                    pos += 1
                    right, pos = self.eval_power(tokens, pos)
                    left = self.apply_op_vector(left, right, op)
                else:
                    break
            else:
                break
        return left, pos
    
    def eval_power(self, tokens, pos):
        """Evaluate power"""
        base, pos = self.eval_unary(tokens, pos)
        
        if pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '^':
                pos += 1
                exp, pos = self.eval_unary(tokens, pos)
                return self.apply_op_vector(base, exp, '^'), pos
        return base, pos
    
    def eval_unary(self, tokens, pos):
        """Evaluate unary"""
        if pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '-':
                pos += 1
                val, pos = self.eval_unary(tokens, pos)
                return -val, pos
            elif tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '+':
                pos += 1
                return self.eval_unary(tokens, pos)
        return self.eval_primary(tokens, pos)
    
    def eval_primary(self, tokens, pos):
        """Evaluate primary"""
        if pos >= len(tokens):
            raise ValueError("Unexpected end of expression")
        
        token_type, token_val = tokens[pos]
        pos += 1
        
        if token_type == 'NUMBER':
            return np.full(self.n_points, token_val), pos
        elif token_type == 'CONSTANT':
            if token_val == 'pi':
                return np.full(self.n_points, np.pi), pos
            elif token_val == 'e':
                return np.full(self.n_points, np.e), pos
            else:
                raise ValueError(f"Unknown constant: {token_val}")
        elif token_type == 'VARIABLE':
            # Get variable data directly from RawFile
            data = self.raw_file.get_variable_data(token_val, self.dataset_idx)
            if data is not None:
                if len(data) == self.n_points:
                    return data, pos
                else:
                    raise ValueError(f"Variable '{token_val}' has {len(data)} points, expected {self.n_points}")
            else:
                raise ValueError(f"Unknown variable: {token_val}")
        elif token_type == 'FUNCTION':
            arg, pos = self.eval_expression(tokens, pos)
            if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
                pos += 1
            return self.apply_function(token_val, arg), pos
        elif token_type == 'LPAREN':
            val, pos = self.eval_expression(tokens, pos)
            if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
                pos += 1
            else:
                raise ValueError("Missing closing \"")
            return val, pos
        else:
            raise ValueError(f"Unexpected token: {token_type}")
    
    def apply_op_vector(self, left, right, op):
        """Apply operator to vectors"""
        if len(left) != len(right):
            raise ValueError(f"Vector length mismatch: {len(left)} vs {len(right)}")
        
        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            if np.any(right == 0):
                raise ValueError("Division by zero")
            return left / right
        elif op == '^':
            return np.power(left, right)
        else:
            raise ValueError(f"Unknown operator: {op}")
    
    def apply_function(self, name, arg):
        """Apply function to vector"""
        if name == 'sin':
            return np.sin(arg)
        elif name == 'cos':
            return np.cos(arg)
        elif name == 'tan':
            return np.tan(arg)
        elif name == 'asin':
            return np.arcsin(arg)
        elif name == 'acos':
            return np.arccos(arg)
        elif name == 'atan':
            return np.arctan(arg)
        elif name == 'abs':
            return np.abs(arg)
        elif name == 'sqrt':
            if np.any(arg < 0):
                raise ValueError("sqrt of negative number")
            return np.sqrt(arg)
        elif name == 'log':
            if np.any(arg <= 0):
                raise ValueError("log of non-positive number")
            return np.log(arg)
        elif name == 'log10':
            if np.any(arg <= 0):
                raise ValueError("log10 of non-positive number")
            return np.log10(arg)
        elif name == 'exp':
            return np.exp(arg)
        elif name == 'mag':
            # For complex variables, mag() should be handled by get_variable_data
            # but if it's called as a function, use absolute value
            return np.abs(arg)
        elif name == 'real':
            # For complex variables, real() should be handled by get_variable_data
            # but if it's called as a function, return the argument as is
            return arg
        elif name == 'imag':
            # For complex variables, imag() should be handled by get_variable_data
            # but if it's called as a function, return zeros (this is a fallback)
            return np.zeros_like(arg)
        elif name == 'ph':
            # For complex variables, ph() should be handled by get_variable_data
            # but if it's called as a function, return angle in degrees
            return np.degrees(np.arctan2(np.zeros_like(arg), arg))
        else:
            raise ValueError(f"Unknown function: {name}")

class WaveViewer(QMainWindow):
    """Main wave viewer window"""
    
    def __init__(self, initial_file=None):
        super().__init__()
        self.setWindowTitle("Wave Viewer")
        self.setGeometry(100, 100, 1000, 600)
        
        # Initialize variables
        self.raw_file = None
        self.current_dataset = 0
        self.traces = []
        self.initial_file = initial_file  # Store initial file for later loading
        # Color management
        self.used_colors = []
        self.color_index = 0
        # Predefined color palette
        self.color_palette = [
            (255, 0, 0),      # Red
            (0, 255, 0),      # Green
            (0, 0, 255),      # Blue
            (255, 255, 0),    # Yellow
            (255, 0, 255),    # Magenta
            (0, 255, 255),    # Cyan
            (128, 0, 0),      # Maroon
            (0, 128, 0),      # Dark Green
            (0, 0, 128),      # Navy
            (128, 128, 0),    # Olive
            (128, 0, 128),    # Purple
            (0, 128, 128),    # Teal
            (192, 192, 192),  # Silver
            (128, 128, 128),  # Gray
            (255, 165, 0),    # Orange
            (147, 112, 219),  # Medium Purple
            (64, 224, 208),   # Turquoise
            (255, 192, 203),  # Pink
            (173, 216, 230),  # Light Blue
            (240, 230, 140)   # Khaki
        ]
        
        # X-axis properties
        self.x_min = 0.0
        self.x_max = 1.0
        self.x_log = False
        self.current_x_var = None  # Current X-axis variable
        # Y-axis properties
        self.y1_min = 0.0
        self.y1_max = 1.0
        self.y1_log = False
        self.y2_min = 0.0
        self.y2_max = 1.0
        self.y2_log = False
        
        # Create menu bar
        menubar = QMenuBar(self)
        file_menu = QMenu("File", self)
        
        # Open Raw File action (renamed from Open)
        open_raw_action = QAction("Open Raw File", self)
        open_raw_action.triggered.connect(self.open_file)
        file_menu.addAction(open_raw_action)
        
        # Open New Window action
        open_new_window_action = QAction("Open New Window", self)
        open_new_window_action.triggered.connect(self.open_new_window)
        file_menu.addAction(open_new_window_action)
        
        menubar.addMenu(file_menu)
        
        edit_menu = QMenu("Edit", self)
        edit_properties_action = QAction("Edit Trace Properties", self)
        edit_properties_action.triggered.connect(self.edit_trace_properties)
        edit_menu.addAction(edit_properties_action)
        
        # Add settings action
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)
        edit_menu.addAction(settings_action)
        
        menubar.addMenu(edit_menu)
        
        self.setMenuBar(menubar)
        
        # Create main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # Create layout
        main_layout = QVBoxLayout()
        # Add margin to the layout
        main_layout.setContentsMargins(10, 10, 10, 10)
        # Set spacing for main layout
        main_layout.setSpacing(10)
        
        # Create plot widget with custom log axes for X, Y1 and Y2
        self.plot_widget = pg.PlotWidget(axisItems={
            'bottom': LogAxisItem(orientation='bottom', log_mode_changed_callback=self.on_axis_log_mode_changed),
            'left': LogAxisItem(orientation='left', log_mode_changed_callback=self.on_axis_log_mode_changed),
            'right': LogAxisItem(orientation='right', log_mode_changed_callback=self.on_axis_log_mode_changed)
        })
        # Use system theme colors
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QApplication
        # Get system background color
        bg_color = QApplication.palette().window().color()
        # Convert to hex format for pyqtgraph
        hex_color = bg_color.name()
        self.plot_widget.setBackground(hex_color)
        # Get system text color
        text_color = QApplication.palette().windowText().color()
        # Set axis labels color
        self.plot_widget.getAxis('bottom').setPen(text_color)
        self.plot_widget.getAxis('left').setPen(text_color)
        self.plot_widget.getAxis('right').setPen(text_color)
        # Set grid color (lighter version of text color)
        grid_color = QColor(text_color)
        grid_color.setAlpha(100)  # Semi-transparent
        # Show grid
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        # Set grid pen color for X and Y axes
        self.plot_widget.getAxis('bottom').gridPen = pg.mkPen(color=grid_color)
        self.plot_widget.getAxis('left').gridPen = pg.mkPen(color=grid_color)
        self.plot_widget.getAxis('right').gridPen = pg.mkPen(color=grid_color)
        # Set border for the viewbox to ensure frame is always visible
        self.plot_widget.plotItem.vb.setBorder(pg.mkPen(color=text_color, width=1))
        # Add legend
        self.legend = self.plot_widget.addLegend()
        # Set initial axis labels with system theme color
        self.update_x_label('X-axis')
        self.update_y1_label('Y1-axis')
        self.update_y2_label('Y2-axis')
        # Set initial plot title with system theme color
        self.update_plot_title('Wave Viewer')
        # Make plot widget expand to fill space
        main_layout.addWidget(self.plot_widget, 1)
        
        # Create controls layout with two rows
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(5)
        
        # First row: Dataset and Vector combos
        first_row_layout = QHBoxLayout()
        first_row_layout.setContentsMargins(0, 0, 0, 0)
        first_row_layout.setSpacing(10)
        
        # Dataset controls
        dataset_label = QLabel("Dataset:")
        self.dataset_combo = QComboBox()
        self.dataset_combo.currentIndexChanged.connect(self.change_dataset)
        # Set minimal size for dataset combo
        self.dataset_combo.setMaximumWidth(200)
        first_row_layout.addWidget(dataset_label)
        first_row_layout.addWidget(self.dataset_combo)
        
        # Add spacing
        first_row_layout.addSpacing(20)
        
        # Vector controls (replaces both X and Y combos)
        vector_label = QLabel("Vector:")
        self.vector_combo = QComboBox()
        # Connect to add variable to trace_expr
        self.vector_combo.currentTextChanged.connect(self.add_vector_to_expr)
        # Set minimal size for vector combo
        self.vector_combo.setMaximumWidth(200)
        first_row_layout.addWidget(vector_label)
        first_row_layout.addWidget(self.vector_combo)
        
        # Add stretch to push controls to the left
        first_row_layout.addStretch()
        
        # Add first row to controls layout
        controls_layout.addLayout(first_row_layout)
        
        # Second row: Add Trace and buttons
        second_row_layout = QHBoxLayout()
        second_row_layout.setContentsMargins(0, 0, 0, 0)
        second_row_layout.setSpacing(10)
        
        # Add Trace controls
        trace_label = QLabel("Add Trace:")
        self.trace_expr = QLineEdit()
        # Set minimal size for line edit
        self.trace_expr.setMinimumWidth(200)
        # Set stretch factor to fill available space
        second_row_layout.addWidget(trace_label)
        second_row_layout.addWidget(self.trace_expr, 1)  # Stretch factor 1
        
        # Create button layout for X, Y1, Y2 buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(5)
        
        # X button - for adding X-axis trace
        self.x_button = QPushButton("X")
        self.x_button.clicked.connect(lambda: self.add_trace_to_axis("X"))
        self.x_button.setMaximumWidth(40)
        button_layout.addWidget(self.x_button)
        
        # Y1 button - for adding Y1-axis trace
        self.y1_button = QPushButton("Y1")
        self.y1_button.clicked.connect(lambda: self.add_trace_to_axis("Y1"))
        self.y1_button.setMaximumWidth(40)
        button_layout.addWidget(self.y1_button)
        
        # Y2 button - for adding Y2-axis trace
        self.y2_button = QPushButton("Y2")
        self.y2_button.clicked.connect(lambda: self.add_trace_to_axis("Y2"))
        self.y2_button.setMaximumWidth(40)
        button_layout.addWidget(self.y2_button)
        
        # Add button layout to second row
        second_row_layout.addLayout(button_layout)
        
        # Add second row to controls layout
        controls_layout.addLayout(second_row_layout)
        
        # Add controls layout to main layout
        main_layout.addLayout(controls_layout)
        
        main_widget.setLayout(main_layout)
        
        # Load initial file if provided (using single-shot timer to ensure UI is ready)
        if self.initial_file:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._load_initial_file())
    
    def _load_initial_file(self):
        """Load the initial file provided via command line"""
        try:
            print(f"Loading initial file: {self.initial_file}")
            self.raw_file = RawFile(self.initial_file)
            self.current_dataset = 0
            self.update_dataset_combo()
            self.update_variable_combo()
            self.clear_traces()
            self.auto_x_range()
            self.auto_y1_range()
            self.auto_y2_range()
            # Update window title with file path
            self.setWindowTitle(f"Wave Viewer - {self.initial_file}")
            print(f"Successfully loaded: {self.initial_file}")
        except FileNotFoundError as e:
            print(f"Error opening initial file: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"File not found: {self.initial_file}")
        except Exception as e:
            print(f"Error opening initial file: {e}")
            from PyQt6.QtWidgets import QMessageBox
            error_msg = str(e)
            if "Invalid RAW file" in error_msg:
                QMessageBox.warning(self, "Error", f"Invalid RAW file format: {self.initial_file}\n\n{error_msg}")
            else:
                QMessageBox.warning(self, "Error", f"Error opening file: {self.initial_file}\n\n{error_msg}")
    
    def open_file(self):
        """Open a raw file"""
        filename, _ = QFileDialog.getOpenFileName(self, "Open Raw File", "", "Raw Files (*.raw);;All Files (*)")
        if filename:
            try:
                self.raw_file = RawFile(filename)
                self.current_dataset = 0
                self.update_dataset_combo()
                self.update_variable_combo()
                self.clear_traces()
                self.auto_x_range()
                self.auto_y1_range()
                self.auto_y2_range()
                # Update window title with file path
                self.setWindowTitle(f"Wave Viewer - {filename}")
            except FileNotFoundError as e:
                print(f"Error opening file: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"File not found: {filename}")
            except Exception as e:
                print(f"Error opening file: {e}")
                from PyQt6.QtWidgets import QMessageBox
                # Show the actual error message from spicelib
                error_msg = str(e)
                if "Invalid RAW file" in error_msg:
                    QMessageBox.warning(self, "Error", f"Invalid RAW file format: {filename}\n\n{error_msg}")
                else:
                    QMessageBox.warning(self, "Error", f"Error opening file: {filename}\n\n{error_msg}")
    
    def open_new_window(self):
        """Open a new WaveViewer window"""
        # Create a new WaveViewer instance
        new_window = WaveViewer()
        new_window.show()
    
    def update_dataset_combo(self):
        """Update dataset combo box"""
        if self.raw_file:
            self.dataset_combo.clear()
            for i, dataset in enumerate(self.raw_file.datasets):
                self.dataset_combo.addItem(f"Dataset {i+1}: {dataset['plotname']}")
    
    def update_variable_combo(self):
        """Update variable combo box"""
        if self.raw_file:
            var_names = self.raw_file.get_variable_names(self.current_dataset)
            # Update vector combo (replaces both X and Y combos)
            self.vector_combo.clear()
            self.vector_combo.addItems(var_names)
            # Set vector combo to no selection
            self.vector_combo.setCurrentIndex(-1)
            # Smart X-axis guess
            self.guess_x_axis()
            # Clear the trace expression input box
            self.trace_expr.clear()
    
    def update_trace_expr(self, text):
        """Update trace expression when Y-axis is selected"""
        # Get current text in the input box
        current_text = self.trace_expr.text().strip()
        # Wrap the variable in quotes
        quoted_text = f'"{text}"'
        # If there's existing text, append the new variable
        if current_text:
            # Append with a space to separate
            new_text = current_text + " " + quoted_text
            self.trace_expr.setText(new_text)
        else:
            # If no existing text, just set the new variable
            self.trace_expr.setText(quoted_text)
    
    def add_x_variable_to_expr(self, text):
        """Add X-axis variable to trace expression"""
        print(f"\n=== add_x_variable_to_expr called: text='{text}' ===")
        if text:
            # Quote the variable name (allow both single and double quotes)
            # Use double quotes by default
            quoted_text = f'"{text}"'
            # Get current text in trace_expr
            current_text = self.trace_expr.text().strip()
            print(f"  Current trace_expr: '{current_text}'")
            print(f"  Quoted text: '{quoted_text}'")
            if current_text:
                # If there's existing text, append with space
                new_text = f"{current_text} {quoted_text}"
                self.trace_expr.setText(new_text)
                print(f"  Updated trace_expr to: '{new_text}'")
            else:
                # If no existing text, just set the new variable
                self.trace_expr.setText(quoted_text)
                print(f"  Set trace_expr to: '{quoted_text}'")
        else:
            print("  Empty text, nothing to add")
    
    def add_y_variable_to_expr(self, text):
        """Add Y-axis variable to trace expression"""
        print(f"\n=== add_y_variable_to_expr called: text='{text}' ===")
        if text:
            # Quote the variable name (allow both single and double quotes)
            # Use double quotes by default
            quoted_text = f'"{text}"'
            # Get current text in trace_expr
            current_text = self.trace_expr.text().strip()
            print(f"  Current trace_expr: '{current_text}'")
            print(f"  Quoted text: '{quoted_text}'")
            if current_text:
                # If there's existing text, append with space
                new_text = f"{current_text} {quoted_text}"
                self.trace_expr.setText(new_text)
                print(f"  Updated trace_expr to: '{new_text}'")
            else:
                # If no existing text, just set the new variable
                self.trace_expr.setText(quoted_text)
                print(f"  Set trace_expr to: '{quoted_text}'")
        else:
            print("  Empty text, nothing to add")
    
    def add_vector_to_expr(self, text):
        """Add vector variable to trace expression"""
        print(f"\n=== add_vector_to_expr called: text='{text}' ===")
        if text:
            # Quote the variable name (allow both single and double quotes)
            # Use double quotes by default
            quoted_text = f'"{text}"'
            # Get current text in trace_expr
            current_text = self.trace_expr.text().strip()
            print(f"  Current trace_expr: '{current_text}'")
            print(f"  Quoted text: '{quoted_text}'")
            if current_text:
                # If there's existing text, append with space
                new_text = f"{current_text} {quoted_text}"
                self.trace_expr.setText(new_text)
                print(f"  Updated trace_expr to: '{new_text}'")
            else:
                # If no existing text, just set the new variable
                self.trace_expr.setText(quoted_text)
                print(f"  Set trace_expr to: '{quoted_text}'")
        else:
            print("  Empty text, nothing to add")
    
    def add_trace_to_axis(self, axis):
        """Add trace to specified axis (X, Y1, or Y2)
        
        Args:
            axis: "X", "Y1", or "Y2"
        """
        print(f"\n=== add_trace_to_axis called: axis='{axis}' ===")
        if not self.raw_file:
            print("No raw file opened")
            return
        
        expr = self.trace_expr.text().strip()
        print(f"  Expression from trace_expr: '{expr}'")
        if not expr:
            print("Empty expression")
            return
        
        try:
            print(f"Adding trace to {axis}-axis for expression: {expr}")
            
            # Split the expression into individual variables/expressions
            variables = self.split_expressions(expr)
            print(f"Split expressions: {variables}")
            print(f"Number of variables: {len(variables)}")
            
            # Validate based on axis
            if axis == "X":
                # X-axis can only have one variable/expression
                if len(variables) > 1:
                    print(f"Error: X-axis can only have one variable/expression, got {len(variables)}")
                    # Show error message to user
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "X-axis Error", 
                                       f"X-axis can only have one variable/expression.\n"
                                       f"Found {len(variables)}: {', '.join(variables)}")
                    return
                
                # For X-axis, we need to set the X-axis variable
                if variables:
                    x_var = variables[0]
                    print(f"Setting X-axis variable to: {x_var}")
                    # Store the current X-axis variable
                    self.current_x_var = x_var
                    # Update X-axis label to show the new variable
                    self.update_x_label(x_var)
                    # Auto range X-axis based on new variable
                    self.auto_x_range()
                    # Clear trace_expr after successful addition
                    self.trace_expr.clear()
                    print(f"Cleared trace_expr")
                else:
                    print(f"Warning: No valid variables found in expression")
            
            elif axis in ["Y1", "Y2"]:
                # Y1/Y2 axes can have multiple variables
                if not variables:
                    print("Error: No valid expressions found")
                    return
                
                # For each variable, add trace to the specified Y-axis
                for var in variables:
                    print(f"Adding trace for {var} to {axis}-axis")
                    # Call the existing add_trace method with axis parameter
                    self.add_trace(custom_color=None, selected_y_axis=axis)
                
                # Clear trace_expr after successful addition
                self.trace_expr.clear()
                print(f"Cleared trace_expr")
            
        except Exception as e:
            print(f"Error adding trace to {axis}-axis: {e}")
            import traceback
            traceback.print_exc()
    
    def guess_x_axis(self):
        """Guess the best X-axis variable"""
        if self.raw_file:
            var_names = self.raw_file.get_variable_names(self.current_dataset)
            # Look for common sweep variables
            sweep_vars = ['time', 'frequency', 'freq', 'v sweep', 'i sweep']
            for var in var_names:
                if var.lower() in sweep_vars:
                    self.current_x_var = var
                    self.update_x_label(var)
                    return
            # If no common sweep variable found, use the first variable
            if var_names:
                self.current_x_var = var_names[0]
                self.update_x_label(var_names[0])
    
    def change_dataset(self, index):
        """Change current dataset"""
        self.current_dataset = index
        self.update_variable_combo()
        self.clear_traces()
        self.auto_x_range()
        self.auto_y1_range()
        self.auto_y2_range()
        # Reapply axis labels with system theme color after dataset change
        self.update_x_label('X-axis')
        self.update_y1_label('Y1-axis')
        self.update_y2_label('Y2-axis')
        self.update_plot_title('Wave Viewer')
    
    def split_expressions(self, expr):
        """Split expression into individual expressions, respecting quotes, parentheses and operators"""
        expressions = []
        current_expr = []
        paren_depth = 0
        in_quotes = False
        quote_char = None
        
        i = 0
        while i < len(expr):
            c = expr[i]
            
            if c in ['"', "'"] and paren_depth == 0:
                if not in_quotes:
                    # Start of quoted expression
                    in_quotes = True
                    quote_char = c
                elif c == quote_char:
                    # End of quoted expression
                    in_quotes = False
                    quote_char = None
                current_expr.append(c)
            elif c == '(' and not in_quotes:
                paren_depth += 1
                current_expr.append(c)
            elif c == ')' and not in_quotes:
                paren_depth -= 1
                current_expr.append(c)
            elif c == ' ' and paren_depth == 0 and not in_quotes:
                if current_expr:
                    # Split here
                    expressions.append(''.join(current_expr).strip())
                    current_expr = []
            else:
                current_expr.append(c)
            
            i += 1
        
        if current_expr:
            expressions.append(''.join(current_expr).strip())
        
        # Remove quotes from expressions
        cleaned_expressions = []
        for expr in expressions:
            if expr and expr[0] in ['"', "'"] and expr[-1] == expr[0]:
                cleaned_expressions.append(expr[1:-1])
            else:
                cleaned_expressions.append(expr)
        
        return cleaned_expressions
    
    def add_trace_from_combo(self, text, custom_color=None):
        """Add trace from Y1 or Y2 combo box
        
        Args:
            text: The variable/expression text
            custom_color: Optional custom color for the trace (QColor or tuple)
        """
        if not self.raw_file:
            print("No raw file opened")
            return
        
        var = text.strip()
        if not var:
            return
        
        try:
            print(f"Adding trace from combo: {var}")
            var_names = self.raw_file.get_variable_names(self.current_dataset)
            print(f"Available variables: {var_names}")
            
            n_points = self.raw_file.get_num_points(self.current_dataset)
            print(f"Number of points: {n_points}")
            
            if not self.current_x_var:
                print("No X-axis variable selected")
                return
            x_var = self.current_x_var
            print(f"X-axis variable: {x_var}")
            
            x_data = self.raw_file.get_variable_data(x_var, self.current_dataset)
            if x_data is not None:
                print(f"X data length: {len(x_data)}")
                # Always print X data range for debugging
                x_data_real = np.real(x_data)
                print(f"  X data range: [{np.min(x_data_real):.6e}, {np.max(x_data_real):.6e}]")
                
                # Check X-axis log mode
                print(f"  Current X log mode: {self.x_log}")
                if self.x_log:
                    print(f"  X-axis is in log mode, transforming X data...")
                    print(f"  Original X data range: [{np.min(x_data_real):.6e}, {np.max(x_data_real):.6e}]")
                    
                    # Handle non-positive values (log10 undefined for <= 0)
                    mask = x_data_real > 0
                    if np.any(~mask):
                        print(f"  Warning: {np.sum(~mask)} non-positive X values found, adjusting for log scale...")
                        
                        # Calculate a reasonable replacement value
                        if np.any(mask):
                            # If there are positive values, use a small fraction of the minimum positive value
                            min_positive = np.min(x_data_real[mask])
                            replacement = min_positive * 1e-10  # Much smaller fraction
                        else:
                            # If no positive values, use a small fraction of the data range
                            data_range = np.max(np.abs(x_data_real)) - np.min(np.abs(x_data_real))
                            if data_range > 0:
                                replacement = data_range * 1e-10
                            else:
                                replacement = 1e-10  # Default small value
                        
                        print(f"    Replacement value: {replacement:.6e}")
                        x_data_real = np.where(mask, x_data_real, replacement)
                        print(f"    Adjusted X data range: [{np.min(x_data_real):.6e}, {np.max(x_data_real):.6e}]")
                    
                    # Transform to log10
                    x_data_transformed = np.log10(x_data_real)
                    print(f"  Transformed X data range: [{np.min(x_data_transformed):.6e}, {np.max(x_data_transformed):.6e}]")
                    x_data = x_data_transformed
                else:
                    print(f"  X-axis is in linear mode, using original X data")
                
                # Determine which Y-axis to use based on which combo box was triggered
                sender = self.sender()
                if sender == self.y1_combo:
                    selected_y_axis = "Y1"
                elif sender == self.y2_combo:
                    selected_y_axis = "Y2"
                else:
                    selected_y_axis = "Y1"
                print(f"Selected Y-axis: {selected_y_axis}")
                
                evaluator = ExprEvaluator(self.raw_file, self.current_dataset)
                print(f"Created evaluator for {var}")
                
                y_data = evaluator.evaluate(var)
                print(f"Evaluated expression {var}, result length: {len(y_data)}")
                
                # Check Y-axis log mode
                y_log = self.y1_log if selected_y_axis == "Y1" else self.y2_log
                print(f"  Current Y log mode: {y_log}")
                if y_log:
                    print(f"  Y-axis is in log mode, transforming Y data...")
                    # Transform Y data to log10 space
                    y_data_real = np.real(y_data)
                    print(f"  Original Y data range: [{np.min(y_data_real):.6e}, {np.max(y_data_real):.6e}]")
                    
                    # Handle non-positive values (log10 undefined for <= 0)
                    mask = y_data_real > 0
                    if np.any(~mask):
                        print(f"  Warning: {np.sum(~mask)} non-positive Y values found, adjusting for log scale...")
                        
                        # Calculate a reasonable replacement value
                        if np.any(mask):
                            # If there are positive values, use a small fraction of the minimum positive value
                            min_positive = np.min(y_data_real[mask])
                            replacement = min_positive * 1e-10  # Much smaller fraction
                        else:
                            # If no positive values, use a small fraction of the data range
                            data_range = np.max(np.abs(y_data_real)) - np.min(np.abs(y_data_real))
                            if data_range > 0:
                                replacement = data_range * 1e-10
                            else:
                                replacement = 1e-10  # Default small value
                        
                        print(f"    Replacement value: {replacement:.6e}")
                        y_data_real = np.where(mask, y_data_real, replacement)
                        print(f"    Adjusted Y data range: [{np.min(y_data_real):.6e}, {np.max(y_data_real):.6e}]")
                    
                    # Transform to log10
                    y_data_transformed = np.log10(y_data_real)
                    print(f"  Transformed Y data range: [{np.min(y_data_transformed):.6e}, {np.max(y_data_transformed):.6e}]")
                    y_data = y_data_transformed
                else:
                    print(f"  Y-axis is in linear mode, using original Y data")
                
                # Check if X and Y data have the same length
                if len(x_data) != len(y_data):
                    print(f"  ERROR: X and Y data length mismatch!")
                    print(f"    X data length: {len(x_data)}")
                    print(f"    Y data length: {len(y_data)}")
                    print(f"    Skipping trace for {var}")
                    return
                
                # Get color - use custom color if provided and valid, otherwise get next from palette
                if custom_color is not None and custom_color is not False:
                    color = custom_color
                    print(f"  Using custom color: {color}")
                else:
                    color = self.get_next_color()
                    if custom_color is False:
                        print(f"  Using default color (custom_color=False): {color}")
                pen = pg.mkPen(color=color, width=2)
                
                # Use the selected Y-axis
                if selected_y_axis == "Y2":
                    # For Y2, use the right axis
                    # First ensure the right axis and y2 viewbox exist
                    if not hasattr(self, 'right_axis'):
                        # Show right axis
                        self.plot_widget.showAxis('right')
                        # Get right axis
                        self.right_axis = self.plot_widget.getAxis('right')
                        # Set Y2 axis color to match system theme
                        from PyQt6.QtGui import QColor
                        from PyQt6.QtWidgets import QApplication
                        text_color = QApplication.palette().windowText().color()
                        self.right_axis.setPen(text_color)
                        # Set grid color for Y2 axis
                        grid_color = QColor(text_color)
                        grid_color.setAlpha(100)  # Semi-transparent
                        # Set grid pen for Y2 axis using pyqtgraph's mkPen
                        self.right_axis.gridPen = pg.mkPen(color=grid_color)
                        # Create a new ViewBox for Y2
                        self.y2_viewbox = pg.ViewBox()
                        # Add to the plot widget's scene
                        self.plot_widget.scene().addItem(self.y2_viewbox)
                        # Link X axis with main viewbox
                        self.y2_viewbox.setXLink(self.plot_widget.plotItem)
                        # Connect right axis to Y2 viewbox
                        self.right_axis.linkToView(self.y2_viewbox)
                        # Set Y2 viewbox geometry
                        def update_viewbox():
                            # Update Y2 viewbox geometry to match main viewbox
                            rect = self.plot_widget.plotItem.vb.sceneBoundingRect()
                            self.y2_viewbox.setGeometry(rect)
                            # Update linked axes
                            self.y2_viewbox.linkedViewChanged(self.plot_widget.plotItem.vb, self.y2_viewbox.XAxis)
                        # Initial update
                        update_viewbox()
                        # Connect to resize signal
                        self.plot_widget.plotItem.vb.sigResized.connect(update_viewbox)
                    # Create plot item for Y2
                    plot_item = pg.PlotCurveItem(x_data, y_data, name=var, pen=pen)
                    # Add plot item to Y2 viewbox
                    self.y2_viewbox.addItem(plot_item)
                    # Add to legend with Y2 prefix
                    legend_name = f"{var} @ Y2"
                    self.legend.addItem(plot_item, legend_name)
                    # Auto range Y2
                    self.auto_y2_range()
                else:
                    # For Y1, use the default left axis
                    # Create plot item for Y1
                    plot_item = pg.PlotCurveItem(x_data, y_data, name=var, pen=pen)
                    # Add plot item to main viewbox
                    self.plot_widget.plotItem.vb.addItem(plot_item)
                    # Add to legend with Y1 prefix
                    legend_name = f"{var} @ Y1"
                    self.legend.addItem(plot_item, legend_name)
                    # Auto range Y1
                    self.auto_y1_range()
                
                # Store trace info
                self.traces.append((var, plot_item, selected_y_axis))
                print(f"Added trace {var} to {selected_y_axis}")
        except Exception as e:
            print(f"Error adding trace: {e}")
    
    def add_trace(self, custom_color=None, selected_y_axis="Y1"):
        """Add a trace
        
        Args:
            custom_color: Optional custom color for the trace (QColor or tuple)
            selected_y_axis: Which Y-axis to use ("Y1" or "Y2")
        """
        if not self.raw_file:
            print("No raw file opened")
            return
        
        expr = self.trace_expr.text().strip()
        if not expr:
            print("Empty expression")
            return
        
        try:
            print(f"Adding trace for expression: {expr}")
            var_names = self.raw_file.get_variable_names(self.current_dataset)
            print(f"Available variables: {var_names}")
            
            n_points = self.raw_file.get_num_points(self.current_dataset)
            print(f"Number of points: {n_points}")
            
            # Split the expression into individual variables/expressions
            variables = self.split_expressions(expr)
            print(f"Split expressions: {variables}")
            
            if not self.current_x_var:
                print("No X-axis variable selected")
                return
            x_var = self.current_x_var
            print(f"X-axis variable: {x_var}")
            
            x_data = self.raw_file.get_variable_data(x_var, self.current_dataset)
            if x_data is not None:
                print(f"X data length: {len(x_data)}")
                
                # Check X-axis log mode
                print(f"  Current X log mode: {self.x_log}")
                if self.x_log:
                    print(f"  X-axis is in log mode, transforming X data...")
                    # Transform X data to log10 space
                    x_data_real = np.real(x_data)
                    print(f"  Original X data range: [{np.min(x_data_real):.6e}, {np.max(x_data_real):.6e}]")
                    
                    # Handle non-positive values (log10 undefined for <= 0)
                    mask = x_data_real > 0
                    if np.any(~mask):
                        print(f"  Warning: {np.sum(~mask)} non-positive X values found, adjusting for log scale...")
                        
                        # Calculate a reasonable replacement value
                        if np.any(mask):
                            # If there are positive values, use a small fraction of the minimum positive value
                            min_positive = np.min(x_data_real[mask])
                            replacement = min_positive * 1e-10  # Much smaller fraction
                        else:
                            # If no positive values, use a small fraction of the data range
                            data_range = np.max(np.abs(x_data_real)) - np.min(np.abs(x_data_real))
                            if data_range > 0:
                                replacement = data_range * 1e-10
                            else:
                                replacement = 1e-10  # Default small value
                        
                        print(f"    Replacement value: {replacement:.6e}")
                        x_data_real = np.where(mask, x_data_real, replacement)
                        print(f"    Adjusted X data range: [{np.min(x_data_real):.6e}, {np.max(x_data_real):.6e}]")
                    
                    # Transform to log10
                    x_data_transformed = np.log10(x_data_real)
                    print(f"  Transformed X data range: [{np.min(x_data_transformed):.6e}, {np.max(x_data_transformed):.6e}]")
                    x_data = x_data_transformed
                else:
                    print(f"  X-axis is in linear mode, using original X data")
                
                # Use the provided selected_y_axis parameter
                print(f"Selected Y-axis: {selected_y_axis}")
                
                for var in variables:
                    evaluator = ExprEvaluator(self.raw_file, self.current_dataset)
                    print(f"Created evaluator for {var}")
                    
                    y_data = evaluator.evaluate(var)
                    print(f"Evaluated expression {var}, result length: {len(y_data)}")
                    # Always print Y data range for debugging
                    y_data_real = np.real(y_data)
                    print(f"  Y data range: [{np.min(y_data_real):.6e}, {np.max(y_data_real):.6e}]")
                    
                    # Check Y-axis log mode
                    y_log = self.y1_log if selected_y_axis == "Y1" else self.y2_log
                    print(f"  Current Y log mode: {y_log}")
                    if y_log:
                        print(f"  Y-axis is in log mode, transforming Y data...")
                        print(f"  Original Y data range: [{np.min(y_data_real):.6e}, {np.max(y_data_real):.6e}]")
                        
                        # Handle non-positive values (log10 undefined for <= 0)
                        mask = y_data_real > 0
                        if np.any(~mask):
                            print(f"  Warning: {np.sum(~mask)} non-positive Y values found, adjusting for log scale...")
                            
                            # Calculate a reasonable replacement value
                            if np.any(mask):
                                # If there are positive values, use a small fraction of the minimum positive value
                                min_positive = np.min(y_data_real[mask])
                                replacement = min_positive * 1e-10  # Much smaller fraction
                            else:
                                # If no positive values, use a small fraction of the data range
                                data_range = np.max(np.abs(y_data_real)) - np.min(np.abs(y_data_real))
                                if data_range > 0:
                                    replacement = data_range * 1e-10
                                else:
                                    replacement = 1e-10  # Default small value
                            
                            print(f"    Replacement value: {replacement:.6e}")
                            y_data_real = np.where(mask, y_data_real, replacement)
                            print(f"    Adjusted Y data range: [{np.min(y_data_real):.6e}, {np.max(y_data_real):.6e}]")
                        
                        # Transform to log10
                        y_data_transformed = np.log10(y_data_real)
                        print(f"  Transformed Y data range: [{np.min(y_data_transformed):.6e}, {np.max(y_data_transformed):.6e}]")
                        y_data = y_data_transformed
                    else:
                        print(f"  Y-axis is in linear mode, using original Y data")
                    
                    # Check if X and Y data have the same length
                    if len(x_data) != len(y_data):
                        print(f"  ERROR: X and Y data length mismatch!")
                        print(f"    X data length: {len(x_data)}")
                        print(f"    Y data length: {len(y_data)}")
                        print(f"    Skipping trace for {var}")
                        continue
                    
                    # Get color - use custom color if provided and valid, otherwise get next from palette
                    if custom_color is not None and custom_color is not False:
                        color = custom_color
                        print(f"  Using custom color: {color}")
                    else:
                        color = self.get_next_color()
                        if custom_color is False:
                            print(f"  Using default color (custom_color=False): {color}")
                    pen = pg.mkPen(color=color, width=2)
                    
                    # Use the selected Y-axis
                    if selected_y_axis == "Y2":
                        # For Y2, use the right axis
                        # First ensure the right axis and y2 viewbox exist
                        if not hasattr(self, 'right_axis'):
                            # Show right axis
                            self.plot_widget.showAxis('right')
                            # Get right axis
                            self.right_axis = self.plot_widget.getAxis('right')
                            # Create a new ViewBox for Y2
                            self.y2_viewbox = pg.ViewBox()
                            # Add to the plot widget's scene
                            self.plot_widget.scene().addItem(self.y2_viewbox)
                            # Link X axis with main viewbox
                            self.y2_viewbox.setXLink(self.plot_widget.plotItem)
                            # Connect right axis to Y2 viewbox
                            self.right_axis.linkToView(self.y2_viewbox)
                            # Set Y2 viewbox geometry
                            def update_viewbox():
                                # Update Y2 viewbox geometry to match main viewbox
                                rect = self.plot_widget.plotItem.vb.sceneBoundingRect()
                                self.y2_viewbox.setGeometry(rect)
                                # Update linked axes
                                self.y2_viewbox.linkedViewChanged(self.plot_widget.plotItem.vb, self.y2_viewbox.XAxis)
                            # Initial update
                            update_viewbox()
                            # Connect to resize signal
                            self.plot_widget.plotItem.vb.sigResized.connect(update_viewbox)
                            # Set system text color for Y2 axis
                            from PyQt6.QtGui import QColor
                            from PyQt6.QtWidgets import QApplication
                            text_color = QApplication.palette().windowText().color()
                            self.right_axis.setPen(text_color)
                            # Set grid color for Y2 axis
                            grid_color = QColor(text_color)
                            grid_color.setAlpha(100)  # Semi-transparent
                            self.right_axis.gridPen = pg.mkPen(color=grid_color)
                        # Create plot item for Y2
                        plot_item = pg.PlotCurveItem(x_data, y_data, name=var, pen=pen)
                        # Add plot item to Y2 viewbox
                        self.y2_viewbox.addItem(plot_item)
                        # Add to legend with Y2 prefix
                        legend_name = f"{var} @ Y2"
                        self.legend.addItem(plot_item, legend_name)
                        # Auto range Y2
                        self.auto_y2_range()
                    else:
                        # For Y1, use the default left axis
                        # Create plot item for Y1
                        plot_item = pg.PlotCurveItem(x_data, y_data, name=var, pen=pen)
                        # Add plot item to main viewbox
                        self.plot_widget.plotItem.vb.addItem(plot_item)
                        # Add to legend with Y1 prefix
                        legend_name = f"{var} @ Y1"
                        self.legend.addItem(plot_item, legend_name)
                        # Auto range Y1
                        self.auto_y1_range()
                    
                    # Store trace with Y-axis information
                    self.traces.append((var, plot_item, selected_y_axis))
                    print(f"Added trace: {var} on {selected_y_axis}")
                
                # Auto range for the selected Y-axis
                if selected_y_axis == "Y2":
                    self.auto_y2_range()
                else:
                    self.auto_y1_range()
                print("Auto y range done")
                # Clear the trace expression input box
                self.trace_expr.clear()
            else:
                print(f"No data for X variable: {x_var}")
        except Exception as e:
            print(f"Error adding trace: {e}")
            import traceback
            traceback.print_exc()
    
    def clear_traces(self):
        """Clear all traces"""
        # Clear traces from viewboxes
        for _, plot_item, y_axis in self.traces:
            if y_axis == "Y2" and hasattr(self, 'y2_viewbox'):
                self.y2_viewbox.removeItem(plot_item)
            else:
                self.plot_widget.plotItem.vb.removeItem(plot_item)
        # Clear legend items
        if hasattr(self, 'legend'):
            # Clear all items from legend
            items = list(self.legend.items)
            print(f"  Clearing {len(items)} items from legend")
            for item in items:
                try:
                    self.legend.removeItem(item)
                except Exception as e:
                    print(f"    Error removing legend item: {e}")
            # Also try clear() method
            try:
                self.legend.clear()
            except Exception as e:
                print(f"    Error clearing legend: {e}")
        # Reset traces list
        self.traces = []
        # Reset color management
        self.used_colors = []
        self.color_index = 0
        # Remove right axis and y2 viewbox references
        if hasattr(self, 'right_axis'):
            # Hide right axis instead of removing it
            self.plot_widget.hideAxis('right')
            delattr(self, 'right_axis')
        if hasattr(self, 'y2_viewbox'):
            # Remove y2_viewbox from scene
            try:
                self.plot_widget.scene().removeItem(self.y2_viewbox)
            except Exception:
                pass
            delattr(self, 'y2_viewbox')
    
    def get_next_color(self):
        """Get the next color from the palette, ensuring no repeats"""
        if self.color_index < len(self.color_palette):
            # Use predefined color
            color = self.color_palette[self.color_index]
            self.color_index += 1
        else:
            # Generate random color if palette is exhausted
            while True:
                color = (np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255))
                if color not in self.used_colors:
                    break
        self.used_colors.append(color)
        return color
    
    def on_axis_log_mode_changed(self, orientation, log_mode):
        """Callback when axis log mode changes via LogAxisItem"""
        print(f"\n=== on_axis_log_mode_changed: orientation={orientation}, log_mode={log_mode} ===")
        
        if orientation == 'bottom':
            # X-axis log mode changed
            self.x_log = log_mode
            print(f"  Updated self.x_log to {log_mode}")
        elif orientation == 'left':
            # Y1-axis log mode changed
            self.y1_log = log_mode
            print(f"  Updated self.y1_log to {log_mode}")
        elif orientation == 'right':
            # Y2-axis log mode changed
            self.y2_log = log_mode
            print(f"  Updated self.y2_log to {log_mode}")
        
        # Update all existing traces
        print(f"  Updating existing traces for new log mode")
        self.update_traces_for_log_mode()
    
    def update_traces_for_log_mode(self):
        """Update all existing traces for current log mode settings"""
        print(f"\n=== update_traces_for_log_mode ===")
        print(f"  Current log modes: x_log={self.x_log}, y1_log={self.y1_log}, y2_log={self.y2_log}")
        
        if not self.traces:
            print(f"  No traces to update")
            return
        
        print(f"  Found {len(self.traces)} traces to update")
        
        # Save current trace information
        saved_traces = []
        for var, plot_item, y_axis in self.traces:
            # Get trace color from plot item and convert to RGB tuple
            qcolor = plot_item.opts['pen'].color()
            # Convert QColor to RGB tuple
            color = (qcolor.red(), qcolor.green(), qcolor.blue())
            saved_traces.append({
                'var': var,
                'y_axis': y_axis,
                'color': color
            })
            print(f"  Saving trace: {var} on {y_axis}, color={color}")
        
        # Clear all traces and legend
        self.clear_traces()
        print(f"  Cleared all traces and legend")
        
        # Re-add all traces with current log mode settings
        for trace_info in saved_traces:
            var = trace_info['var']
            y_axis = trace_info['y_axis']
            color = trace_info['color']
            
            print(f"  Re-adding trace: {var} on {y_axis} with color {color}")
            
            # Directly call add_trace with the saved information
            try:
                # Set the trace expression to the variable
                self.trace_expr.setText(f'"{var}"')
                # Call add_trace directly with the saved color and axis
                self.add_trace(custom_color=color, selected_y_axis=y_axis)
            except Exception as e:
                print(f"    Error re-adding trace: {e}")
        
        print(f"  Trace update complete")
    
    def update_x_log(self, state):
        """Update X-axis log mode"""
        is_log = state == Qt.CheckState.Checked.value
        print(f"\n=== update_x_log: is_log={is_log} ===")
        
        # Update the property
        self.x_log = is_log
        print(f"  Updated self.x_log to {is_log}")
        
        # Set log mode for X-axis while preserving Y1-axis log mode
        print(f"  Calling setLogMode(x={is_log}, y={self.y1_log})")
        self.plot_widget.plotItem.setLogMode(x=is_log, y=self.y1_log)
    
    def update_y1_log(self, state):
        """Update Y1-axis log mode"""
        is_log = state == Qt.CheckState.Checked.value
        print(f"\n=== update_y1_log: is_log={is_log} ===")
        
        # Update the property
        self.y1_log = is_log
        print(f"  Updated self.y1_log to {is_log}")
        
        # Instead of calling setLogMode directly, let LogAxisItem handle it
        # This will trigger the callback which updates traces
        print(f"  Calling setLogMode(x={self.x_log}, y={is_log})")
        self.plot_widget.plotItem.setLogMode(x=self.x_log, y=is_log)
    
    def update_y2_log(self, state):
        """Update Y2-axis log mode"""
        is_log = state == Qt.CheckState.Checked.value
        # Update the property
        self.y2_log = is_log
        # Set log mode for Y2 viewbox
        if hasattr(self, 'y2_viewbox'):
            self.y2_viewbox.setLogMode(y=is_log)
        # Set log mode for right axis
        if hasattr(self, 'right_axis'):
            self.right_axis.setLogMode(is_log)
    
    def auto_x_range(self):
        """Auto scale X-axis"""
        if self.raw_file and self.current_x_var:
            x_var = self.current_x_var
            x_data = self.raw_file.get_variable_data(x_var, self.current_dataset)
            if x_data is not None:
                # Check if data contains valid values
                if len(x_data) > 0:
                    # Handle possible NaN values
                    valid_data = x_data[~np.isnan(x_data)]
                    if len(valid_data) > 0:
                        # Ensure data is real
                        valid_data = np.real(valid_data)
                        
                        # Handle logarithmic mode for X-axis
                        if self.x_log:
                            # Handle non-positive values for log scale
                            mask = valid_data > 0
                            if np.any(~mask):
                                # Calculate a reasonable replacement value
                                if np.any(mask):
                                    min_positive = np.min(valid_data[mask])
                                    replacement = min_positive * 1e-10
                                else:
                                    replacement = 1e-10
                                valid_data = np.where(mask, valid_data, replacement)
                            
                            # Transform to log10 for log mode
                            valid_data = np.log10(valid_data)
                        
                        min_val = np.min(valid_data)
                        max_val = np.max(valid_data)
                        
                        # Only update spin boxes if they exist and are not deleted
                        if hasattr(self, 'x_min_spin') and hasattr(self.x_min_spin, 'setValue'):
                            try:
                                # For log mode, show actual values in spin boxes, not log values
                                if self.x_log:
                                    # Convert back to linear for display
                                    self.x_min_spin.setValue(float(10 ** min_val))
                                    self.x_max_spin.setValue(float(10 ** max_val))
                                else:
                                    self.x_min_spin.setValue(float(min_val))
                                    self.x_max_spin.setValue(float(max_val))
                            except (RuntimeError, AttributeError):
                                # Ignore if spin boxes are deleted
                                pass
                        
                        # Use plotItem's setXRange with padding to properly manage boundaries
                        # Add small padding to ensure viewbox doesn't exceed plot widget boundaries
                        if self.x_log:
                            # For log mode, use log space padding
                            log_range = max_val - min_val
                            log_padding = log_range * 0.05 if log_range > 0 else 0.1
                            padded_min = min_val - log_padding
                            padded_max = max_val + log_padding
                        else:
                            range_padding = (max_val - min_val) * 0.05 if max_val > min_val else 0.1
                            padded_min = min_val - range_padding
                            padded_max = max_val + range_padding
                        
                        self.plot_widget.plotItem.setXRange(float(padded_min), float(padded_max))
    
    def auto_y1_range(self):
        """Auto scale Y1-axis"""
        if not self.traces:
            return
        
        y_min = float('inf')
        y_max = float('-inf')
        
        for _, plot_item, y_axis in self.traces:
            if y_axis == "Y1":
                data = plot_item.getData()[1]
                if len(data) > 0:
                    # Handle possible NaN values
                    valid_data = data[~np.isnan(data)]
                    if len(valid_data) > 0:
                        # For logarithmic mode, use magnitude of complex data
                        if self.y1_log:
                            # Use absolute value for log scale
                            valid_data = np.abs(valid_data)
                        else:
                            # Ensure data is real for linear scale
                            valid_data = np.real(valid_data)
                        y_min = min(y_min, np.min(valid_data))
                        y_max = max(y_max, np.max(valid_data))
        
        if y_min != float('inf') and y_max != float('-inf'):
            # Handle logarithmic mode
            if self.y1_log:
                # When in log mode, data is already log10 transformed
                # So y_min and y_max are already log10 values
                log_min = y_min
                log_max = y_max
                log_range = log_max - log_min
                log_padding = log_range * 0.05 if log_range > 0 else 0.1
                # For log mode, we set the range in log space
                # pyqtgraph expects log10 values when setLogMode(y=True)
                padded_min = log_min - log_padding
                padded_max = log_max + log_padding
            else:
                # Use linear padding for linear scale
                range_padding = (y_max - y_min) * 0.05 if y_max > y_min else 0.1
                padded_min = y_min - range_padding
                padded_max = y_max + range_padding
            
            # Only update spin boxes if they exist and are not deleted
            if hasattr(self, 'y1_min_spin') and hasattr(self.y1_min_spin, 'setValue'):
                try:
                    self.y1_min_spin.setValue(float(y_min))
                    self.y1_max_spin.setValue(float(y_max))
                except (RuntimeError, AttributeError):
                    # Ignore if spin boxes are deleted
                    pass
            
            # Set Y range with appropriate padding
            self.plot_widget.plotItem.setYRange(float(padded_min), float(padded_max))
    
    def auto_y2_range(self):
        """Auto scale Y2-axis"""
        if not self.traces or not hasattr(self, 'y2_viewbox'):
            return
        
        y_min = float('inf')
        y_max = float('-inf')
        
        for _, plot_item, y_axis in self.traces:
            if y_axis == "Y2":
                data = plot_item.getData()[1]
                if len(data) > 0:
                    # Handle possible NaN values
                    valid_data = data[~np.isnan(data)]
                    if len(valid_data) > 0:
                        # For logarithmic mode, use magnitude of complex data
                        if hasattr(self, 'y2_log') and self.y2_log:
                            # Use absolute value for log scale
                            valid_data = np.abs(valid_data)
                        else:
                            # Ensure data is real for linear scale
                            valid_data = np.real(valid_data)
                        y_min = min(y_min, np.min(valid_data))
                        y_max = max(y_max, np.max(valid_data))
        
        if y_min != float('inf') and y_max != float('-inf'):
            # Handle logarithmic mode for Y2
            if hasattr(self, 'y2_log') and self.y2_log:
                # When in log mode, data is already log10 transformed
                # So y_min and y_max are already log10 values
                log_min = y_min
                log_max = y_max
                log_range = log_max - log_min
                log_padding = log_range * 0.05 if log_range > 0 else 0.1
                # For log mode, we set the range in log space
                # pyqtgraph expects log10 values when setLogMode(y=True)
                padded_min = log_min - log_padding
                padded_max = log_max + log_padding
            else:
                # Use linear padding for linear scale
                range_padding = (y_max - y_min) * 0.05 if y_max > y_min else 0.1
                padded_min = y_min - range_padding
                padded_max = y_max + range_padding
            
            # Only update spin boxes if they exist and are not deleted
            if hasattr(self, 'y2_min_spin') and hasattr(self.y2_min_spin, 'setValue'):
                try:
                    self.y2_min_spin.setValue(float(y_min))
                    self.y2_max_spin.setValue(float(y_max))
                except (RuntimeError, AttributeError):
                    # Ignore if spin boxes are deleted
                    pass
            # Set Y2 range (right axis) with appropriate padding
            self.y2_viewbox.setYRange(float(padded_min), float(padded_max))
    
    def update_x_range(self):
        """Update X-axis range from spin boxes"""
        if hasattr(self, 'x_min_spin') and hasattr(self, 'x_max_spin'):
            try:
                x_min = self.x_min_spin.value()
                x_max = self.x_max_spin.value()
                if x_min < x_max:
                    # Use plotItem's setXRange with padding to properly manage boundaries
                    # Add small padding to ensure viewbox doesn't exceed plot widget boundaries
                    range_padding = (x_max - x_min) * 0.05 if x_max > x_min else 0.1
                    self.plot_widget.plotItem.setXRange(x_min - range_padding, x_max + range_padding)
            except (RuntimeError, AttributeError):
                # Ignore if spin boxes are deleted
                pass
    
    def update_y1_range(self):
        """Update Y1-axis range from spin boxes"""
        if hasattr(self, 'y1_min_spin') and hasattr(self, 'y1_max_spin'):
            try:
                y_min = self.y1_min_spin.value()
                y_max = self.y1_max_spin.value()
                if y_min < y_max:
                    # Use plotItem's setYRange with padding to properly manage boundaries
                    # Add small padding to ensure viewbox doesn't exceed plot widget boundaries
                    range_padding = (y_max - y_min) * 0.05 if y_max > y_min else 0.1
                    self.plot_widget.plotItem.setYRange(y_min - range_padding, y_max + range_padding)
            except (RuntimeError, AttributeError):
                # Ignore if spin boxes are deleted
                pass
    
    def update_y2_range(self):
        """Update Y2-axis range from spin boxes"""
        if hasattr(self, 'y2_min_spin') and hasattr(self, 'y2_max_spin') and hasattr(self, 'y2_viewbox'):
            try:
                y_min = self.y2_min_spin.value()
                y_max = self.y2_max_spin.value()
                if y_min < y_max:
                    self.y2_viewbox.setYRange(y_min, y_max, padding=0.1)
            except (RuntimeError, AttributeError):
                # Ignore if spin boxes are deleted
                pass
    
    def update_plot_title(self, text):
        """Update plot title"""
        # Get system text color for title
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QApplication
        text_color = QApplication.palette().windowText().color()
        # Set title with proper alignment and margin to avoid overlapping with border
        self.plot_widget.setTitle(text, size='12pt', color=text_color.name(), bold=True,
                               justify='center', titlePadding=10)
    
    def update_x_label(self, text):
        """Update X-axis label"""
        # Get system text color for label
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QApplication
        text_color = QApplication.palette().windowText().color()
        self.plot_widget.setLabel('bottom', text, color=text_color.name())
    
    def update_y1_label(self, text):
        """Update Y1-axis label"""
        # Get system text color for label
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QApplication
        text_color = QApplication.palette().windowText().color()
        self.plot_widget.setLabel('left', text, color=text_color.name())
    
    def update_y2_label(self, text):
        """Update Y2-axis label"""
        # Get system text color for label
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QApplication
        text_color = QApplication.palette().windowText().color()
        self.plot_widget.setLabel('right', text, color=text_color.name())
    
    def show_settings(self):
        """Show settings widget as independent window"""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, QGroupBox, QGridLayout, QPushButton
        from PyQt6.QtCore import Qt
        
        # Create independent widget instead of dialog
        # Store as instance variable to prevent it from being garbage collected
        self.settings_widget = QWidget()
        self.settings_widget.setWindowTitle("Wave Viewer Settings")
        self.settings_widget.setMinimumWidth(500)
        # Set window flags to make it independent
        self.settings_widget.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        layout = QVBoxLayout()
        
        # Create plot title edit
        title_layout = QHBoxLayout()
        title_label = QLabel("Plot Title:")
        self.plot_title_edit = QLineEdit()
        self.plot_title_edit.setPlaceholderText("Enter plot title...")
        self.plot_title_edit.textChanged.connect(self.update_plot_title)
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.plot_title_edit)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        layout.addLayout(title_layout)
        
        # Create axes settings
        axes_group = QGroupBox("Axes Settings")
        axes_group_layout = QHBoxLayout()
        # Set spacing between panels
        axes_group_layout.setSpacing(10)
        
        # X-axis settings
        x_group = QGroupBox("X-axis")
        x_group_layout = QVBoxLayout()
        
        x_log_layout = QHBoxLayout()
        x_log_check = QCheckBox("Log")
        x_log_check.setChecked(self.x_log)
        x_log_check.stateChanged.connect(self.update_x_log)
        x_log_layout.addWidget(x_log_check)
        x_log_layout.addStretch()
        x_group_layout.addLayout(x_log_layout)
        
        # X-axis label edit
        x_label_layout = QHBoxLayout()
        x_label_edit_label = QLabel("Label:")
        self.x_label_edit = QLineEdit()
        self.x_label_edit.setPlaceholderText("X-axis label...")
        self.x_label_edit.setMaximumWidth(150)
        self.x_label_edit.textChanged.connect(self.update_x_label)
        x_label_layout.addWidget(x_label_edit_label)
        x_label_layout.addWidget(self.x_label_edit)
        x_label_layout.setContentsMargins(0, 0, 0, 0)
        x_label_layout.setSpacing(2)
        x_group_layout.addLayout(x_label_layout)
        
        # X-axis range
        x_range_layout = QGridLayout()
        x_range_label = QLabel("Range:")
        # Set label alignment
        x_range_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setDecimals(6)
        # Set minimal size for spin boxes
        self.x_min_spin.setMaximumWidth(100)
        self.x_min_spin.setMinimum(-1e9)
        self.x_min_spin.setMaximum(1e9)
        self.x_min_spin.valueChanged.connect(self.update_x_range)
        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setDecimals(6)
        self.x_max_spin.setMaximumWidth(100)
        self.x_max_spin.setMinimum(-1e9)
        self.x_max_spin.setMaximum(1e9)
        self.x_max_spin.valueChanged.connect(self.update_x_range)
        self.x_auto_btn = QPushButton("Auto")
        self.x_auto_btn.clicked.connect(self.auto_x_range)
        # Set minimal size for buttons
        self.x_auto_btn.setMaximumWidth(80)
        
        x_range_layout.addWidget(x_range_label, 0, 0)
        x_range_layout.addWidget(QLabel("Min:"), 1, 0)
        x_range_layout.addWidget(self.x_min_spin, 1, 1)
        x_range_layout.addWidget(QLabel("Max:"), 2, 0)
        x_range_layout.addWidget(self.x_max_spin, 2, 1)
        x_range_layout.addWidget(self.x_auto_btn, 3, 0, 1, 2)
        # Set minimal spacing for range layout
        x_range_layout.setContentsMargins(0, 0, 0, 0)
        x_range_layout.setSpacing(2)
        x_group_layout.addLayout(x_range_layout)
        
        x_group.setLayout(x_group_layout)
        axes_group_layout.addWidget(x_group)
        
        # Y1-axis settings
        y1_group = QGroupBox("Y1-axis")
        y1_group_layout = QVBoxLayout()
        
        y1_log_layout = QHBoxLayout()
        y1_log_check = QCheckBox("Log")
        y1_log_check.setChecked(self.y1_log)
        y1_log_check.stateChanged.connect(self.update_y1_log)
        y1_log_layout.addWidget(y1_log_check)
        y1_log_layout.addStretch()
        y1_group_layout.addLayout(y1_log_layout)
        
        # Y1-axis label edit
        y1_label_layout = QHBoxLayout()
        y1_label_edit_label = QLabel("Label:")
        self.y1_label_edit = QLineEdit()
        self.y1_label_edit.setPlaceholderText("Y1-axis label...")
        self.y1_label_edit.setMaximumWidth(150)
        self.y1_label_edit.textChanged.connect(self.update_y1_label)
        y1_label_layout.addWidget(y1_label_edit_label)
        y1_label_layout.addWidget(self.y1_label_edit)
        y1_label_layout.setContentsMargins(0, 0, 0, 0)
        y1_label_layout.setSpacing(2)
        y1_group_layout.addLayout(y1_label_layout)
        
        # Y1-axis range
        y1_range_layout = QGridLayout()
        y1_range_label = QLabel("Range:")
        # Set label alignment
        y1_range_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.y1_min_spin = QDoubleSpinBox()
        self.y1_min_spin.setDecimals(6)
        # Set minimal size for spin boxes
        self.y1_min_spin.setMaximumWidth(100)
        self.y1_min_spin.setMinimum(-1e9)
        self.y1_min_spin.setMaximum(1e9)
        self.y1_min_spin.valueChanged.connect(self.update_y1_range)
        self.y1_max_spin = QDoubleSpinBox()
        self.y1_max_spin.setDecimals(6)
        self.y1_max_spin.setMaximumWidth(100)
        self.y1_max_spin.setMinimum(-1e9)
        self.y1_max_spin.setMaximum(1e9)
        self.y1_max_spin.valueChanged.connect(self.update_y1_range)
        self.y1_auto_btn = QPushButton("Auto")
        self.y1_auto_btn.clicked.connect(self.auto_y1_range)
        # Set minimal size for buttons
        self.y1_auto_btn.setMaximumWidth(80)
        
        y1_range_layout.addWidget(y1_range_label, 0, 0)
        y1_range_layout.addWidget(QLabel("Min:"), 1, 0)
        y1_range_layout.addWidget(self.y1_min_spin, 1, 1)
        y1_range_layout.addWidget(QLabel("Max:"), 2, 0)
        y1_range_layout.addWidget(self.y1_max_spin, 2, 1)
        y1_range_layout.addWidget(self.y1_auto_btn, 3, 0, 1, 2)
        # Set minimal spacing for range layout
        y1_range_layout.setContentsMargins(0, 0, 0, 0)
        y1_range_layout.setSpacing(2)
        y1_group_layout.addLayout(y1_range_layout)
        
        y1_group.setLayout(y1_group_layout)
        axes_group_layout.addWidget(y1_group)
        
        # Y2-axis settings
        y2_group = QGroupBox("Y2-axis")
        y2_group_layout = QVBoxLayout()
        
        y2_log_layout = QHBoxLayout()
        y2_log_check = QCheckBox("Log")
        y2_log_check.setChecked(self.y2_log)
        y2_log_check.stateChanged.connect(self.update_y2_log)
        y2_log_layout.addWidget(y2_log_check)
        y2_log_layout.addStretch()
        y2_group_layout.addLayout(y2_log_layout)
        
        # Y2-axis label edit
        y2_label_layout = QHBoxLayout()
        y2_label_edit_label = QLabel("Label:")
        self.y2_label_edit = QLineEdit()
        self.y2_label_edit.setPlaceholderText("Y2-axis label...")
        self.y2_label_edit.setMaximumWidth(150)
        self.y2_label_edit.textChanged.connect(self.update_y2_label)
        y2_label_layout.addWidget(y2_label_edit_label)
        y2_label_layout.addWidget(self.y2_label_edit)
        y2_label_layout.setContentsMargins(0, 0, 0, 0)
        y2_label_layout.setSpacing(2)
        y2_group_layout.addLayout(y2_label_layout)
        
        # Y2-axis range
        y2_range_layout = QGridLayout()
        y2_range_label = QLabel("Range:")
        # Set label alignment
        y2_range_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.y2_min_spin = QDoubleSpinBox()
        self.y2_min_spin.setDecimals(6)
        # Set minimal size for spin boxes
        self.y2_min_spin.setMaximumWidth(100)
        self.y2_min_spin.setMinimum(-1e9)
        self.y2_min_spin.setMaximum(1e9)
        self.y2_min_spin.valueChanged.connect(self.update_y2_range)
        self.y2_max_spin = QDoubleSpinBox()
        self.y2_max_spin.setDecimals(6)
        self.y2_max_spin.setMaximumWidth(100)
        self.y2_max_spin.setMinimum(-1e9)
        self.y2_max_spin.setMaximum(1e9)
        self.y2_max_spin.valueChanged.connect(self.update_y2_range)
        self.y2_auto_btn = QPushButton("Auto")
        self.y2_auto_btn.clicked.connect(self.auto_y2_range)
        # Set minimal size for buttons
        self.y2_auto_btn.setMaximumWidth(80)
        
        y2_range_layout.addWidget(y2_range_label, 0, 0)
        y2_range_layout.addWidget(QLabel("Min:"), 1, 0)
        y2_range_layout.addWidget(self.y2_min_spin, 1, 1)
        y2_range_layout.addWidget(QLabel("Max:"), 2, 0)
        y2_range_layout.addWidget(self.y2_max_spin, 2, 1)
        y2_range_layout.addWidget(self.y2_auto_btn, 3, 0, 1, 2)
        # Set minimal spacing for range layout
        y2_range_layout.setContentsMargins(0, 0, 0, 0)
        y2_range_layout.setSpacing(2)
        y2_group_layout.addLayout(y2_range_layout)
        
        y2_group.setLayout(y2_group_layout)
        axes_group_layout.addWidget(y2_group)
        
        axes_group.setLayout(axes_group_layout)
        layout.addWidget(axes_group)
        
        # Create buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.settings_widget.close)
        button_layout.addWidget(ok_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.settings_widget.setLayout(layout)
        self.settings_widget.show()
    
    def edit_trace_alias(self):
        """Edit trace alias"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLineEdit, QPushButton, QHBoxLayout
        
        if not self.traces:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Trace Aliases")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Create list widget for traces
        list_widget = QListWidget()
        for i, (expr, plot_item, y_axis) in enumerate(self.traces):
            list_widget.addItem(f"{i+1}. {expr}")
        
        list_widget.currentRowChanged.connect(lambda row: self._update_alias_edit(row, alias_edit, list_widget))
        layout.addWidget(list_widget)
        
        # Create alias edit
        alias_layout = QHBoxLayout()
        alias_label = QLabel("Alias:")
        alias_edit = QLineEdit()
        alias_layout.addWidget(alias_label)
        alias_layout.addWidget(alias_edit)
        layout.addLayout(alias_layout)
        
        # Create buttons
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(lambda: self._apply_trace_alias(list_widget.currentRow(), alias_edit.text(), list_widget))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def edit_trace_properties(self):
        """Edit trace properties (alias, color, line width)"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLineEdit, QPushButton, QHBoxLayout, QLabel, QComboBox
        
        if not self.traces:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Trace Properties")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Create list widget for traces
        list_widget = QListWidget()
        for i, (expr, plot_item, y_axis) in enumerate(self.traces):
            list_widget.addItem(f"{i+1}. {expr}")
        
        layout.addWidget(list_widget)
        
        # Create alias edit
        alias_layout = QHBoxLayout()
        alias_label = QLabel("Alias:")
        self.alias_edit = QLineEdit()
        alias_layout.addWidget(alias_label)
        alias_layout.addWidget(self.alias_edit)
        layout.addLayout(alias_layout)
        
        # Create color combo
        color_layout = QHBoxLayout()
        color_label = QLabel("Color:")
        self.color_combo = QComboBox()
        # Add color options
        colors = [
            ("Default (auto)", None),
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
            ("Yellow", (255, 255, 0)),
            ("Magenta", (255, 0, 255)),
            ("Cyan", (0, 255, 255)),
            ("Orange", (255, 165, 0)),
            ("Purple", (128, 0, 128)),
            ("Brown", (165, 42, 42))
        ]
        for color_name, color_value in colors:
            self.color_combo.addItem(color_name, color_value)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_combo)
        layout.addLayout(color_layout)
        
        # Create line width combo
        width_layout = QHBoxLayout()
        width_label = QLabel("Line width:")
        self.width_combo = QComboBox()
        # Add line width options
        widths = [1, 2, 3, 4, 5]
        for width in widths:
            self.width_combo.addItem(str(width), width)
        width_layout.addWidget(width_label)
        width_layout.addWidget(self.width_combo)
        layout.addLayout(width_layout)
        
        # Connect list selection change to update all fields
        list_widget.currentRowChanged.connect(lambda row: self._update_trace_properties(row, list_widget))
        
        # Create buttons
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(lambda: self._apply_trace_properties(list_widget.currentRow(), list_widget))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def _update_alias_edit(self, row, alias_edit, list_widget):
        """Update alias edit with current trace name"""
        if 0 <= row < len(self.traces):
            expr, plot_item, y_axis = self.traces[row]
            alias_edit.setText(expr)
    
    def _apply_trace_alias(self, row, alias, list_widget):
        """Apply trace alias"""
        if 0 <= row < len(self.traces) and alias:
            expr, plot_item, y_axis = self.traces[row]
            # Update trace name in legend
            plot_item.opts['name'] = alias
            # Update list widget
            list_widget.item(row).setText(f"{row+1}. {alias}")
            # Update traces list
            self.traces[row] = (alias, plot_item, y_axis)
            # Clear and re-add legend items with Y-axis prefix
            self.legend.clear()
            for var, item, y_axis in self.traces:
                legend_name = f"{var} @ {y_axis}"
                self.legend.addItem(item, legend_name)
    
    def _update_trace_properties(self, row, list_widget):
        """Update trace properties fields with current trace values"""
        if 0 <= row < len(self.traces):
            expr, plot_item, y_axis = self.traces[row]
            # Update alias field
            self.alias_edit.setText(expr)
            
            # Update color combo
            current_color = plot_item.opts['pen'].color()
            current_rgb = (current_color.red(), current_color.green(), current_color.blue())
            
            # Find matching color in combo
            color_index = 0  # Default to "Default (auto)"
            for i in range(self.color_combo.count()):
                color_value = self.color_combo.itemData(i)
                if color_value == current_rgb:
                    color_index = i
                    break
            self.color_combo.setCurrentIndex(color_index)
            
            # Update line width combo
            current_width = plot_item.opts['pen'].width()
            width_index = 0  # Default to 1
            for i in range(self.width_combo.count()):
                width_value = self.width_combo.itemData(i)
                if width_value == current_width:
                    width_index = i
                    break
            self.width_combo.setCurrentIndex(width_index)
    
    def _apply_trace_properties(self, row, list_widget):
        """Apply trace properties (alias, color, line width)"""
        if 0 <= row < len(self.traces):
            expr, plot_item, y_axis = self.traces[row]
            
            # Get new values
            new_alias = self.alias_edit.text().strip()
            new_color = self.color_combo.currentData()
            new_width = self.width_combo.currentData()
            
            # Update alias if provided
            if new_alias:
                plot_item.opts['name'] = new_alias
                expr = new_alias
            
            # Update color if not None (None means "Default (auto)")
            if new_color is not None:
                from PyQt6.QtGui import QColor
                qcolor = QColor(*new_color)
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=qcolor, width=pen.width())
                plot_item.setPen(new_pen)
            
            # Update line width
            if new_width:
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=pen.color(), width=new_width)
                plot_item.setPen(new_pen)
            
            # Update list widget
            list_widget.item(row).setText(f"{row+1}. {expr}")
            
            # Update traces list
            self.traces[row] = (expr, plot_item, y_axis)
            
            # Clear and re-add legend items with Y-axis prefix
            self.legend.clear()
            for var, item, y_axis in self.traces:
                legend_name = f"{var} @ {y_axis}"
                self.legend.addItem(item, legend_name)

def main():
    """Main entry point for pqwave application"""
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description='Wave Viewer for SPICE raw data')
    parser.add_argument('raw_file', nargs='?', help='SPICE raw file to open (optional)')
    parser.add_argument('--version', action='version', version='pqwave 0.2.1.1')
    
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # Create window with optional initial file
    if args.raw_file:
        print(f"Opening file from command line: {args.raw_file}")
        window = WaveViewer(initial_file=args.raw_file)
    else:
        window = WaveViewer()
    
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
