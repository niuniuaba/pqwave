#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dataset and Variable models for SPICE simulation data.

This module provides classes to represent SPICE datasets and variables
in a structured way, separate from the raw file parsing logic.
"""

import numpy as np
from typing import List, Optional, Union, Dict, Any


class Variable:
    """Represents a single variable (trace) in a SPICE dataset.

    A Variable can be a real or complex-valued vector with associated
    metadata such as name, type (voltage, current, time, etc.), and index.
    Complex variables provide access to magnitude, real, imaginary, and phase
    components via derived variables.
    """

    def __init__(self, name: str, index: int, var_type: str, data: np.ndarray):
        """Initialize a Variable.

        Args:
            name: Variable name (e.g., 'v(out)', 'time')
            index: Column index in the dataset's data matrix
            var_type: Type of variable ('voltage', 'current', 'time', 'frequency', 'unknown')
            data: Numerical data array (real or complex)
        """
        self.name = name
        self.index = index
        self.type = var_type
        self.data = data
        self.is_complex = np.iscomplexobj(data)

    @property
    def magnitude(self) -> np.ndarray:
        """Get magnitude of complex variable, or absolute value of real variable."""
        if self.is_complex:
            return np.abs(self.data)
        else:
            return np.abs(self.data)

    @property
    def real(self) -> np.ndarray:
        """Get real part of complex variable, or the data itself for real variable."""
        if self.is_complex:
            return np.real(self.data)
        else:
            return self.data

    @property
    def imag(self) -> np.ndarray:
        """Get imaginary part of complex variable, or zeros for real variable."""
        if self.is_complex:
            return np.imag(self.data)
        else:
            return np.zeros_like(self.data)

    @property
    def phase(self) -> np.ndarray:
        """Get phase in radians of complex variable, or zeros for real variable."""
        if self.is_complex:
            return np.angle(self.data)
        else:
            return np.zeros_like(self.data)

    def get_derived_data(self, component: str) -> np.ndarray:
        """Get derived data for a specific component.

        Args:
            component: One of 'mag', 'real', 'imag', 'ph'

        Returns:
            Derived data array

        Raises:
            ValueError: If component is invalid
        """
        if component == 'mag':
            return self.magnitude
        elif component == 'real':
            return self.real
        elif component == 'imag':
            return self.imag
        elif component == 'ph':
            return self.phase
        else:
            raise ValueError(f"Invalid component: {component}")

    def __repr__(self) -> str:
        return f"Variable(name='{self.name}', index={self.index}, type='{self.type}', complex={self.is_complex})"


class Dataset:
    """Represents a single SPICE simulation dataset.

    A Dataset contains metadata (title, date, plotname, flags), a list of
    Variable objects, and the raw data matrix. It provides methods to access
    variables by name and retrieve variable data, handling complex variables
    and derived components transparently.
    """

    def __init__(self, raw_file: 'RawFile', dataset_idx: int = 0):
        """Initialize a Dataset from a RawFile.

        Args:
            raw_file: RawFile instance containing parsed data
            dataset_idx: Index of the dataset within the raw file (0-based)

        Raises:
            IndexError: If dataset_idx is out of range
        """
        self.raw_file = raw_file
        self.dataset_idx = dataset_idx

        if dataset_idx >= len(raw_file.datasets):
            raise IndexError(f"Dataset index {dataset_idx} out of range (max {len(raw_file.datasets)-1})")

        dataset_dict = raw_file.datasets[dataset_idx]
        self.title = dataset_dict.get('title', '')
        self.date = dataset_dict.get('date', '')
        self.plotname = dataset_dict.get('plotname', '')
        self.flags = dataset_dict.get('flags', '')
        self._data = dataset_dict.get('data')

        # Create Variable objects
        self.variables: List[Variable] = []
        var_dicts = dataset_dict.get('variables', [])
        data_matrix = dataset_dict.get('data')
        for var_dict in var_dicts:
            name = var_dict['name']
            index = var_dict['index']
            var_type = var_dict['type']
            # Reference column from memmap/column_stack directly (numpy view, no copy)
            if data_matrix is not None and data_matrix.size > 0:
                data = data_matrix[:, index]
            else:
                data = raw_file.get_variable_data(name, dataset_idx)
            if data is not None:
                var = Variable(name, index, var_type, data)
                self.variables.append(var)

        # Build name-to-variable mapping
        self._var_map: Dict[str, Variable] = {var.name: var for var in self.variables}

    @property
    def n_points(self) -> int:
        """Number of data points in the dataset."""
        if self._data is not None:
            return len(self._data)
        elif self.variables:
            return len(self.variables[0].data)
        else:
            return 0

    @property
    def n_variables(self) -> int:
        """Number of variables in the dataset."""
        return len(self.variables)

    def get_variable_names(self, include_derived: bool = False) -> List[str]:
        """Get list of variable names.

        Args:
            include_derived: If True, include derived names for complex variables
                             (mag(...), real(...), imag(...), ph(...))

        Returns:
            List of variable names
        """
        names = [var.name for var in self.variables]
        if include_derived:
            derived = []
            for var in self.variables:
                if var.is_complex:
                    derived.extend([
                        f'mag({var.name})',
                        f'real({var.name})',
                        f'imag({var.name})',
                        f'ph({var.name})'
                    ])
            names.extend(derived)
        return names

    def get_variable(self, name: str) -> Optional[Variable]:
        """Get Variable object by name.

        Handles derived variable names (mag(...), real(...), etc.) by returning
        a wrapper that provides access to the derived component.

        Args:
            name: Variable name (e.g., 'v(out)', 'mag(v(out))')

        Returns:
            Variable object or None if not found
        """
        # Check for derived variable
        if name.startswith('mag(') and name.endswith(')'):
            base_name = name[4:-1]
            var = self._var_map.get(base_name)
            if var is not None:
                # Return a wrapper variable for magnitude
                return DerivedVariable(var, 'mag')
        elif name.startswith('real(') and name.endswith(')'):
            base_name = name[5:-1]
            var = self._var_map.get(base_name)
            if var is not None:
                return DerivedVariable(var, 'real')
        elif name.startswith('imag(') and name.endswith(')'):
            base_name = name[5:-1]
            var = self._var_map.get(base_name)
            if var is not None:
                return DerivedVariable(var, 'imag')
        elif name.startswith('ph(') and name.endswith(')'):
            base_name = name[3:-1]
            var = self._var_map.get(base_name)
            if var is not None:
                return DerivedVariable(var, 'ph')

        # Regular variable
        return self._var_map.get(name)

    def get_variable_data(self, name: str) -> Optional[np.ndarray]:
        """Get data array for a variable.

        Args:
            name: Variable name (e.g., 'v(out)', 'mag(v(out))')

        Returns:
            Data array or None if variable not found
        """
        var = self.get_variable(name)
        if var is None:
            return None
        return var.data

    def __repr__(self) -> str:
        return f"Dataset(title='{self.title}', plotname='{self.plotname}', n_variables={self.n_variables}, n_points={self.n_points})"


class DerivedVariable(Variable):
    """A Variable that represents a derived component of a complex variable.

    This class wraps an existing Variable and provides access to a specific
    component (magnitude, real, imaginary, or phase) as if it were a regular
    variable.
    """

    def __init__(self, base_variable: Variable, component: str):
        """Initialize a DerivedVariable.

        Args:
            base_variable: The base complex variable
            component: One of 'mag', 'real', 'imag', 'ph'
        """
        self.base_variable = base_variable
        self.component = component
        super().__init__(
            name=f"{component}({base_variable.name})",
            index=base_variable.index,
            var_type=base_variable.type,
            data=base_variable.get_derived_data(component)
        )

    def __repr__(self) -> str:
        return f"DerivedVariable(base='{self.base_variable.name}', component='{self.component}')"