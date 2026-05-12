#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Chat Panel — resizable bottom panel for Python/AI REPL in pqwave.

Toggled via Ctrl+` from the main window. Sits in a QSplitter so the
user can drag the boundary to resize.

Autocomplete: QCompleter with substring matching.  Tab / Enter on a
suggestion accepts it.  Up / Down arrows navigate input history.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QCompleter,
)
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel, QEvent
from PyQt6.QtGui import QFont, QKeyEvent


class ChatPanel(QWidget):
    """Resizable bottom panel for REPL interaction."""

    command_submitted = pyqtSignal(str)
    visibility_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode: str = "python"
        self._history: list[str] = []
        self._history_idx: int = -1
        self._font_family: str = "monospace"
        self._font_size: int = 11
        self._fg_color: str = ""  # empty = default
        self._bg_color: str = ""  # empty = default
        self.splitter = None

        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        self.mode_label = QPushButton("python >")
        self.mode_label.setFlat(True)
        self.mode_label.setMinimumWidth(80)
        self.mode_label.setStyleSheet(
            "QPushButton { color: #4ec9b0; font-weight: bold; "
            "text-align: left; padding: 2px 4px; }"
        )
        self.mode_label.clicked.connect(self._toggle_mode)
        toolbar.addWidget(self.mode_label)
        toolbar.addStretch()

        self.config_btn = QPushButton("⚙")
        self.config_btn.setFlat(True)
        self.config_btn.setFixedSize(24, 24)
        self.config_btn.setToolTip("Configure AI backend...")
        self.config_btn.clicked.connect(self._open_setup)
        toolbar.addWidget(self.config_btn)

        layout.addLayout(toolbar)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 2px;
            }
        """)
        self.output.setMaximumBlockCount(2000)
        layout.addWidget(self.output, 1)

        self.input = QLineEdit()
        self.input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3c3c3c;
                border-radius: 2px;
                padding: 4px;
            }
        """)
        self.input.setPlaceholderText(
            "Type a command, /ai for AI mode, /python for Python mode..."
        )
        self.input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.input)

        # QCompleter with substring matching
        self._model = QStringListModel()
        self._completer = QCompleter(self._model, self.input)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setMaxVisibleItems(12)
        self._completer.popup().setStyleSheet("""
            QAbstractItemView {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                selection-background-color: #094771;
            }
        """)
        self.input.setCompleter(self._completer)
        self.input.installEventFilter(self)

        self.setLayout(layout)
        self._apply_fonts()

    # ---- Font & Appearance ----

    def set_font_size(self, size: int):
        self._font_size = max(8, min(24, size))
        self._apply_fonts()

    def _apply_fonts(self):
        family = self._font_family or "monospace"
        font = QFont(family, self._font_size)
        if hasattr(self, "output") and self.output:
            self.output.setFont(font)
        if hasattr(self, "input") and self.input:
            self.input.setFont(font)

    def apply_settings(
        self, font_family: str, font_size: int, fg_color: str, bg_color: str
    ) -> None:
        """Apply REPL appearance settings."""
        self._font_family = font_family
        self._font_size = max(8, min(24, font_size))
        self._fg_color = fg_color
        self._bg_color = bg_color
        self._apply_fonts()
        self._apply_colors()

    def _apply_colors(self):
        """Apply foreground/background colors via stylesheet."""
        fg = self._fg_color or "#d4d4d4"
        bg = self._bg_color or "#1e1e1e"
        try:
            r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
            ibg = f"#{min(255, r + 12):02x}{min(255, g + 12):02x}{min(255, b + 12):02x}"
        except (ValueError, IndexError):
            ibg = "#2d2d2d"
        if hasattr(self, "output") and self.output:
            self.output.setStyleSheet(
                f"QPlainTextEdit {{ background-color: {bg}; color: {fg}; "
                f"border: 1px solid #3c3c3c; border-radius: 2px; padding: 4px; }}"
            )
        if hasattr(self, "input") and self.input:
            self.input.setStyleSheet(
                f"QLineEdit {{ background-color: {ibg}; color: {fg}; "
                f"border: 1px solid #3c3c3c; border-radius: 2px; padding: 4px; }}"
            )
        self._completer.popup().setStyleSheet(
            f"QAbstractItemView {{ background-color: {bg}; color: {fg}; "
            f"border: 1px solid #3c3c3c; "
            f"selection-background-color: #094771; }}"
        )

    # ---- Mode ----

    @property
    def mode(self) -> str:
        return self._mode

    def set_ai_mode(self, model_name: str = None):
        self._mode = "ai"
        if model_name:
            self._last_model_name = model_name
        model = model_name or getattr(self, "_last_model_name", None) or "llm"
        self.mode_label.setText(f"ai [{model}] >")
        self.mode_label.setStyleSheet(
            "QPushButton { color: #ce9178; font-weight: bold; "
            "text-align: left; padding: 2px 4px; }"
        )
        self.append_output(
            f"-- AI mode: type naturally. /python to switch back.  Model: {model}\n"
        )

    def set_python_mode(self):
        self._mode = "python"
        self.mode_label.setText("python >")
        self.mode_label.setStyleSheet(
            "QPushButton { color: #4ec9b0; font-weight: bold; "
            "text-align: left; padding: 2px 4px; }"
        )

    def _toggle_mode(self):
        if self._mode == "python":
            self.set_ai_mode()
        else:
            self.set_python_mode()

    def _open_setup(self):
        from pqwave.llm.setup import show_setup_dialog

        show_setup_dialog(self)

    # ---- Autocomplete ----

    def set_completions(self, items: list[str]):
        """Set the completion items (commands, signals, functions, etc.)."""
        self._model.setStringList(items)

    # ---- Input handling ----

    def _on_submit(self):
        text = self.input.text().strip()
        if not text:
            return

        self._history.append(text)
        self._history_idx = len(self._history)
        self.input.clear()

        self.append_output(f"{self.mode_label.text()} {text}\n")
        self.command_submitted.emit(text)

    # ---- Output ----

    def append_output(self, text: str):
        self.output.appendPlainText(text.rstrip("\n"))
        scrollbar = self.output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def append_result(self, result):
        if result is None:
            return
        self.append_output(str(result))

    # ---- Input key handling (event filter) ----

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            popup = self._completer.popup()
            popup_visible = popup.isVisible()

            # Tab: always intercepted to prevent Qt focus change.
            # If completer has matches, show popup; otherwise swallow.
            if key == Qt.Key.Key_Tab:
                prefix = self.input.text()[:self.input.cursorPosition()]
                self._completer.setCompletionPrefix(prefix)
                if self._completer.completionCount() > 0:
                    self._completer.complete()
                return True

            # When completer popup is visible, let Qt handle Up/Down/Enter
            # (QCompleter navigates items), but still intercept Esc/others.
            if popup_visible:
                if key in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                           Qt.Key.Key_Return, Qt.Key.Key_Enter,
                           Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                           Qt.Key.Key_Home, Qt.Key.Key_End):
                    return super().eventFilter(obj, event)
                return True  # swallow everything else while popup is open

            # Up/Down: history navigation (popup not visible)
            if key == Qt.Key.Key_Up:
                if self._history and self._history_idx > 0:
                    self._history_idx -= 1
                    self.input.setText(self._history[self._history_idx])
                return True
            if key == Qt.Key.Key_Down:
                if self._history_idx < len(self._history) - 1:
                    self._history_idx += 1
                    self.input.setText(self._history[self._history_idx])
                else:
                    self._history_idx = len(self._history)
                    self.input.clear()
                return True

            # Escape: hide completer popup if visible, otherwise pass through
            if key == Qt.Key.Key_Escape:
                if popup_visible:
                    popup.setVisible(False)
                return True

        return super().eventFilter(obj, event)

    # ---- Visibility ----

    def toggle(self):
        self.setVisible(not self.isVisible())
        self.visibility_changed.emit(self.isVisible())
