#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RawFile - SPICE raw file parsing using spicelib
"""

import numpy as np

try:
    from spicelib import RawRead
    SPICELIB_AVAILABLE = True
except ImportError:
    SPICELIB_AVAILABLE = False
    RawRead = None


class RawFile:
    """Parse NGSPICE raw files using spicelib"""
    def __init__(self, filename):
        self.filename = filename
        self.datasets = []
        self.raw_data = None
        self.parse()

    def parse(self):
        """Parse the raw file using spicelib"""
        if not SPICELIB_AVAILABLE:
            raise ImportError("spicelib is not available. Install with: pip install spicelib")

        try:
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


if __name__ == "__main__":
    # Simple test
    import sys
    if len(sys.argv) > 1:
        rf = RawFile(sys.argv[1])
        print(f"File: {rf.filename}")
        print(f"Datasets: {len(rf.datasets)}")
        if rf.datasets:
            print(f"Variables: {rf.get_variable_names()}")
    else:
        print("Usage: python rawfile.py <rawfile>")