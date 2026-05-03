#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PowerAnalysisDialog — Non-modal dialog for power analysis results.
Shows summary statistics and per-cycle breakdown with adjustable
V threshold for ON/OFF detection.
"""

from __future__ import annotations

import csv
import numpy as np

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QHBoxLayout, QLabel, QGroupBox,
    QDoubleSpinBox, QFormLayout, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt

from pqwave.analysis.power_analyzer import power_analysis


class PowerAnalysisDialog(QDialog):
    """Non-modal dialog for power analysis results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Power Analysis")
        self.setMinimumSize(500, 400)
        self.resize(520, 450)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._v_data = None
        self._i_data = None
        self._t_data = None
        self._xmin = 0.0
        self._xmax = 0.0
        self._v_name = ""
        self._i_name = ""

        self._layout = QVBoxLayout()
        self._layout.setSpacing(8)

        # Header
        self._header = QLabel()
        self._header.setStyleSheet("font-weight: bold; font-size: 12px;")
        self._header.setWordWrap(True)
        self._layout.addWidget(self._header)

        # X range label
        self._range_label = QLabel()
        self._range_label.setStyleSheet("font-size: 11px; color: #666;")
        self._layout.addWidget(self._range_label)

        # Summary group
        summary_group = QGroupBox("Summary")
        self._summary_layout = QFormLayout()
        self._summary_labels = {}
        for key, label in [
            ('avg_power', 'Avg Power'),
            ('sw_loss', 'Switching Loss'),
            ('cond_loss', 'Conduction Loss'),
            ('total_loss', 'Total Loss'),
            ('v_avg_on', 'V avg (on)'),
            ('i_avg_on', 'I avg (on)'),
            ('duty', 'Duty Cycle'),
        ]:
            lbl = QLabel("—")
            self._summary_labels[key] = lbl
            self._summary_layout.addRow(label, lbl)
        summary_group.setLayout(self._summary_layout)
        self._layout.addWidget(summary_group)

        # Per-cycle breakdown
        cycle_group = QGroupBox("Per-Cycle Breakdown")
        cycle_layout = QVBoxLayout()
        self._cycle_table = QTableWidget(0, 6)
        self._cycle_table.setHorizontalHeaderLabels(
            ["Cycle", "E_sw", "E_cond", "E_total", "freq", "Duty"])
        self._cycle_table.horizontalHeader().setStretchLastSection(True)
        self._cycle_table.verticalHeader().setVisible(False)
        self._cycle_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._cycle_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        cycle_layout.addWidget(self._cycle_table)
        cycle_group.setLayout(cycle_layout)
        self._layout.addWidget(cycle_group)

        # V threshold
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("V threshold for ON/OFF detection:"))
        self._v_threshold_spin = QDoubleSpinBox()
        self._v_threshold_spin.setRange(0.0, 1e6)
        self._v_threshold_spin.setDecimals(3)
        self._v_threshold_spin.setValue(0.5)
        self._v_threshold_spin.setSuffix(" V")
        self._v_threshold_spin.setToolTip(
            "Voltage below this threshold is considered ON (conducting)")
        self._v_threshold_spin.valueChanged.connect(self._on_threshold_changed)
        thresh_layout.addWidget(self._v_threshold_spin)
        thresh_layout.addStretch()
        self._layout.addLayout(thresh_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(export_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        self._layout.addLayout(btn_layout)

        self.setLayout(self._layout)

    def set_data(
        self,
        v_name: str, i_name: str,
        v_data: np.ndarray, i_data: np.ndarray, t_data: np.ndarray,
        xmin: float, xmax: float,
    ) -> None:
        """Set trace data and analysis window.  Triggers initial computation."""
        self._v_name = v_name
        self._i_name = i_name
        self._v_data = v_data
        self._i_data = i_data
        self._t_data = t_data
        self._xmin = xmin
        self._xmax = xmax
        # Auto-detect a reasonable default threshold
        mask = (t_data >= xmin) & (t_data <= xmax)
        if mask.any():
            v_range = v_data[mask]
            default_threshold = float(np.mean(v_range))
            self._v_threshold_spin.setValue(max(0.001, default_threshold))
        self._recompute()

    def _on_threshold_changed(self) -> None:
        if self._v_data is not None:
            self._recompute()

    def _recompute(self) -> None:
        """Rerun analysis and update display."""
        v_threshold = self._v_threshold_spin.value()
        results = power_analysis(
            self._v_data, self._i_data, self._t_data,
            self._xmin, self._xmax, v_threshold,
        )

        self._header.setText(
            f"Power Analysis: {self._v_name} × {self._i_name}"
        )
        self._range_label.setText(
            f"Range: {self._xmin:.4g}s — {self._xmax:.4g}s"
            f"  ({results['num_cycles']} cycles)"
        )

        # Summary
        avg_power = results['avg_power']
        cycles = results['cycles']
        if cycles:
            e_sw_total = sum(c['e_sw'] for c in cycles)
            e_cond_total = sum(c['e_cond'] for c in cycles)
            e_total = e_sw_total + e_cond_total
            if e_total > 0:
                sw_pct = e_sw_total / e_total * 100.0
                cond_pct = e_cond_total / e_total * 100.0
                sw_power = avg_power * sw_pct / 100.0
                cond_power = avg_power * cond_pct / 100.0
            else:
                sw_pct = cond_pct = sw_power = cond_power = 0.0
            v_avg = np.mean([c['v_avg_on'] for c in cycles])
            i_avg = np.mean([c['i_avg_on'] for c in cycles])
            duty = np.mean([c['duty'] for c in cycles]) * 100.0
        else:
            sw_power = cond_power = sw_pct = cond_pct = 0.0
            v_avg = i_avg = duty = 0.0

        self._summary_labels['avg_power'].setText(f"{avg_power:.4g} W")
        self._summary_labels['sw_loss'].setText(
            f"{sw_power:.4g} W ({sw_pct:.1f}%)")
        self._summary_labels['cond_loss'].setText(
            f"{cond_power:.4g} W ({cond_pct:.1f}%)")
        self._summary_labels['total_loss'].setText(f"{avg_power:.4g} W")
        self._summary_labels['v_avg_on'].setText(f"{v_avg:.4g} V")
        self._summary_labels['i_avg_on'].setText(f"{i_avg:.4g} A")
        self._summary_labels['duty'].setText(f"{duty:.1f}%")

        self._populate_cycle_table(cycles)

    def _populate_cycle_table(self, cycles: list[dict]) -> None:
        self._cycle_table.setRowCount(0)
        for c in cycles:
            row = self._cycle_table.rowCount()
            self._cycle_table.insertRow(row)
            self._cycle_table.setItem(row, 0,
                QTableWidgetItem(str(c['cycle'])))
            self._cycle_table.setItem(row, 1,
                self._energy_item(c['e_sw']))
            self._cycle_table.setItem(row, 2,
                self._energy_item(c['e_cond']))
            self._cycle_table.setItem(row, 3,
                self._energy_item(c['e_total']))
            self._cycle_table.setItem(row, 4,
                self._freq_item(c['freq']))
            self._cycle_table.setItem(row, 5,
                self._pct_item(c['duty'] * 100.0))
        if cycles:
            row = self._cycle_table.rowCount()
            self._cycle_table.insertRow(row)
            for col, val in enumerate([
                "Mean",
                self._energy_text(np.mean([c['e_sw'] for c in cycles])),
                self._energy_text(np.mean([c['e_cond'] for c in cycles])),
                self._energy_text(np.mean([c['e_total'] for c in cycles])),
                self._freq_text(np.mean([c['freq'] for c in cycles])),
                f"{np.mean([c['duty'] for c in cycles]) * 100:.1f}%",
            ]):
                item = QTableWidgetItem(str(val))
                fg = self.palette().color(self.palette().ColorRole.Text)
                item.setForeground(fg)
                self._cycle_table.setItem(row, col, item)

    @staticmethod
    def _energy_item(value: float) -> QTableWidgetItem:
        return PowerAnalysisDialog._fmt_num(value, 1e-6, "μJ", 1e-9, "nJ", "J")

    @staticmethod
    def _energy_text(value: float) -> str:
        return PowerAnalysisDialog._fmt_str(value, 1e-6, "μJ", 1e-9, "nJ", "J")

    @staticmethod
    def _freq_item(value: float) -> QTableWidgetItem:
        return PowerAnalysisDialog._fmt_num(value, 1e6, "MHz", 1e3, "kHz", "Hz")

    @staticmethod
    def _freq_text(value: float) -> str:
        return PowerAnalysisDialog._fmt_str(value, 1e6, "MHz", 1e3, "kHz", "Hz")

    @staticmethod
    def _pct_item(value: float) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.DisplayRole, f"{value:.1f}%")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    @staticmethod
    def _fmt_num(value: float, hi: float, hi_u: str, lo: float, lo_u: str, base: str) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.DisplayRole,
                     PowerAnalysisDialog._fmt_str(value, hi, hi_u, lo, lo_u, base))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    @staticmethod
    def _fmt_str(value: float, hi: float, hi_u: str, lo: float, lo_u: str, base: str) -> str:
        if abs(value) >= hi:
            return f"{value / hi:.3f} {hi_u}"
        elif abs(value) >= lo:
            return f"{value / lo:.3f} {lo_u}"
        else:
            return f"{value:.3g} {base}"

    def _on_export(self) -> None:
        """Export power analysis results to a CSV file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Power Analysis",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return
        try:
            self._export_csv(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Failed to export:\n{e}")

    def _export_csv(self, path: str) -> None:
        """Write summary and per-cycle breakdown to CSV."""
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([self._header.text()])
            writer.writerow([self._range_label.text()])
            writer.writerow([])
            writer.writerow(["Summary"])
            for row in range(self._summary_layout.rowCount()):
                label = self._summary_layout.itemAt(
                    row, QFormLayout.ItemRole.LabelRole)
                field = self._summary_layout.itemAt(
                    row, QFormLayout.ItemRole.FieldRole)
                if label and field:
                    writer.writerow(
                        [label.widget().text(), field.widget().text()])
            if self._cycle_table.rowCount() > 0:
                writer.writerow([])
                writer.writerow(["Per-Cycle Breakdown"])
                headers = []
                for c in range(self._cycle_table.columnCount()):
                    headers.append(
                        self._cycle_table.horizontalHeaderItem(c).text())
                writer.writerow(headers)
                for r in range(self._cycle_table.rowCount()):
                    cells = []
                    for c in range(self._cycle_table.columnCount()):
                        item = self._cycle_table.item(r, c)
                        if item:
                            cells.append(
                                item.data(Qt.ItemDataRole.DisplayRole))
                        else:
                            cells.append("")
                    writer.writerow(cells)

