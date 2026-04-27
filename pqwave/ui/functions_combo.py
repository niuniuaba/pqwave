#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FunctionsCombo — QComboBox listing all expression functions and constants.
"""

from PyQt6.QtWidgets import QComboBox, QCompleter
from PyQt6.QtCore import pyqtSignal, Qt

from pqwave.ui.function_registry import FunctionInfo, get_all


class FunctionsCombo(QComboBox):
    """Dropdown listing functions and constants alphabetically for expression building.

    Each item shows a tooltip with its description on hover. Selecting an item
    emits function_selected(FunctionInfo).
    """

    function_selected = pyqtSignal(object)  # carries FunctionInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_by_index: dict[int, FunctionInfo] = {}
        self.setToolTip("Select a function to insert into the expression")
        self._populate()
        self.activated.connect(self._on_activated)

    def _populate(self):
        """Fill the combo with all functions and constants sorted alphabetically."""
        items = get_all()
        items.sort(key=lambda info: info.name)

        for info in items:
            self.addItem(info.signature)
            idx = self.count() - 1
            self._info_by_index[idx] = info
            self.setItemData(idx, info.description, Qt.ItemDataRole.ToolTipRole)

        self.setMaxVisibleItems(12)
        self.setEditable(True)
        completer = QCompleter(self.model(), self)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(completer)

    def _on_activated(self, index: int):
        """Emit function_selected when a real item is chosen."""
        info = self._info_by_index.get(index)
        if info is None:
            return
        self.setToolTip(info.description)
        self.function_selected.emit(info)

    @property
    def selected_info(self) -> FunctionInfo | None:
        """Return the currently selected FunctionInfo, or None."""
        return self._info_by_index.get(self.currentIndex())
