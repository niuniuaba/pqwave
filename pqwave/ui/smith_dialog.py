#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SmithVectorDialog - select complex vector and reference impedance Z0.

Provided to the user so they can pick which complex vector to plot on a
Smith chart and set the reference impedance Z0.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QComboBox,
    QLabel,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
)


class SmithVectorDialog(QDialog):
    """Dialog for selecting a complex vector and reference impedance Z0."""

    def __init__(self, var_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smith Chart — Select Vector")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Complex Vector:"))
        self._var_combo = QComboBox()
        self._var_combo.addItems(var_names)
        layout.addWidget(self._var_combo)

        z0_layout = QHBoxLayout()
        z0_layout.addWidget(QLabel("Reference Impedance Z0:"))
        self._z0_spin = QDoubleSpinBox()
        self._z0_spin.setRange(0.1, 10000.0)
        self._z0_spin.setValue(50.0)
        self._z0_spin.setSuffix(" Ohm")
        self._z0_spin.setDecimals(1)
        z0_layout.addWidget(self._z0_spin)
        z0_layout.addStretch()
        layout.addLayout(z0_layout)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_vector(self) -> str:
        """Return the selected variable name."""
        return self._var_combo.currentText()

    def reference_impedance(self) -> float:
        """Return Z0 value."""
        return self._z0_spin.value()
