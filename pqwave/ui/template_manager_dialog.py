import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QMessageBox, QLabel,
)
from pqwave.templates.manager import TemplateManager
from pqwave.session.api import get_template_dir


class TemplateManagerDialog(QDialog):
    """Dialog for managing saved view templates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Template Manager")
        self.setMinimumSize(400, 300)
        self._mgr = TemplateManager(get_template_dir())
        self.selected_name = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Saved Templates:"))
        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        self._load_btn = QPushButton("Load")
        self._load_btn.setEnabled(False)
        self._load_btn.clicked.connect(self._on_load)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._load_btn)
        btn_layout.addWidget(self._delete_btn)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

        self._refresh()

    def _refresh(self):
        self._list.clear()
        for name in self._mgr.list():
            self._list.addItem(name)

    def _on_selection(self):
        has = bool(self._list.currentItem())
        self._load_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)

    def _on_load(self):
        if self._list.currentItem():
            self.selected_name = self._list.currentItem().text()
            self.accept()

    def _on_delete(self):
        if self._list.currentItem():
            name = self._list.currentItem().text()
            reply = QMessageBox.question(
                self, "Confirm", f"Delete template '{name}'?"
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._mgr.delete(name)
                self._refresh()
