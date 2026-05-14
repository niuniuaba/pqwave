"""
ApiHelpDialog — Filterable, categorized reference of all Session API commands.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from pqwave.session.api import get_command_registry


class ApiHelpDialog(QDialog):
    """Modal dialog showing all API commands in a filterable, categorized tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help — API")
        self.resize(600, 650)

        layout = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter commands...")
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

    def _add_leaf(self, parent: QTreeWidgetItem, sig: str, help_text: str,
                  name: str = "") -> None:
        text = f"{sig}  —  {help_text}"
        item = QTreeWidgetItem(parent, [text])
        self._all_items.append((item, name or sig, help_text))
        parent.addChild(item)

    def _categorize(self, name: str) -> str:
        if "cursor" in name:
            return "Cursor"
        if name in ("add", "add_all", "show", "show_all", "remove",
                     "remove_all", "hide", "hide_all", "signals",
                     "show_matching", "bus", "expand", "collapse", "digital"):
            return "Trace & Bus"
        if name in ("measure", "measure_script", "fft", "fft_config",
                     "power", "eye"):
            return "Analyze"
        if name in ("load", "reload", "export_csv", "export_plot", "change_x"):
            return "File & Data"
        if name in ("grid", "legend", "cross_hair", "zoom_fit", "zoom_in",
                     "zoom_out", "auto_range_x", "auto_range_y", "title",
                     "theme", "range", "log_x", "log_y"):
            return "View"
        if name in ("split_horizontal", "split_vertical", "close_panel"):
            return "Panel"
        return "Other"

    def _populate(self):
        registry = get_command_registry()
        cat_order = ["Trace & Bus", "Analyze", "Cursor",
                      "View", "File & Data", "Panel", "Other"]
        categories: dict[str, QTreeWidgetItem] = {}

        root = QTreeWidgetItem(self._tree, ["API Commands"])
        for cat in cat_order:
            categories[cat] = QTreeWidgetItem(root, [cat])

        for name, entry in sorted(registry.items()):
            cat = self._categorize(name)
            cat_item = categories.get(cat, categories["Other"])
            self._add_leaf(cat_item, entry["signature"], entry["help"], name)

        for cat in cat_order:
            if categories[cat].childCount() == 0:
                root.removeChild(categories[cat])

        self._tree.expandAll()

    def _apply_filter(self, text: str):
        needle = text.lower()
        for item, name, desc in self._all_items:
            visible = (not needle or needle in name.lower()
                       or needle in desc.lower())
            item.setHidden(not visible)
            if visible:
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()
