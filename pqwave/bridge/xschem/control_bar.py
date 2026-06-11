# pqwave/bridge/xschem/control_bar.py
"""Status bar widget for Xschem bridge controls.

Uniform layout shared with Lepton control bars:
[Connect] [Simulate Now] [Disconnect] [Annotate DC] [Clear Annotations]
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal


class XschemControlBar(QWidget):
    """Status and control bar for xschem bridge.

    Signals:
        connect_clicked():           user wants to connect to xschem
        simulate_clicked():          user wants to run simulation
        disconnect_clicked():        user wants to disconnect
        annotate_dc_clicked():       user wants to stamp DC voltages
        clear_annotations_clicked(): user wants to clear labels/stamps
    """

    connect_clicked = pyqtSignal()
    simulate_clicked = pyqtSignal()
    disconnect_clicked = pyqtSignal()
    annotate_dc_clicked = pyqtSignal()
    clear_annotations_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self._status_label = QLabel("Xschem: disconnected")
        layout.addWidget(self._status_label)
        layout.addSpacing(10)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self.connect_clicked.emit)
        layout.addWidget(self._connect_btn)

        self._simulate_btn = QPushButton("Simulate Now")
        self._simulate_btn.setVisible(False)
        self._simulate_btn.clicked.connect(self.simulate_clicked.emit)
        layout.addWidget(self._simulate_btn)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setVisible(False)
        self._disconnect_btn.clicked.connect(self.disconnect_clicked.emit)
        layout.addWidget(self._disconnect_btn)

        self._annotate_btn = QPushButton("Annotate DC")
        self._annotate_btn.setVisible(False)
        self._annotate_btn.clicked.connect(self.annotate_dc_clicked.emit)
        layout.addWidget(self._annotate_btn)

        self._clear_annotations_btn = QPushButton("Clear Annotations")
        self._clear_annotations_btn.setVisible(False)
        self._clear_annotations_btn.clicked.connect(self.clear_annotations_clicked.emit)
        layout.addWidget(self._clear_annotations_btn)

        layout.addStretch()
        self.setMaximumHeight(40)
        self.setLayout(layout)

    def set_connected(self, connected: bool):
        """Toggle button visibility based on connected state."""
        self._connect_btn.setVisible(not connected)
        self._simulate_btn.setVisible(connected)
        self._disconnect_btn.setVisible(connected)
        self._annotate_btn.setVisible(connected)
        self._clear_annotations_btn.setVisible(connected)

    def set_status(self, text: str):
        """Update the status label."""
        self._status_label.setText(f"Xschem: {text}")

    def set_simulating(self, active: bool):
        """Disable Simulate Now during simulation."""
        self._simulate_btn.setEnabled(not active)
        if active:
            self.set_status("simulating...")
