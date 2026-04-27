#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FunctionsHelpDialog — Categorized, filterable reference of all expression
functions and constants.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from pqwave.ui.function_registry import (
    get_all_functions,
    get_all_constants,
    FunctionInfo,
)


class FunctionsHelpDialog(QDialog):
    """Modal dialog showing all expression functions and constants
    in a filterable, categorized tree view.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Functions Reference")
        self.resize(550, 600)

        layout = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter functions...")
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
        """Add a leaf item showing signature and description."""
        text = f"{info.signature} — {info.description}"
        item = QTreeWidgetItem(parent, [text])
        self._all_items.append((item, info.name, info.description))
        parent.addChild(item)

    def _populate(self):
        """Build the tree with Functions > category > item and Operators > item."""
        # Functions top-level node
        funcs_root = QTreeWidgetItem(self._tree, ["Functions"])

        functions = get_all_functions()
        constants = get_all_constants()

        # Group functions by category
        categories: dict[str, list[FunctionInfo]] = {}
        for fn in functions:
            categories.setdefault(fn.category, []).append(fn)

        for cat, fns in categories.items():
            cat_item = QTreeWidgetItem(funcs_root, [cat])
            for fn in fns:
                self._add_leaf(cat_item, fn)

        # Constants as sub-category under Functions
        if constants:
            const_item = QTreeWidgetItem(funcs_root, ["Constants"])
            for c in constants:
                self._add_leaf(const_item, c)

        self._tree.expandAll()

    def _apply_filter(self, text: str):
        """Show/hide tree items based on filter text."""
        needle = text.lower()
        for item, name, desc in self._all_items:
            visible = not needle or needle in name.lower() or needle in desc.lower()
            item.setHidden(not visible)
            # If a leaf is visible, ensure its parent chain is also visible
            if visible:
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()
