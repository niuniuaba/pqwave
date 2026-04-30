#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MeasureResultsWidget — modal dialog displaying scalar measurement results
in a table with export and copy functionality.
"""

from __future__ import annotations

import csv
import io

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class MeasureResultsWidget(QDialog):
    """Dialog showing batch measurement results in a table.

    Columns: #, Label, Expression, Result, Unit.
    Buttons: Delete Last, Copy Selected, Export (CSV/txt).
    Reused across sessions — closeEvent calls hide() instead of closing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measure Results")
        self.resize(700, 400)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["#", "Label", "Expression", "Result", "Unit"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        btn_layout = QHBoxLayout()
        self._delete_btn = QPushButton("Delete Last")
        self._delete_btn.clicked.connect(self._delete_last)
        btn_layout.addWidget(self._delete_btn)

        self._copy_btn = QPushButton("Copy Selected")
        self._copy_btn.clicked.connect(self._copy_selected)
        btn_layout.addWidget(self._copy_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.clicked.connect(self._export)
        btn_layout.addWidget(self._export_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._counter = 0

    def add_result(
        self, label: str, expr: str, value: float, unit: str = ""
    ) -> None:
        """Append a successful result row."""
        self._counter += 1
        row = self._table.rowCount()
        self._table.insertRow(row)

        items = [
            QTableWidgetItem(str(self._counter)),
            QTableWidgetItem(label),
            QTableWidgetItem(expr),
            QTableWidgetItem(f"{value:.6g}"),
            QTableWidgetItem(unit),
        ]
        for col, item in enumerate(items):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, col, item)

        self._table.scrollToBottom()

    def add_error(self, label: str, expr: str, error_msg: str) -> None:
        """Append an error row (highlighted in red)."""
        self._counter += 1
        row = self._table.rowCount()
        self._table.insertRow(row)

        items = [
            QTableWidgetItem(str(self._counter)),
            QTableWidgetItem(label),
            QTableWidgetItem(expr),
            QTableWidgetItem(error_msg),
            QTableWidgetItem(""),
        ]
        for col, item in enumerate(items):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(200, 0, 0))
            self._table.setItem(row, col, item)

        self._table.scrollToBottom()

    def clear_all(self) -> None:
        """Remove all result rows."""
        self._table.setRowCount(0)
        self._counter = 0

    def _delete_last(self) -> None:
        row = self._table.rowCount()
        if row > 0:
            self._table.removeRow(row - 1)
            if self._counter > 0:
                self._counter -= 1

    def _copy_selected(self) -> None:
        selected = self._table.selectedRanges()
        if not selected:
            return
        rows = set()
        for rng in selected:
            for r in range(rng.topRow(), rng.bottomRow() + 1):
                rows.add(r)

        lines: list[str] = []
        for r in sorted(rows):
            cols = []
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                cols.append(item.text() if item else "")
            lines.append("\t".join(cols))

        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results",
            "",
            "CSV Files (*.csv);;Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return

        delimiter = "," if path.endswith(".csv") else "\t"
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter)

        headers = []
        for c in range(self._table.columnCount()):
            h = self._table.horizontalHeaderItem(c)
            headers.append(h.text() if h else "")
        writer.writerow(headers)

        for r in range(self._table.rowCount()):
            row_data = []
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                row_data.append(item.text() if item else "")
            writer.writerow(row_data)

        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(buf.getvalue())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
