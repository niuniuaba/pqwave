#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BodeDialog — select magnitude (dB), phase (deg), and frequency vectors.

Provides a simple dialog to let the user pick the three vectors needed
for a Bode plot.  If *auto_pair* is provided (a ``(mag, phase, freq)``
tuple from :func:`~pqwave.analysis.bode.detect_bode_vectors`), those
entries are pre-selected.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QComboBox,
    QLabel,
    QDialogButtonBox,
)


class BodeDialog(QDialog):
    """Dialog for selecting magnitude, phase, and frequency vectors."""

    def __init__(self, var_names, parent=None, auto_pair=None):
        super().__init__(parent)
        self.setWindowTitle("Bode Plot — Select Vectors")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Magnitude (dB):"))
        self._mag_combo = QComboBox()
        self._mag_combo.addItems(var_names)
        layout.addWidget(self._mag_combo)

        layout.addWidget(QLabel("Phase (degrees):"))
        self._phase_combo = QComboBox()
        self._phase_combo.addItems(var_names)
        layout.addWidget(self._phase_combo)

        layout.addWidget(QLabel("Frequency:"))
        self._freq_combo = QComboBox()
        self._freq_combo.addItems(["(auto)"] + var_names)
        layout.addWidget(self._freq_combo)

        if auto_pair:
            mag, phase, freq = auto_pair
            idx = self._mag_combo.findText(mag)
            if idx >= 0:
                self._mag_combo.setCurrentIndex(idx)
            idx = self._phase_combo.findText(phase)
            if idx >= 0:
                self._phase_combo.setCurrentIndex(idx)
            if freq:
                idx = self._freq_combo.findText(freq)
                if idx >= 0:
                    self._freq_combo.setCurrentIndex(idx)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_vectors(self) -> tuple[str, str, str | None]:
        """Return the currently selected (mag, phase, freq) vector names.

        Returns:
            ``(mag_var, phase_var, freq_var)`` where ``freq_var`` is
            ``None`` when ``"(auto)"`` is selected.
        """
        freq = self._freq_combo.currentText()
        if freq == "(auto)":
            freq = None
        return (self._mag_combo.currentText(), self._phase_combo.currentText(), freq)
