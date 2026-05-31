"""Status bar widget for xschem bridge controls."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal


class XschemControlBar(QWidget):
    """Status and control bar for xschem bridge.

    Same pattern as MCControlBar, KiCadControlBar, and LeptonControlBar:
    lazy creation, hidden by default, horizontal layout, 40px max height.

    Signals:
        simulate_clicked():  user wants to run simulation
        unwatch_clicked():   user wants to stop watching
    """

    simulate_clicked = pyqtSignal()
    unwatch_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self._status_label = QLabel("Xschem: not watching")
        layout.addWidget(self._status_label)
        layout.addSpacing(10)

        self._simulate_btn = QPushButton("Simulate Now")
        self._simulate_btn.setMinimumWidth(110)
        self._simulate_btn.clicked.connect(self.simulate_clicked.emit)
        layout.addWidget(self._simulate_btn)

        self._unwatch_btn = QPushButton("Stop Watching")
        self._unwatch_btn.setMinimumWidth(110)
        self._unwatch_btn.clicked.connect(self.unwatch_clicked.emit)
        layout.addWidget(self._unwatch_btn)

        layout.addStretch()
        self.setMaximumHeight(40)
        self.setLayout(layout)

    def set_status(self, text: str):
        self._status_label.setText(f"Xschem: {text}")

    def set_simulating(self, active: bool):
        self._simulate_btn.setEnabled(not active)
        if active:
            self.set_status("simulating...")

    def set_simulation_complete(self):
        self.set_status("simulation complete")
