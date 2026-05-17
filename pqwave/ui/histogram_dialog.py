#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HistogramDialog — configuration dialog for histogram computation.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QComboBox, QDoubleSpinBox, QPushButton,
    QCheckBox, QGroupBox,
)


class HistogramDialog(QDialog):
    """Dialog for configuring histogram parameters (bins, norm, range)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Histogram")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # ---- Bins group ----
        bins_group = QGroupBox("Bins")
        bins_layout = QFormLayout(bins_group)
        self._auto_bins = QCheckBox("Auto (Sturges' rule)")
        self._auto_bins.setChecked(True)
        self._bins_spin = QSpinBox()
        self._bins_spin.setRange(1, 10000)
        self._bins_spin.setValue(50)
        self._bins_spin.setEnabled(False)
        self._auto_bins.toggled.connect(
            lambda checked: self._bins_spin.setEnabled(not checked)
        )
        bins_layout.addRow(self._auto_bins)
        bins_layout.addRow("Count:", self._bins_spin)
        layout.addWidget(bins_group)

        # ---- Normalization group ----
        norm_group = QGroupBox("Normalization")
        norm_layout = QFormLayout(norm_group)
        self._norm_combo = QComboBox()
        self._norm_combo.addItems(["count", "density", "probability"])
        norm_layout.addRow("Mode:", self._norm_combo)
        layout.addWidget(norm_group)

        # ---- Range group ----
        range_group = QGroupBox("Range")
        range_layout = QFormLayout(range_group)
        self._auto_range = QCheckBox("Auto (full data)")
        self._auto_range.setChecked(True)
        self._range_min = QDoubleSpinBox()
        self._range_min.setRange(-1e12, 1e12)
        self._range_max = QDoubleSpinBox()
        self._range_max.setRange(-1e12, 1e12)
        self._range_min.setEnabled(False)
        self._range_max.setEnabled(False)
        self._auto_range.toggled.connect(lambda checked: (
            self._range_min.setEnabled(not checked),
            self._range_max.setEnabled(not checked),
        ))
        range_layout.addRow(self._auto_range)
        range_layout.addRow("Min:", self._range_min)
        range_layout.addRow("Max:", self._range_max)
        layout.addWidget(range_group)

        # ---- Buttons ----
        btn_layout = QHBoxLayout()
        self._ok_btn = QPushButton("Show Histogram")
        self._ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_config(self):
        """Return a HistogramConfig built from current dialog values."""
        from pqwave.models.state import HistogramConfig
        return HistogramConfig(
            bins=None if self._auto_bins.isChecked() else self._bins_spin.value(),
            norm=self._norm_combo.currentText(),
            range=None if self._auto_range.isChecked() else (
                self._range_min.value(), self._range_max.value()
            ),
        )
