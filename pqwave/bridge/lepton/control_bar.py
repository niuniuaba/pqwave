# pqwave/bridge/lepton/control_bar.py
"""Status bar widget for Lepton-EDA bridge controls."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal


class LeptonControlBar(QWidget):
    """Status and control bar for lepton-eda bridge.

    Same pattern as MCControlBar and KiCadControlBar: lazy creation,
    hidden by default, horizontal layout, 40px max height.

    Signals:
        simulate_clicked():           user wants to run simulation
        annotate_dc_clicked():        user wants to stamp DC voltages
        clear_annotations_clicked():  user wants to clear labels
        unwatch_clicked():            user wants to stop watching
    """

    simulate_clicked = pyqtSignal()
    rewatch_clicked = pyqtSignal()
    annotate_dc_clicked = pyqtSignal()
    clear_annotations_clicked = pyqtSignal()
    unwatch_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self._status_label = QLabel("Lepton: not watching")
        layout.addWidget(self._status_label)
        layout.addSpacing(10)

        self._simulate_btn = QPushButton("Simulate Now")
        self._simulate_btn.setMinimumWidth(110)
        self._simulate_btn.clicked.connect(self.simulate_clicked.emit)
        layout.addWidget(self._simulate_btn)

        self._annotate_btn = QPushButton("Annotate DC")
        self._annotate_btn.setMinimumWidth(100)
        self._annotate_btn.clicked.connect(self.annotate_dc_clicked.emit)
        self._annotate_btn.setEnabled(False)
        layout.addWidget(self._annotate_btn)

        self._clear_annotations_btn = QPushButton("Clear Annotations")
        self._clear_annotations_btn.setMinimumWidth(130)
        self._clear_annotations_btn.clicked.connect(self.clear_annotations_clicked.emit)
        layout.addWidget(self._clear_annotations_btn)

        self._rewatch_btn = QPushButton("Re-Watch")
        self._rewatch_btn.setMinimumWidth(90)
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
        self._status_label.setText(f"Lepton: {text}")

    def set_simulating(self, active: bool):
        self._simulate_btn.setEnabled(not active)
        self._rewatch_btn.setEnabled(not active)
        if active:
            self.set_status("simulating...")

    def set_simulation_complete(self):
        self._annotate_btn.setEnabled(True)
        self.set_status("simulation complete")
