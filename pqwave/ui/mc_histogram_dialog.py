"""Dialog for configuring MC histogram analysis."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QDialogButtonBox, QLabel, QHBoxLayout,
)


class MCHistogramDialog(QDialog):
    """Configure and run MC histogram analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MC Histogram")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.signal_edit = QLineEdit("v(out)")
        form.addRow("Signal:", self.signal_edit)

        self.measure_combo = QComboBox()
        self.measure_combo.addItems(["max", "min", "mean", "rms", "pk_pk"])
        form.addRow("Measure:", self.measure_combo)

        self.bins_spin = QSpinBox()
        self.bins_spin.setRange(5, 500)
        self.bins_spin.setValue(50)
        form.addRow("Bins:", self.bins_spin)

        range_layout = QHBoxLayout()
        self.range_low = QDoubleSpinBox()
        self.range_low.setRange(-1e12, 1e12)
        self.range_low.setDecimals(6)
        self.range_high = QDoubleSpinBox()
        self.range_high.setRange(-1e12, 1e12)
        self.range_high.setDecimals(6)
        range_layout.addWidget(self.range_low)
        range_layout.addWidget(QLabel("to"))
        range_layout.addWidget(self.range_high)
        form.addRow("Range:", range_layout)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_config(self) -> dict:
        return {
            "signal": self.signal_edit.text(),
            "measure": self.measure_combo.currentText(),
            "bins": self.bins_spin.value(),
            "range": (self.range_low.value(), self.range_high.value()),
        }
