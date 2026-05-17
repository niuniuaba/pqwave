"""Dialog for configuring MC yield analysis."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDoubleSpinBox, QDialogButtonBox,
)


class MCYieldDialog(QDialog):
    """Configure and run MC yield analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MC Yield Analysis")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.signal_edit = QLineEdit("v(out)")
        form.addRow("Signal:", self.signal_edit)

        self.low_spin = QDoubleSpinBox()
        self.low_spin.setRange(-1e12, 1e12)
        self.low_spin.setDecimals(6)
        self.low_spin.setValue(-3.0)
        form.addRow("Low limit:", self.low_spin)

        self.high_spin = QDoubleSpinBox()
        self.high_spin.setRange(-1e12, 1e12)
        self.high_spin.setDecimals(6)
        self.high_spin.setValue(3.0)
        form.addRow("High limit:", self.high_spin)

        self.measure_combo = QComboBox()
        self.measure_combo.addItem("(per-point)", None)
        self.measure_combo.addItem("max", "max")
        self.measure_combo.addItem("min", "min")
        self.measure_combo.addItem("rms", "rms")
        form.addRow("Condition:", self.measure_combo)

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
            "low": self.low_spin.value(),
            "high": self.high_spin.value(),
            "measure": self.measure_combo.currentData(),
        }
