#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TraceAnalysisDialog — Non-modal dialog showing tabulated statistics for
one or more traces over the visible X range.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QHBoxLayout, QLabel, QApplication, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt


class TraceAnalysisDialog(QDialog):
    """Non-modal, independently movable dialog with one tab per trace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trace Statistics")
        self.setMinimumSize(400, 300)
        self.resize(420, 320)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._layout = QVBoxLayout()
        self._layout.setSpacing(8)

        # Region label (shared across all traces)
        self._region_label = QLabel()
        self._region_label.setStyleSheet("font-size: 11px; color: #666;")
        self._region_label.setWordWrap(True)
        self._layout.addWidget(self._region_label)

        # Tab widget — one tab per trace
        self._tabs = QTabWidget()
        self._layout.addWidget(self._tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        self._layout.addLayout(btn_layout)

        self.setLayout(self._layout)

    def set_region_str(self, text: str) -> None:
        """Set the shared X range label."""
        self._region_label.setText(f"Range: {text}")

    def add_trace_result(self, trace_name: str, metrics: dict) -> None:
        """Add a tab with one trace's computed statistics.

        Args:
            trace_name: Name of the trace (e.g. 'v(out)')
            metrics: Dict of metric_name -> value.
        """
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(4)

        # Table
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        for metric, value in metrics.items():
            if value is None:
                continue
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(metric))
            item = QTableWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, value)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, 1, item)
        table.resizeColumnsToContents()

        layout.addWidget(table)
        tab.setLayout(layout)

        # Short tab label
        label = trace_name[:18] + "..." if len(trace_name) > 20 else trace_name
        self._tabs.addTab(tab, label)

    def _copy_to_clipboard(self) -> None:
        """Copy all tabs' contents as TSV to clipboard."""
        lines = [self._region_label.text(), ""]
        for i in range(self._tabs.count()):
            lines.append(f"--- {self._tabs.tabText(i)} ---")
            tab = self._tabs.widget(i)
            table = tab.findChild(QTableWidget)
            if table is None:
                continue
            for row in range(table.rowCount()):
                item0 = table.item(row, 0)
                item1 = table.item(row, 1)
                if item0 is None or item1 is None:
                    continue
                metric = item0.text()
                val = item1.data(Qt.ItemDataRole.DisplayRole)
                lines.append(f"{metric}\t{val}")
            lines.append("")
        QApplication.clipboard().setText('\n'.join(lines))
