"""Monte Carlo control bar for display mode, run filter, and sigma control."""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox,
    QLineEdit, QSpinBox,
)
from PyQt6.QtCore import pyqtSignal


class MCControlBar(QWidget):
    """Horizontal control bar for MC display configuration.

    Signals:
        display_mode_changed(str): spaghetti, envelope, or single
        envelope_sigma_changed(float): new sigma value for envelope bands
        nominal_changed(int): new nominal run index
        run_filter_changed(object): "all" (str) or list[int] of run indices
    """

    display_mode_changed = pyqtSignal(str)
    envelope_sigma_changed = pyqtSignal(float)
    nominal_changed = pyqtSignal(int)
    run_filter_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        # Run count label
        self.run_count_label = QLabel("MC: 0 runs")
        self.run_count_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.run_count_label)

        layout.addSpacing(15)

        # Display mode
        layout.addWidget(QLabel("Display:"))
        self.display_combo = QComboBox()
        self.display_combo.addItems(["spaghetti", "envelope", "single"])
        self.display_combo.currentTextChanged.connect(self.display_mode_changed.emit)
        layout.addWidget(self.display_combo)

        # Sigma for envelope
        layout.addWidget(QLabel("σ:"))
        self.sigma_spin = QDoubleSpinBox()
        self.sigma_spin.setRange(0.5, 6.0)
        self.sigma_spin.setValue(3.0)
        self.sigma_spin.setSingleStep(0.5)
        self.sigma_spin.valueChanged.connect(self.envelope_sigma_changed.emit)
        layout.addWidget(self.sigma_spin)

        # Nominal run
        layout.addWidget(QLabel("Nominal:"))
        self.nominal_spin = QSpinBox()
        self.nominal_spin.setMinimum(0)
        self.nominal_spin.valueChanged.connect(self.nominal_changed.emit)
        layout.addWidget(self.nominal_spin)

        # Run filter
        layout.addWidget(QLabel("Runs:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("all")
        self.filter_edit.setMaximumWidth(120)
        self.filter_edit.editingFinished.connect(self._parse_filter)
        layout.addWidget(self.filter_edit)

        self.setMaximumHeight(40)
        self.setLayout(layout)

    def set_run_count(self, n: int):
        """Update the run count display and nominal spinner range."""
        self.run_count_label.setText(f"MC: {n} runs")
        self.nominal_spin.setMaximum(max(0, n - 1))

    def set_nominal(self, idx: int):
        """Set the nominal run index without emitting signal."""
        self.nominal_spin.blockSignals(True)
        self.nominal_spin.setValue(idx)
        self.nominal_spin.blockSignals(False)

    def set_display_mode(self, mode: str):
        """Set the display mode combo without emitting signal."""
        idx = self.display_combo.findText(mode)
        if idx >= 0:
            self.display_combo.blockSignals(True)
            self.display_combo.setCurrentIndex(idx)
            self.display_combo.blockSignals(False)

    def set_filter(self, value):
        """Set the filter text without emitting signal."""
        if value is None or value == "all":
            self.filter_edit.setText("")
        elif isinstance(value, list):
            self.filter_edit.setText(", ".join(str(i) for i in value))

    def _parse_filter(self):
        """Parse the filter text and emit run_filter_changed."""
        text = self.filter_edit.text().strip()
        if not text or text.lower() == "all":
            self.run_filter_changed.emit("all")
            return
        try:
            indices = [int(x.strip()) for x in text.split(",") if x.strip()]
            self.run_filter_changed.emit(indices)
        except ValueError:
            self.run_filter_changed.emit("all")
