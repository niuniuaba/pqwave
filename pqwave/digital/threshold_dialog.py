"""ThresholdDialog — configures digital signal logic thresholds."""

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDoubleSpinBox, QCheckBox, QDialogButtonBox, QGroupBox,
)

from pqwave.models.trace import Trace
from pqwave.digital.threshold_config import ThresholdConfig, PRESETS


class ThresholdDialog(QDialog):
    """Dialog for setting logic thresholds on a digital trace.

    Provides preset configurations (TTL, CMOS, etc.) and manual override
    of V_high and V_low thresholds.  A *Show preview* checkbox (off by
    default) draws the threshold lines on the plot in real time.
    """

    def __init__(self, trace: Trace, parent=None):
        super().__init__(parent)
        self._trace = trace
        self._config = self._load_config()
        self._plot = parent
        self.setWindowTitle(f"Threshold Settings — {trace.name}")
        self.setMinimumWidth(350)
        self._build_ui()
        self._apply_preset(self._preset_combo.currentText())

    def _load_config(self) -> ThresholdConfig:
        dc = self._trace.digital_config
        if dc:
            return ThresholdConfig(
                v_high=dc.get('v_high', 4.0), v_low=dc.get('v_low', 0.0),
                v_undef=dc.get('v_undef', -0.5),
                description=dc.get('description', ''),
            )
        return ThresholdConfig.from_range(
            float(self._trace.y_data.min()), float(self._trace.y_data.max()))

    def _build_ui(self):
        layout = QVBoxLayout(self)

        preset_group = QGroupBox("Preset")
        preset_layout = QVBoxLayout(preset_group)
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(list(PRESETS.keys()))
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self._preset_combo)
        self._preset_desc = QLabel()
        self._preset_desc.setWordWrap(True)
        preset_layout.addWidget(self._preset_desc)
        layout.addWidget(preset_group)

        manual_group = QGroupBox("Threshold Voltages")
        manual_layout = QHBoxLayout(manual_group)

        v_low_layout = QVBoxLayout()
        v_low_layout.addWidget(QLabel("V_low (1→0)"))
        self._v_low_spin = QDoubleSpinBox()
        self._v_low_spin.setRange(-1000, 1000)
        self._v_low_spin.setDecimals(3)
        self._v_low_spin.setSingleStep(0.1)
        v_low_layout.addWidget(self._v_low_spin)
        manual_layout.addLayout(v_low_layout)

        v_high_layout = QVBoxLayout()
        v_high_layout.addWidget(QLabel("V_high (0→1)"))
        self._v_high_spin = QDoubleSpinBox()
        self._v_high_spin.setRange(-1000, 1000)
        self._v_high_spin.setDecimals(3)
        self._v_high_spin.setSingleStep(0.1)
        v_high_layout.addWidget(self._v_high_spin)
        manual_layout.addLayout(v_high_layout)

        layout.addWidget(manual_group)

        info = QLabel(
            f"Signal range: {self._trace.y_data.min():.3g} – "
            f"{self._trace.y_data.max():.3g}")
        info.setStyleSheet("color: gray;")
        layout.addWidget(info)

        self._preview_cb = QCheckBox("Show preview on plot")
        self._preview_cb.setChecked(
            self._trace.metadata.get('_thresh_preview', False))
        self._preview_cb.toggled.connect(self._on_preview_toggled)
        layout.addWidget(self._preview_cb)

        # Connect spinbox changes for live preview updates
        self._v_high_spin.valueChanged.connect(self._update_preview_lines)
        self._v_low_spin.valueChanged.connect(self._update_preview_lines)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_preset_changed(self, name: str):
        self._apply_preset(name)

    def _apply_preset(self, name: str):
        if name == "Auto (20%/80%)" or name not in PRESETS or PRESETS[name] is None:
            cfg = ThresholdConfig.from_range(
                float(self._trace.y_data.min()), float(self._trace.y_data.max()))
        else:
            cfg = PRESETS[name]
        self._v_high_spin.setValue(cfg.v_high)
        self._v_low_spin.setValue(cfg.v_low)
        self._preset_desc.setText(cfg.description)

    def _on_preview_toggled(self, checked: bool):
        self._trace.metadata['_thresh_preview'] = checked
        if checked:
            self._add_preview_lines()
        else:
            self._remove_preview_lines()

    @property
    def _v_high_line(self):
        return getattr(self._plot, '_thresh_preview_high', None)

    @_v_high_line.setter
    def _v_high_line(self, line):
        self._plot._thresh_preview_high = line

    @property
    def _v_low_line(self):
        return getattr(self._plot, '_thresh_preview_low', None)

    @_v_low_line.setter
    def _v_low_line(self, line):
        self._plot._thresh_preview_low = line

    def _add_preview_lines(self):
        if self._plot is None:
            return
        if self._v_high_line is None:
            line = pg.InfiniteLine(
                angle=0, pen=pg.mkPen('r', width=1, style=Qt.PenStyle.DashLine))
            self._plot.addItem(line)
            self._v_high_line = line
        if self._v_low_line is None:
            line = pg.InfiniteLine(
                angle=0, pen=pg.mkPen('b', width=1, style=Qt.PenStyle.DashLine))
            self._plot.addItem(line)
            self._v_low_line = line
        self._update_preview_lines()

    def _update_preview_lines(self):
        if self._v_high_line is not None:
            self._v_high_line.setValue(self._v_high_spin.value())
        if self._v_low_line is not None:
            self._v_low_line.setValue(self._v_low_spin.value())

    def _remove_preview_lines(self):
        if self._v_high_line is not None and self._plot is not None:
            self._plot.removeItem(self._v_high_line)
            self._v_high_line = None
        if self._v_low_line is not None and self._plot is not None:
            self._plot.removeItem(self._v_low_line)
            self._v_low_line = None

    def _on_accept(self):
        v_high = self._v_high_spin.value()
        v_low = self._v_low_spin.value()
        if v_high <= v_low:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Invalid Thresholds",
                "V_high must be greater than V_low for Schmitt-trigger operation.")
            return
        dc = self._trace.digital_config or {}
        dc['v_high'] = v_high
        dc['v_low'] = v_low
        self._trace.digital_config = dc
        self._config = ThresholdConfig(v_high=v_high, v_low=v_low)
        self.accept()

    def get_config(self) -> ThresholdConfig:
        return self._config
