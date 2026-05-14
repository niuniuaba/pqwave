"""
ReplHelpDialog — Filterable help reference for the pqwave REPL chat panel.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class ReplHelpDialog(QDialog):
    """Modal dialog showing REPL commands and usage in a filterable tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help — REPL")
        self.resize(550, 600)

        layout = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter...")
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

    def _add_leaf(self, parent: QTreeWidgetItem, text: str, name: str = "",
                  desc: str = "") -> None:
        item = QTreeWidgetItem(parent, [text])
        self._all_items.append((item, name, desc))
        parent.addChild(item)

    def _populate(self):
        root = QTreeWidgetItem(self._tree, ["REPL Commands"])

        modes = QTreeWidgetItem(root, ["Modes"])
        self._add_leaf(modes, "python>  Python mode — type API commands directly",
                       "python mode", "Python REPL")
        self._add_leaf(modes, "ai>  AI mode — natural language translated to commands",
                       "ai mode", "AI mode")
        self._add_leaf(modes, "/ai — Switch to AI mode", "/ai", "")
        self._add_leaf(modes, "/python — Switch to Python mode", "/python", "")

        cmds = QTreeWidgetItem(root, ["Slash Commands"])
        slash_commands = [
            ("/clear", "Clear output"),
            ("/help", "List all commands"),
            ("/backend", "Show backend status"),
            ("/backend template on|off", "Enable/disable template engine"),
            ("/backend llm on|off", "Enable/disable LLM fallback"),
            ("/test-backend", "Test LLM connection"),
            ("/remember", "Save LLM translations as templates"),
            ("/font 8-24", "Change font size"),
            ("/open <path>", "Open a file"),
        ]
        for cmd, help_text in slash_commands:
            self._add_leaf(cmds, f"{cmd}  —  {help_text}", cmd, help_text)

        ac = QTreeWidgetItem(root, ["Autocomplete"])
        self._add_leaf(ac, "Tab — Complete current word", "tab", "")
        self._add_leaf(ac, "Auto-suggest after 2+ chars (300ms debounce)",
                       "autosuggest", "")
        self._add_leaf(ac, "Up/Down/Enter — Navigate popup", "popup nav", "")

        tips = QTreeWidgetItem(root, ["AI Mode Tips"])
        self._add_leaf(tips, "Template engine catches common patterns (instant, free)",
                       "template engine", "")
        self._add_leaf(tips, "LLM fallback for edge cases", "llm fallback", "")
        self._add_leaf(tips, "/remember to save successful LLM translations",
                       "/remember ai", "")

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
