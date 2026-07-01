#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""PolarVectorDialog -- select magnitude and phase vectors for a polar plot."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QComboBox,
    QLabel,
    QDialogButtonBox,
)


class PolarVectorDialog(QDialog):
    """Dialog for selecting magnitude and phase vectors.

    If *auto_pair* is provided (from detect_polar_vectors), those entries
    are pre-selected.
    """

    def __init__(self, var_names, parent=None, auto_pair=None):
        super().__init__(parent)
        self.setWindowTitle("Polar Plot -- Select Vectors")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Magnitude:"))
        self._mag_combo = QComboBox()
        self._mag_combo.addItems(var_names)
        layout.addWidget(self._mag_combo)

        layout.addWidget(QLabel("Phase:"))
        self._phase_combo = QComboBox()
        self._phase_combo.addItems(var_names)
        layout.addWidget(self._phase_combo)

        if auto_pair:
            m_idx = self._mag_combo.findText(auto_pair[0])
            if m_idx >= 0:
                self._mag_combo.setCurrentIndex(m_idx)
            p_idx = self._phase_combo.findText(auto_pair[1])
            if p_idx >= 0:
                self._phase_combo.setCurrentIndex(p_idx)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_pair(self) -> tuple[str, str]:
        """Return (magnitude_var, phase_var) tuple."""
        return (self._mag_combo.currentText(), self._phase_combo.currentText())
