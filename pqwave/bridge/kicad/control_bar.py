"""Status bar widget for KiCad bridge controls."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal


class KiCadControlBar(QWidget):
    """Status and control bar for KiCad bridge.

    Follows the same pattern as MCControlBar (pqwave/ui/mc_control_bar.py):
    lazy creation, hidden by default, horizontal layout, 40px max height,
    dynamically inserted into upper_layout.

    Signals:
        rewatch_clicked(): user wants to resume watching the last file
        unwatch_clicked(): user wants to stop watching
    """

    rewatch_clicked = pyqtSignal()
    unwatch_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self._status_label = QLabel("KiCad: not watching")
        layout.addWidget(self._status_label)

        layout.addSpacing(15)

        self._rewatch_btn = QPushButton("Re-Watch")
        self._rewatch_btn.setMinimumWidth(110)
        self._rewatch_btn.clicked.connect(self.rewatch_clicked.emit)
        layout.addWidget(self._rewatch_btn)

        self._unwatch_btn = QPushButton("Stop Watching")
        self._unwatch_btn.setMinimumWidth(110)
        self._unwatch_btn.clicked.connect(self.unwatch_clicked.emit)
        layout.addWidget(self._unwatch_btn)

        layout.addStretch()

        self.setMaximumHeight(40)
        self.setLayout(layout)

    def set_status(self, text: str):
        self._status_label.setText(f"KiCad: {text}")

    def set_simulating(self, active: bool):
        self._rewatch_btn.setEnabled(not active)
        if active:
            self.set_status("simulating...")
