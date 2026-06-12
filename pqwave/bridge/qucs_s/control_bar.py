"""Minimal status bar showing Qucs-S integration state."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt


class QucsSControlBar(QWidget):
    """Minimal status bar showing Qucs-S integration state."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.refresh()

    def refresh(self):
        if self._bridge.is_configured():
            self._label.setText(
                "Qucs-S: Configured ✓ — restart Qucs-S, then simulate to open results here"
            )
            self._label.setStyleSheet("color: #2e7d32;")
        else:
            self._label.setText(
                "Qucs-S: Not configured — use File > Qucs-S Bridge > Connect"
            )
            self._label.setStyleSheet("color: #888;")
