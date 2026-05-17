#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NyquistVectorDialog — select real and imaginary vectors for a Nyquist plot.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QComboBox, QLabel, QDialogButtonBox,
)


class NyquistVectorDialog(QDialog):
    """Dialog for selecting real and imaginary components of a complex vector.

    If *auto_pair* is provided (a ``(real_var, imag_var)`` tuple from
    :func:`~pqwave.analysis.nyquist.detect_nyquist_vectors`), those entries
    are pre-selected.
    """

    def __init__(self, var_names, parent=None, auto_pair=None):
        super().__init__(parent)
        self.setWindowTitle("Nyquist Plot — Select Vectors")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Real part:"))
        self._real_combo = QComboBox()
        self._real_combo.addItems(var_names)
        layout.addWidget(self._real_combo)

        layout.addWidget(QLabel("Imaginary part:"))
        self._imag_combo = QComboBox()
        self._imag_combo.addItems(var_names)
        layout.addWidget(self._imag_combo)

        if auto_pair:
            r_idx = self._real_combo.findText(auto_pair[0])
            if r_idx >= 0:
                self._real_combo.setCurrentIndex(r_idx)
            i_idx = self._imag_combo.findText(auto_pair[1])
            if i_idx >= 0:
                self._imag_combo.setCurrentIndex(i_idx)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_pair(self) -> tuple[str, str]:
        """Return the currently selected (real_var, imag_var)."""
        return (self._real_combo.currentText(), self._imag_combo.currentText())
