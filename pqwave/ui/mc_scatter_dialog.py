"""Dialog for configuring MC scatter analysis."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox,
)


class MCScatterDialog(QDialog):
    """Configure and run MC scatter analysis."""

    def __init__(self, parent=None, parameters: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("MC Scatter Plot")
        self._parameters = parameters or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.signal_edit = QLineEdit("v(out)")
        form.addRow("Signal:", self.signal_edit)

        self.measure_combo = QComboBox()
        self.measure_combo.addItems(["max", "min", "mean", "rms", "pk_pk"])
        form.addRow("Measure:", self.measure_combo)

        self.param_combo = QComboBox()
        if self._parameters:
            self.param_combo.addItems(list(self._parameters.keys()))
        self.param_combo.setEditable(True)
        form.addRow("Parameter:", self.param_combo)

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
            "param": self.param_combo.currentText(),
        }
