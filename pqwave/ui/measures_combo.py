#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MeasuresCombo — QComboBox listing all built-in measurement functions.
"""

from PyQt6.QtWidgets import QComboBox, QCompleter, QToolTip
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QCursor

from pqwave.ui.function_registry import FunctionInfo
from pqwave.ui.measure_registry import get_all_measure_functions


class MeasuresCombo(QComboBox):
    """Dropdown listing measure functions alphabetically for expression building.

    Each item shows a tooltip with its description on hover. Selecting an item
    emits function_selected(FunctionInfo).
    """

    function_selected = pyqtSignal(object)  # carries FunctionInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_by_index: dict[int, FunctionInfo] = {}
        self.setToolTip("Select a measure function to insert into the expression")
        self._populate()
        self.activated.connect(self._on_activated)

    def _populate(self):
        """Fill the combo with all measure functions sorted alphabetically."""
        items = get_all_measure_functions()
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
        self.highlighted.connect(self._on_highlighted)

    def _on_highlighted(self, index: int):
        """Show tooltip for the highlighted item during dropdown navigation."""
        info = self._info_by_index.get(index)
        if info is not None:
            QToolTip.showText(QCursor.pos(), info.description)

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
