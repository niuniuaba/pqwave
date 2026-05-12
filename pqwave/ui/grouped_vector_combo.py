"""GroupedVectorCombo — combo-box lookalike with grouped, multi-select popup.

Replaces the flat QComboBox for vector selection.  Supports multi-file
sessions by grouping vectors under their source file name and allows
Ctrl+click / Shift+click multi-selection via ExtendedSelection mode.
"""

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QApplication, QFrame,
)


class _PopupFrame(QFrame):
    """Frameless popup that emits closed on hide (any hide cause)."""
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)

    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)


class GroupedVectorCombo(QWidget):
    """A combo-box-like widget with a grouped, checkable tree popup.

    Signals:
        vectors_selected(str): space-separated names of selected vectors.
    """

    vectors_selected = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._groups: Dict[str, List[str]] = {}
        self._group_items: Dict[str, QTreeWidgetItem] = {}
        self._all_items: Dict[str, QTreeWidgetItem] = {}
        self._popup: Optional[_PopupFrame] = None
        self._suppress_reopen: bool = False
        self._skip_close_emit: bool = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._line_edit = QLineEdit()
        self._line_edit.setReadOnly(True)
        self._line_edit.setPlaceholderText("Select vectors...")
        layout.addWidget(self._line_edit)

        self._btn = QPushButton("▼")
        self._btn.setFixedWidth(24)
        self._btn.clicked.connect(self._toggle_popup)
        layout.addWidget(self._btn)

        self.setMinimumWidth(250)
        self.setMaximumWidth(500)

    # -- popup ----------------------------------------------------------------

    def _toggle_popup(self) -> None:
        if self._popup is not None:
            # hideEvent → closed → _on_popup_closed → _emit_selection
            self._popup.hide()
            return
        if self._suppress_reopen:
            return
        self._show_popup()

    def _show_popup(self) -> None:
        popup = _PopupFrame(self)
        popup.closed.connect(lambda: self._on_popup_closed(popup))
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        search = QLineEdit()
        search.setPlaceholderText("Filter...")
        search.textChanged.connect(lambda t: self._filter(t))
        layout.addWidget(search)

        # Tree
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection)
        tree.setRootIsDecorated(True)
        tree.itemChanged.connect(self._on_item_changed)
        tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        layout.addWidget(tree)
        popup._tree = tree
        popup._search = search

        # Populate
        self._populate_tree(tree)

        # Position below the widget
        pos = self.mapToGlobal(QPoint(0, self.height()))
        popup.setMinimumWidth(self.width())
        popup.setMaximumHeight(400)
        popup.move(pos)
        popup.show()
        search.setFocus()

        self._popup = popup

    def _on_popup_closed(self, popup: _PopupFrame) -> None:
        if self._skip_close_emit:
            self._skip_close_emit = False
        else:
            self._emit_selection()
        self._popup = None
        self._suppress_reopen = True
        QTimer.singleShot(100, self._clear_suppress)

    def _clear_suppress(self) -> None:
        self._suppress_reopen = False

    # -- population -----------------------------------------------------------

    def set_groups(self, groups: Dict[str, List[str]]) -> None:
        """Replace all groups.  *groups* maps source-file label → variable names."""
        self._groups = groups
        self._all_items.clear()
        self._group_items.clear()
        if self._popup is not None and self._popup.isVisible():
            self._popup._tree.clear()
            self._populate_tree(self._popup._tree)
        self._update_summary()

    def _populate_tree(self, tree: QTreeWidget) -> None:
        tree.clear()
        bold = QFont()
        bold.setBold(True)

        for group_label, vectors in self._groups.items():
            grp = QTreeWidgetItem(tree)
            grp.setText(0, group_label)
            grp.setFont(0, bold)
            grp.setFlags(grp.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            grp.setExpanded(True)
            self._group_items[group_label] = grp

            for name in vectors:
                item = QTreeWidgetItem(grp)
                item.setText(0, name)
                item.setToolTip(0, name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                self._all_items[name] = item

    # -- interaction ----------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.parent() is None:
            return  # ignore group headers
        self._update_summary()

    def _on_tree_selection_changed(self) -> None:
        """Sync check states from selection after Ctrl/Shift+click.

        Re-entrancy guard prevents fighting with native checkbox-click toggles.
        """
        if getattr(self, '_syncing_checks', False):
            return
        QTimer.singleShot(0, self._sync_checks_from_selection)

    def _sync_checks_from_selection(self) -> None:
        popup = self._popup
        if popup is None:
            return
        tree = getattr(popup, '_tree', None)
        if tree is None:
            return

        selected_ids = set()
        for item in tree.selectedItems():
            if item.parent() is not None:
                selected_ids.add(id(item))

        self._syncing_checks = True
        try:
            for name, item in self._all_items.items():
                should_check = id(item) in selected_ids
                current = item.checkState(0) == Qt.CheckState.Checked
                if should_check != current:
                    item.setCheckState(
                        0, Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
        finally:
            self._syncing_checks = False

        self._update_summary()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.parent() is None:
            return
        self.vectors_selected.emit(item.text(0))
        self._skip_close_emit = True
        if self._popup is not None:
            self._popup.hide()

    def _filter(self, text: str) -> None:
        if self._popup is None:
            return
        tree = self._popup._tree
        lower = text.lower()
        for i in range(tree.topLevelItemCount()):
            grp = tree.topLevelItem(i)
            visible_children = 0
            for j in range(grp.childCount()):
                child = grp.child(j)
                match = (not lower) or (lower in child.text(0).lower())
                child.setHidden(not match)
                if match:
                    visible_children += 1
            grp.setHidden(visible_children == 0)

    def _update_summary(self) -> None:
        checked = []
        for name, item in self._all_items.items():
            if item.checkState(0) == Qt.CheckState.Checked:
                checked.append(name)
        if checked:
            self._line_edit.setText(f"{len(checked)} vectors selected")
        else:
            self._line_edit.clear()

    def _emit_selection(self) -> None:
        checked = self.checked_names()
        if checked:
            self.vectors_selected.emit(' '.join(checked))

    # -- query ----------------------------------------------------------------

    def checked_names(self) -> List[str]:
        return [n for n, it in self._all_items.items()
                if it.checkState(0) == Qt.CheckState.Checked]

    def set_check_state(self, name: str, checked: bool) -> None:
        item = self._all_items.get(name)
        if item:
            item.setCheckState(
                0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self._update_summary()
