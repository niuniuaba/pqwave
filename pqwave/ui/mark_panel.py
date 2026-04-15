#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MarkPanel - Data display panel for cross-hair cursor marks.

This module provides a standalone dialog that displays mark coordinates
(index, X, Y1, Y2) and supports deletion, export, and clipboard operations.
"""

import csv
import io

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent


class MarkPanel(QDialog):
    """Standalone panel displaying mark coordinates from cross-hair cursor.

    Lives for the duration of one cross-hair session (ON to OFF).
    When closed by the parent, all marks are cleared.

    Signals:
        mark_deleted_last: Emitted when the last mark is deleted via button
        window_closed: Emitted when user clicks the window close button
    """

    mark_deleted_last = pyqtSignal()
    window_closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mark Data")
        self.setMinimumSize(420, 300)
        self.setWindowFlags(Qt.WindowType.Window)

        self._setup_ui()

        # Internal data store: list of (x, y1, y2) tuples
        self._marks = []

    def _setup_ui(self):
        """Build the panel layout."""
        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Index", "X", "Y1", "Y2"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Buttons row
        btn_layout = QHBoxLayout()

        self.delete_last_btn = QPushButton("Delete Last")
        self.delete_last_btn.clicked.connect(self._on_delete_last)
        btn_layout.addWidget(self.delete_last_btn)

        self.copy_btn = QPushButton("Copy Selected")
        self.copy_btn.clicked.connect(self._on_copy_selected)
        btn_layout.addWidget(self.copy_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(self.export_btn)

        layout.addLayout(btn_layout)

    def add_mark(self, x: float, y1: float, y2: float) -> None:
        """Add a new mark to the panel.

        Args:
            x: X coordinate
            y1: Y1 axis coordinate
            y2: Y2 axis coordinate (NaN if Y2 axis not available)
        """
        import math
        self._marks.append((x, y1, y2))

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 1, QTableWidgetItem(f"{x:.6g}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{y1:.6g}"))
        if math.isnan(y2):
            self.table.setItem(row, 3, QTableWidgetItem("-"))
        else:
            self.table.setItem(row, 3, QTableWidgetItem(f"{y2:.6g}"))

        # Scroll to bottom
        self.table.scrollToBottom()

    def delete_last_mark(self) -> bool:
        """Remove the most recently added mark.

        Returns:
            True if a mark was removed, False if no marks exist.
        """
        if not self._marks:
            return False
        self._marks.pop()
        self.table.removeRow(self.table.rowCount() - 1)
        self.mark_deleted_last.emit()
        return True

    def clear_all_marks(self) -> None:
        """Remove all marks and reset the table."""
        self._marks.clear()
        self.table.setRowCount(0)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close button — just hide, don't destroy."""
        event.ignore()
        self.window_closed.emit()
        self.hide()

    @property
    def mark_count(self) -> int:
        return len(self._marks)

    def _on_delete_last(self) -> None:
        """Handle Delete Last button click."""
        self.delete_last_mark()

    def _on_copy_selected(self) -> None:
        """Copy selected rows to clipboard as tab-separated text."""
        from PyQt6.QtWidgets import QApplication

        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
        )
        if not selected_rows:
            # Copy all marks if nothing selected
            selected_rows = list(range(self.table.rowCount()))
            if not selected_rows:
                return

        lines = ["Index\tX\tY1\tY2"]
        for row in selected_rows:
            vals = []
            for col in range(4):
                item = self.table.item(row, col)
                vals.append(item.text() if item else "-")
            lines.append("\t".join(vals))

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(lines))

    def _on_export(self) -> None:
        """Export marks to a file (CSV or plain text)."""
        if not self._marks:
            QMessageBox.information(self, "No Data", "No marks to export.")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Marks",
            "",
            "CSV Files (*.csv);;Text Files (*.txt);;All Files (*)"
        )
        if not file_path:
            return

        try:
            if selected_filter.startswith("CSV"):
                self._export_csv(file_path)
            else:
                self._export_text(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    def _export_csv(self, path: str) -> None:
        """Export marks to CSV format."""
        import math
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Index", "X", "Y1", "Y2"])
            for i, (x, y1, y2) in enumerate(self._marks, 1):
                y2_str = "" if math.isnan(y2) else y2
                writer.writerow([i, x, y1, y2_str])

    def _export_text(self, path: str) -> None:
        """Export marks to plain text format."""
        import math
        with open(path, "w") as f:
            f.write(f"{'Index':>5}  {'X':>14}  {'Y1':>14}  {'Y2':>14}\n")
            f.write("-" * 57 + "\n")
            for i, (x, y1, y2) in enumerate(self._marks, 1):
                y2_str = "-" if math.isnan(y2) else f"{y2:.6g}"
                f.write(f"{i:>5}  {x:>14.6g}  {y1:>14.6g}  {y2_str:>14}\n")
