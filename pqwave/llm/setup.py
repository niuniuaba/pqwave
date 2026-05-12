#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLM Setup Wizard — profile-based configuration for AI translator backend.

Manages named profiles: each has a backend type (local URL or external API)
and connection details. The active profile is whichever one is checked in
the profile list — no separate selector needed.

Accessible from ChatPanel gear button or pqwave --setup-llm.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QSplitter,
    QWidget, QLabel, QLineEdit, QPushButton, QFormLayout,
    QMessageBox, QListWidget, QListWidgetItem, QInputDialog,
)
from PyQt6.QtCore import Qt


class LLMSetupDialog(QDialog):
    """Profile manager dialog for AI backend configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage AI Backend Profiles")
        self.setMinimumWidth(620)
        self.setMinimumHeight(380)

        from pqwave.llm.backends import get_profiles, get_active_profile_name

        self._profiles = {name: (backend, model)
                          for name, backend, model in get_profiles()}
        self._active = get_active_profile_name()
        self._updating_check = False  # guard against recursive check signals

        layout = QVBoxLayout()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- Left: profile list with checkboxes ----
        left = QWidget()
        left.setMinimumWidth(180)
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("<b>Profiles</b> (check = active)"))
        self.profile_list = QListWidget()
        self.profile_list.itemChanged.connect(self._on_item_checked)
        self.profile_list.itemClicked.connect(self._on_item_clicked)
        left_layout.addWidget(self.profile_list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setToolTip("Add new profile")
        add_btn.clicked.connect(self._add_profile)
        btn_row.addWidget(add_btn)

        self.del_btn = QPushButton("−")
        self.del_btn.setToolTip("Delete selected profile")
        self.del_btn.clicked.connect(self._delete_profile)
        btn_row.addWidget(self.del_btn)
        left_layout.addLayout(btn_row)
        left.setLayout(left_layout)

        splitter.addWidget(left)

        # ---- Right: backend config ----
        right = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_local_url_tab(), "Local LLM")
        self.tabs.addTab(self._create_external_api_tab(), "External API")
        right_layout.addWidget(self.tabs)
        right.setLayout(right_layout)

        splitter.addWidget(right)
        splitter.setSizes([180, 440])
        layout.addWidget(splitter)

        # ---- Bottom buttons ----
        bottom = QHBoxLayout()
        bottom.addStretch()
        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        save_btn = QPushButton("Save Profile")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_current)
        bottom.addWidget(save_btn)
        layout.addLayout(bottom)

        self.setLayout(layout)

        # Populate the list
        self._populate_list()

    # ---- Profile list management ----

    def _populate_list(self):
        from pqwave.llm.backends import get_profile

        self._updating_check = True
        self.profile_list.clear()
        for name in sorted(self._profiles):
            profile = get_profile(name) or {}
            backend = profile.get("backend", "")
            model = profile.get("model", "")
            label = f"{name}  [{backend}, {model}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if name == self._active
                else Qt.CheckState.Unchecked
            )
            self.profile_list.addItem(item)
        self._updating_check = False
        self.del_btn.setEnabled(len(self._profiles) > 1)

        # Load the active profile into the form
        self._load_profile_into_form(self._active)

    def _load_profile_into_form(self, name: str):
        from pqwave.llm.backends import get_profile

        profile = get_profile(name) or {}
        backend = profile.get("backend", "local_url")

        self.tabs.blockSignals(True)
        if backend == "local_url":
            self.tabs.setCurrentIndex(0)
            self.local_url.setText(profile.get("endpoint", ""))
            self.local_model.setText(profile.get("model", ""))
        else:
            self.tabs.setCurrentIndex(1)
            self.ext_url.setText(profile.get("endpoint", ""))
            self.ext_key.setText(profile.get("api_key", ""))
            self.ext_model.setText(profile.get("model", ""))
        self.tabs.blockSignals(False)

    def _on_item_checked(self, item: QListWidgetItem):
        """Called when any item's check state changes."""
        if self._updating_check:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._updating_check = True
            # Uncheck all other items
            for i in range(self.profile_list.count()):
                other = self.profile_list.item(i)
                if other.data(Qt.ItemDataRole.UserRole) != name:
                    other.setCheckState(Qt.CheckState.Unchecked)
            self._updating_check = False
            self._active = name
            from pqwave.llm.backends import set_active_profile
            set_active_profile(name)
            self._load_profile_into_form(name)

    def _on_item_clicked(self, item: QListWidgetItem):
        """Load profile into form when clicked (even if already checked)."""
        name = item.data(Qt.ItemDataRole.UserRole)
        self._load_profile_into_form(name)

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self._profiles:
            QMessageBox.warning(self, "Error", f"Profile '{name}' already exists.")
            return

        from pqwave.llm.backends import save_profile

        profile = {
            "backend": "local_url",
            "endpoint": "http://localhost:11434/v1",
            "model": "qwen2.5:0.5b",
        }
        save_profile(name, profile)
        self._profiles[name] = ("local_url", "qwen2.5:0.5b")
        self._active = name
        self._populate_list()

    def _delete_profile(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        from pqwave.llm.backends import delete_profile, get_profiles, get_active_profile_name

        ok = delete_profile(name)
        if not ok:
            QMessageBox.warning(self, "Error", "Cannot delete the last profile.")
            return
        del self._profiles[name]
        self._profiles = {n: (b, m) for n, b, m in get_profiles()}
        self._active = get_active_profile_name()
        self._populate_list()

    # ---- Tab 1: Local URL ----

    def _create_local_url_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()

        info = QLabel(
            "Connect to a locally running LLM server with an\n"
            "OpenAI-compatible /v1/chat/completions endpoint."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.local_url = QLineEdit("http://localhost:11434/v1")
        self.local_url.setPlaceholderText("http://localhost:11434/v1")
        form.addRow("Endpoint URL:", self.local_url)

        self.local_model = QLineEdit("qwen2.5:0.5b")
        form.addRow("Model name:", self.local_model)
        layout.addLayout(form)

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_local_url)
        layout.addWidget(test_btn)

        hints = QLabel(
            "<b>Quick setup:</b><br>"
            "<b>Ollama:</b> <code>ollama pull qwen2.5:0.5b</code> "
            "→ <code>http://localhost:11434/v1</code><br>"
            "<b>LM Studio:</b> load any model → "
            "<code>http://localhost:1234/v1</code><br>"
            "<b>llama.cpp server:</b> <code>llama-server -m model.gguf</code>"
            " → <code>http://localhost:8080/v1</code>"
        )
        hints.setWordWrap(True)
        hints.setStyleSheet("QLabel { color: #888; font-size: 11px; }")
        layout.addWidget(hints)

        layout.addStretch()
        w.setLayout(layout)
        return w

    def _test_local_url(self):
        from pqwave.llm.backends import LocalURLBackend
        try:
            backend = LocalURLBackend(
                self.local_url.text().strip(),
                self.local_model.text().strip(),
            )
            resp, _ = backend.chat(
                "You are a test. Reply with just: OK",
                "Say hello",
            )
            QMessageBox.information(
                self, "Success",
                f"Connected successfully!\nResponse: {resp[:200]}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", str(e))

    # ---- Tab 2: External API ----

    def _create_external_api_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()

        info = QLabel(
            "Connect to an external API service.\n"
            "Works with OpenAI, Anthropic, or any\n"
            "OpenAI-compatible API."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.ext_url = QLineEdit("https://api.openai.com/v1")
        form.addRow("Endpoint URL:", self.ext_url)

        self.ext_key = QLineEdit()
        self.ext_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ext_key.setPlaceholderText("sk-...")
        form.addRow("API Key:", self.ext_key)

        self.ext_model = QLineEdit("gpt-4o-mini")
        form.addRow("Model name:", self.ext_model)
        layout.addLayout(form)

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_external)
        layout.addWidget(test_btn)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _test_external(self):
        from pqwave.llm.backends import ExternalAPIBackend
        try:
            backend = ExternalAPIBackend(
                self.ext_url.text().strip(),
                self.ext_key.text().strip(),
                self.ext_model.text().strip(),
            )
            resp, _ = backend.chat(
                "You are a test. Reply with just: OK",
                "Say hello",
            )
            QMessageBox.information(
                self, "Success",
                f"Connected successfully!\nResponse: {resp[:200]}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", str(e))

    # ---- Save ----

    def _save_current(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)

        from pqwave.llm.backends import save_profile

        current_tab = self.tabs.currentIndex()
        if current_tab == 0:
            profile = {
                "backend": "local_url",
                "endpoint": self.local_url.text().strip(),
                "model": self.local_model.text().strip(),
            }
            self._profiles[name] = ("local_url", self.local_model.text().strip())
        else:
            profile = {
                "backend": "external_api",
                "endpoint": self.ext_url.text().strip(),
                "api_key": self.ext_key.text().strip(),
                "model": self.ext_model.text().strip(),
            }
            self._profiles[name] = ("external_api", self.ext_model.text().strip())

        try:
            save_profile(name, profile)
            self._populate_list()
            QMessageBox.information(self, "Saved", f"Profile '{name}' saved.")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {e}")


def show_setup_dialog(parent=None) -> bool:
    dialog = LLMSetupDialog(parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
