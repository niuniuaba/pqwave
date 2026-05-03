#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KeyBindingsDialog - Help dialog showing all application keybindings.

Displays a table of current keybindings with a note on how to customise them
by editing ~/.pqwave/keybindings.json.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt


class KeyBindingsDialog(QDialog):
    """Dialog listing all application keybindings."""

    def __init__(self, bindings: list[dict], config_path: str, parent=None):
        """
        Args:
            bindings: list of dicts with keys ``action``, ``key``,
                      ``description``, ``is_default`` — from
                      ``KeyBindingManager.get_all_bindings()``.
            config_path: path to the user config file shown in the hint.
        """
        super().__init__(parent)
        self.setWindowTitle("Keybindings")
        self.setMinimumSize(550, 500)
        self.resize(600, 600)

        self._bindings = bindings
        self._config_path = config_path

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Title
        title = QLabel("<b>Application Keybindings</b>")
        title.setStyleSheet("font-size: 14px;")
        layout.addWidget(title)

        # Table
        self._table = QTableWidget(len(bindings), 2)
        self._table.setHorizontalHeaderLabels(["Key", "Action"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        for row, b in enumerate(bindings):
            key_item = QTableWidgetItem(b['key'])
            desc_item = QTableWidgetItem(b['description'])
            if not b['is_default']:
                # Custom entries are visually highlighted
                key_item.setFont(self._table.font())
                key_item.setForeground(Qt.GlobalColor.darkBlue)
                desc_item.setForeground(Qt.GlobalColor.darkBlue)
            self._table.setItem(row, 0, key_item)
            self._table.setItem(row, 1, desc_item)

        layout.addWidget(self._table)

        # Customisation hint
        hint = QLabel(
            f"To customise, edit the file:<br>"
            f"  <code>{self._config_path}</code><br><br>"
            "Format: &#123; \"action_name\": \"key_sequence\", … &#125;<br>"
            "Restart pqwave after saving changes for them to take effect."
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)
