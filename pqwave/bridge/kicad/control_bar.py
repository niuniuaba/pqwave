"""KiCad Bridge status bar widget."""

import os

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal


class KiCadControlBar(QWidget):
    """Status bar showing KiCad Bridge integration state.

    Layout: [status label] [Simulate Now] [Connect/Disconnect] [Annotate DC] [Clear Annotations]

    Signal callbacks are wired by the caller (main_window).
    """

    simulate_clicked = pyqtSignal()
    connect_clicked = pyqtSignal()
    disconnect_clicked = pyqtSignal()
    annotate_dc_clicked = pyqtSignal()
    clear_annotations_clicked = pyqtSignal()

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._simulate_btn = QPushButton("Simulate Now")
        self._simulate_btn.setToolTip("Export netlist, run ngspice, load results")
        self._simulate_btn.clicked.connect(self.simulate_clicked)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setToolTip("Disconnect from the schematic file")
        self._disconnect_btn.clicked.connect(self.disconnect_clicked)

        self._annotate_btn = QPushButton("Annotate DC")
        self._annotate_btn.setToolTip("Stamp DC operating-point values onto schematic")
        self._annotate_btn.clicked.connect(self.annotate_dc_clicked)

        self._clear_btn = QPushButton("Clear Annotations")
        self._clear_btn.setToolTip("Remove all annotation text from schematic")
        self._clear_btn.clicked.connect(self.clear_annotations_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.addWidget(self._status_label)
        layout.addStretch()
        layout.addWidget(self._simulate_btn)
        layout.addWidget(self._annotate_btn)
        layout.addWidget(self._clear_btn)
        layout.addWidget(self._disconnect_btn)

        self.refresh()

    def refresh(self):
        """Update button visibility and status text from bridge state."""
        status = self._bridge.get_status()
        if status["connected"]:
            path = status["path"]
            basename = os.path.basename(path) if path else ""
            ipc = "IPC ✓" if status["has_ipc"] else "IPC ✗"
            self._status_label.setText(
                f"KiCad: {basename}  |  {ipc}"
            )
            self._status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self._simulate_btn.setVisible(True)
            self._annotate_btn.setVisible(True)
            self._clear_btn.setVisible(True)
            self._disconnect_btn.setVisible(True)
        else:
            self._status_label.setText("KiCad: Not connected")
            self._status_label.setStyleSheet("color: #888;")
            self._simulate_btn.setVisible(False)
            self._annotate_btn.setVisible(False)
            self._clear_btn.setVisible(False)
            self._disconnect_btn.setVisible(False)
