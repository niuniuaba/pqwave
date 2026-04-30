#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MeasuresHelpDialog — Categorized, filterable reference of all measurement
functions for the Run Measure feature.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from pqwave.ui.function_registry import FunctionInfo
from pqwave.ui.measure_registry import get_measure_functions_by_category


class MeasuresHelpDialog(QDialog):
    """Modal dialog showing all measure functions in a filterable,
    categorized tree view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measures Reference")
        self.resize(550, 600)

        layout = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter measure functions...")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._all_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._populate()

    def _add_leaf(self, parent: QTreeWidgetItem, info: FunctionInfo) -> None:
        text = f"{info.signature} — {info.description}"
        item = QTreeWidgetItem(parent, [text])
        self._all_items.append((item, info.name, info.description))
        parent.addChild(item)

    def _populate(self):
        root = QTreeWidgetItem(self._tree, ["Measures"])
        categories = get_measure_functions_by_category()

        for cat, fns in categories.items():
            cat_item = QTreeWidgetItem(root, [cat])
            for fn in fns:
                self._add_leaf(cat_item, fn)

        self._tree.expandAll()

    def _apply_filter(self, text: str):
        needle = text.lower()
        for item, name, desc in self._all_items:
            visible = not needle or needle in name.lower() or needle in desc.lower()
            item.setHidden(not visible)
            if visible:
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()
