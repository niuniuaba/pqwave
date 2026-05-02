#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SettingsWidget - Widget for configuring plot title and axis settings.

This widget provides controls for:
- Plot title
- X, Y1, Y2 axis settings (log mode, range, auto-range)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QGroupBox, QGridLayout, QPushButton, QDoubleSpinBox, QComboBox,
    QFontComboBox, QSpinBox, QColorDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from pqwave.models.state import AxisId, ApplicationState, ViewboxTheme, THEME_COLORS, FontConfig
from pqwave.ui.axis_manager import AxisManager


class SettingsWidget(QWidget):
    """Settings widget for plot title and axis configuration."""

    # Signal emitted when plot title changes
    viewbox_theme_changed = pyqtSignal(ViewboxTheme)
    font_changed = pyqtSignal()

    def __init__(self,
                 axis_manager: AxisManager,
                 application_state: ApplicationState,
                 parent=None):
        """Initialize SettingsWidget.

        Args:
            axis_manager: AxisManager instance for axis operations
            application_state: ApplicationState singleton
            parent: Parent widget
        """
        super().__init__(parent)
        self.axis_manager = axis_manager
        self.state = application_state

        # Dictionaries to store widgets for each axis
        self.log_checkboxes = {}
        self.min_spinboxes = {}
        self.max_spinboxes = {}
        self.auto_buttons = {}
        self.label_edits = {}

        # Font control storage
        self.font_family_combos = {}
        self.font_size_spinboxes = {}
        self.font_color_buttons = {}

        self.setWindowTitle("Plot Settings")
        self.setMinimumWidth(600)
        # Set window flags to make it independent window
        self.setWindowFlags(Qt.WindowType.Window |
                           Qt.WindowType.WindowCloseButtonHint |
                           Qt.WindowType.WindowMinimizeButtonHint)

        self._create_ui()
        self._load_current_settings()

    def _create_ui(self):
        """Create the user interface."""
        layout = QVBoxLayout(self)

        # Viewbox theme selector
        theme_group = QGroupBox("Viewbox Theme")
        theme_layout = QHBoxLayout()
        theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", ViewboxTheme.DARK)
        self.theme_combo.addItem("Light", ViewboxTheme.LIGHT)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # Fonts
        fonts_group = QGroupBox("Fonts")
        fonts_layout = QGridLayout()

        _FONT_ELEMENTS = [
            ("Title:", "title_font"),
            ("Axis Labels:", "label_font"),
            ("Tick Labels:", "tick_font"),
            ("UI:", "ui_font"),
        ]

        for row, (label_text, key) in enumerate(_FONT_ELEMENTS):
            label = QLabel(label_text)
            fonts_layout.addWidget(label, row, 0)

            # Font family
            family_combo = QFontComboBox()
            family_combo.setEditable(False)
            family_combo.insertItem(0, "Default")
            family_combo.currentIndexChanged.connect(lambda idx, k=key: self._on_font_changed())
            self.font_family_combos[key] = family_combo
            fonts_layout.addWidget(family_combo, row, 1)

            # Size
            size_spin = QSpinBox()
            size_spin.setRange(0, 48)
            size_spin.setSuffix(" pt")
            size_spin.setSpecialValueText("Default")
            size_spin.valueChanged.connect(lambda v, k=key: self._on_font_changed())
            self.font_size_spinboxes[key] = size_spin
            fonts_layout.addWidget(size_spin, row, 2)

            # Color button
            color_btn = QPushButton()
            color_btn.setFixedSize(28, 28)
            color_btn.setToolTip("Select font color (empty = use theme foreground)")
            color_btn.clicked.connect(lambda checked, k=key: self._pick_font_color(k))
            self.font_color_buttons[key] = color_btn
            fonts_layout.addWidget(color_btn, row, 3)

            # Reset
            reset_btn = QPushButton("Reset")
            reset_btn.clicked.connect(lambda checked, k=key: self._reset_font(k))
            fonts_layout.addWidget(reset_btn, row, 4)

        fonts_group.setLayout(fonts_layout)
        layout.addWidget(fonts_group)

        # Axes settings
        axes_group = QGroupBox("Axes Settings")
        axes_layout = QHBoxLayout()

        # X-axis
        x_group = self._create_axis_group("X-axis", AxisId.X)
        axes_layout.addWidget(x_group)

        # Y1-axis
        y1_group = self._create_axis_group("Y1-axis", AxisId.Y1)
        axes_layout.addWidget(y1_group)

        # Y2-axis
        y2_group = self._create_axis_group("Y2-axis", AxisId.Y2)
        axes_layout.addWidget(y2_group)

        axes_group.setLayout(axes_layout)
        layout.addWidget(axes_group)

        # FFT settings
        fft_group = QGroupBox("FFT Settings")
        fft_layout = QGridLayout()

        # Window type
        fft_layout.addWidget(QLabel("Window:"), 0, 0)
        self.fft_window_combo = QComboBox()
        self._fft_window_names = [
            "bartlett-hann", "blackman", "blackman-harris", "bohman",
            "cosine", "dolph-chebyshev", "flattop", "gaussian",
            "general-gaussian", "hamming", "hann", "kaiser",
            "lanczos", "none", "nuttall", "parzen", "poisson",
            "triangular", "tukey", "welch",
        ]
        self.fft_window_combo.addItems(self._fft_window_names)
        self.fft_window_combo.currentTextChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_window_combo, 0, 1)

        # FFT size
        fft_layout.addWidget(QLabel("FFT Size:"), 0, 2)
        self.fft_size_combo = QComboBox()
        self.fft_size_combo.setEditable(True)
        self.fft_size_combo.addItem("Auto", 0)
        for n in [1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]:
            self.fft_size_combo.addItem(str(n), n)
        self.fft_size_combo.currentIndexChanged.connect(self._on_fft_changed)
        self.fft_size_combo.editTextChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_size_combo, 0, 3)

        # X range mode
        fft_layout.addWidget(QLabel("X Range:"), 1, 0)
        self.fft_xrange_combo = QComboBox()
        self.fft_xrange_combo.addItems(["full", "current zoom", "manual"])
        self.fft_xrange_combo.currentTextChanged.connect(self._on_fft_xrange_changed)
        fft_layout.addWidget(self.fft_xrange_combo, 1, 1)

        self.fft_xrange_start = QDoubleSpinBox()
        self.fft_xrange_start.setRange(-1e9, 1e9)
        self.fft_xrange_start.setDecimals(6)
        self.fft_xrange_start.setSuffix(" s")
        self.fft_xrange_start.setVisible(False)
        self.fft_xrange_start.valueChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_xrange_start, 1, 2)

        self.fft_xrange_end = QDoubleSpinBox()
        self.fft_xrange_end.setRange(-1e9, 1e9)
        self.fft_xrange_end.setDecimals(6)
        self.fft_xrange_end.setSuffix(" s")
        self.fft_xrange_end.setValue(0.001)
        self.fft_xrange_end.setVisible(False)
        self.fft_xrange_end.valueChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_xrange_end, 1, 3)

        # Binomial smooth
        fft_layout.addWidget(QLabel("Binomial Smooth:"), 2, 0)
        self.fft_binomial_spin = QSpinBox()
        self.fft_binomial_spin.setRange(0, 100)
        self.fft_binomial_spin.setSuffix(" passes")
        self.fft_binomial_spin.setToolTip("Number of binomial smoothing passes before FFT (0 = off)")
        self.fft_binomial_spin.valueChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_binomial_spin, 2, 1)

        # DC removal
        self.fft_dc_checkbox = QCheckBox("DC Removal")
        self.fft_dc_checkbox.stateChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_dc_checkbox, 2, 2, 1, 2)

        # Representation
        fft_layout.addWidget(QLabel("Representation:"), 3, 2)
        self.fft_repr_combo = QComboBox()
        self.fft_repr_combo.addItems(["db", "linear"])
        self.fft_repr_combo.currentTextChanged.connect(self._on_fft_changed)
        fft_layout.addWidget(self.fft_repr_combo, 3, 3)

        fft_group.setLayout(fft_layout)
        layout.addWidget(fft_group)

        # Close button
        button_layout = QHBoxLayout()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _create_axis_group(self, title: str, axis_id: AxisId):
        """Create axis settings group.

        Args:
            title: Group title
            axis_id: Axis identifier

        Returns:
            QGroupBox configured for the axis
        """
        group = QGroupBox(title)
        layout = QVBoxLayout()

        # Log mode checkbox
        log_layout = QHBoxLayout()
        log_checkbox = QCheckBox("Log")
        log_checkbox.stateChanged.connect(
            lambda state, axis=axis_id: self._on_log_mode_changed(axis, state)
        )
        self.log_checkboxes[axis_id] = log_checkbox
        log_layout.addWidget(log_checkbox)
        log_layout.addStretch()
        layout.addLayout(log_layout)

        # Axis label edit
        label_layout = QHBoxLayout()
        label_label = QLabel("Label:")
        label_edit = QLineEdit()
        label_edit.setPlaceholderText("Axis label...")
        label_edit.setMaximumWidth(150)
        label_edit.textChanged.connect(
            lambda text, axis=axis_id: self._on_label_changed(axis, text)
        )
        self.label_edits[axis_id] = label_edit
        label_layout.addWidget(label_label)
        label_layout.addWidget(label_edit)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(2)
        layout.addLayout(label_layout)

        # Range settings
        range_group = QGroupBox("Range")
        range_layout = QGridLayout()

        # Min spinbox
        min_label = QLabel("Min:")
        min_spinbox = QDoubleSpinBox()
        min_spinbox.setDecimals(6)
        min_spinbox.setMinimum(-1e9)
        min_spinbox.setMaximum(1e9)
        min_spinbox.setMaximumWidth(100)
        min_spinbox.valueChanged.connect(
            lambda value, axis=axis_id: self._on_range_changed(axis)
        )
        self.min_spinboxes[axis_id] = min_spinbox
        range_layout.addWidget(min_label, 0, 0)
        range_layout.addWidget(min_spinbox, 0, 1)

        # Max spinbox
        max_label = QLabel("Max:")
        max_spinbox = QDoubleSpinBox()
        max_spinbox.setDecimals(6)
        max_spinbox.setMinimum(-1e9)
        max_spinbox.setMaximum(1e9)
        max_spinbox.setMaximumWidth(100)
        max_spinbox.valueChanged.connect(
            lambda value, axis=axis_id: self._on_range_changed(axis)
        )
        self.max_spinboxes[axis_id] = max_spinbox
        range_layout.addWidget(max_label, 1, 0)
        range_layout.addWidget(max_spinbox, 1, 1)

        # Auto-range button
        auto_button = QPushButton("Auto")
        auto_button.clicked.connect(
            lambda checked, axis=axis_id: self._on_auto_range_clicked(axis)
        )
        auto_button.setMaximumWidth(80)
        self.auto_buttons[axis_id] = auto_button
        range_layout.addWidget(auto_button, 2, 0, 1, 2)

        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        group.setLayout(layout)
        return group

    def _load_current_settings(self):
        """Load current settings from application state."""
        # Viewbox theme
        theme = self.state.viewbox_theme
        index = self.theme_combo.findData(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

        # Load axis settings
        for axis_id in AxisId:
            config = self.state.get_axis_config(axis_id)

            # Log mode
            self.log_checkboxes[axis_id].setChecked(config.log_mode)

            # Label
            self.label_edits[axis_id].setText(config.label)

            # Range
            if config.range and not config.auto_range:
                min_val, max_val = config.range
                self.min_spinboxes[axis_id].blockSignals(True)
                self.max_spinboxes[axis_id].blockSignals(True)
                self.min_spinboxes[axis_id].setValue(min_val)
                self.max_spinboxes[axis_id].setValue(max_val)
                self.min_spinboxes[axis_id].blockSignals(False)
                self.max_spinboxes[axis_id].blockSignals(False)
            else:
                # Auto-range mode - clear spinboxes
                self.min_spinboxes[axis_id].blockSignals(True)
                self.max_spinboxes[axis_id].blockSignals(True)
                self.min_spinboxes[axis_id].setValue(0.0)
                self.max_spinboxes[axis_id].setValue(1.0)
                self.min_spinboxes[axis_id].blockSignals(False)
                self.max_spinboxes[axis_id].blockSignals(False)

        # Load font settings (block signals to avoid premature emits)
        for key in ("title_font", "label_font", "tick_font", "ui_font"):
            fc = getattr(self.state, key)
            combo = self.font_family_combos[key]
            combo.blockSignals(True)
            if fc.family:
                idx = combo.findText(fc.family)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)
            spin = self.font_size_spinboxes[key]
            spin.blockSignals(True)
            spin.setValue(fc.size)
            spin.blockSignals(False)
            self._update_color_button(key)

        # Load FFT settings
        fft = self.state.fft_config
        idx = self.fft_window_combo.findText(fft.window)
        if idx >= 0:
            self.fft_window_combo.setCurrentIndex(idx)
        # fft_size: try findData first, then try parse from text
        idx = self.fft_size_combo.findData(fft.fft_size)
        if idx >= 0:
            self.fft_size_combo.setCurrentIndex(idx)
        elif fft.fft_size > 0:
            self.fft_size_combo.setCurrentText(str(fft.fft_size))
        self.fft_dc_checkbox.setChecked(fft.dc_removal)
        idx = self.fft_repr_combo.findText(fft.representation)
        if idx >= 0:
            self.fft_repr_combo.setCurrentIndex(idx)
        idx = self.fft_xrange_combo.findText(fft.x_range_mode)
        if idx >= 0:
            self.fft_xrange_combo.setCurrentIndex(idx)
        self.fft_xrange_start.setValue(fft.x_range_start)
        self.fft_xrange_end.setValue(fft.x_range_end)
        self.fft_binomial_spin.setValue(fft.binomial_smooth)
        self._update_fft_xrange_visibility()

    def _on_fft_changed(self) -> None:
        """Handle FFT settings changes — write to ApplicationState."""
        cfg = self.state.fft_config
        cfg.window = self.fft_window_combo.currentText()
        cfg.fft_size = self._read_fft_size()
        cfg.dc_removal = self.fft_dc_checkbox.isChecked()
        cfg.representation = self.fft_repr_combo.currentText()
        cfg.x_range_mode = self.fft_xrange_combo.currentText()
        cfg.x_range_start = self.fft_xrange_start.value()
        cfg.x_range_end = self.fft_xrange_end.value()
        cfg.binomial_smooth = self.fft_binomial_spin.value()

    def _on_fft_xrange_changed(self, text: str) -> None:
        """Show/hide manual range spin boxes when mode changes."""
        self._update_fft_xrange_visibility()
        self._on_fft_changed()

    def _update_fft_xrange_visibility(self) -> None:
        visible = self.fft_xrange_combo.currentText() == "manual"
        self.fft_xrange_start.setVisible(visible)
        self.fft_xrange_end.setVisible(visible)

    def _read_fft_size(self) -> int:
        """Read FFT size from editable combo, accepting user-typed values."""
        data = self.fft_size_combo.currentData()
        if data is not None:
            return int(data)
        text = self.fft_size_combo.currentText().strip()
        if text.lower() == "auto":
            return 0
        try:
            return int(text)
        except ValueError:
            return 0

    def _on_theme_changed(self, index: int) -> None:
        """Handle viewbox theme selection changes."""
        theme = self.theme_combo.itemData(index)
        if theme is not None:
            self.state.viewbox_theme = theme
            self.viewbox_theme_changed.emit(theme)

    def _on_log_mode_changed(self, axis_id: AxisId, state: int):
        """Handle log mode checkbox changes."""
        log_mode = (state == Qt.CheckState.Checked.value)

        # Block enabling Y log mode when FFT traces are on that axis
        if log_mode and axis_id in (AxisId.Y1, AxisId.Y2):
            axis_str = axis_id.value
            if any(
                t.expression.lower().startswith('fft(')
                and t.y_axis.value == axis_str
                for t in self.state.traces
            ):
                QMessageBox.information(
                    self, "Log Y Not Available",
                    "FFT traces are already in dB (log scale). "
                    "Log Y mode is not applicable."
                )
                self.log_checkboxes[axis_id].setChecked(False)
                return

        self.axis_manager.set_axis_log_mode(axis_id, log_mode)

    def _on_label_changed(self, axis_id: AxisId, text: str):
        """Handle axis label changes."""
        self.axis_manager.set_axis_label(axis_id, text)

    def _on_range_changed(self, axis_id: AxisId):
        """Handle range spinbox changes."""
        min_val = self.min_spinboxes[axis_id].value()
        max_val = self.max_spinboxes[axis_id].value()
        if min_val < max_val:
            self.axis_manager.set_axis_range(axis_id, min_val, max_val)

    def _on_auto_range_clicked(self, axis_id: AxisId):
        """Handle auto-range button clicks."""
        self.axis_manager.auto_range_axis(axis_id)
        # Clear spinboxes to indicate auto-range mode
        self.min_spinboxes[axis_id].setValue(0.0)
        self.max_spinboxes[axis_id].setValue(1.0)

    # --- Font settings handlers ---

    def _on_font_changed(self):
        """Handle any font control change -- save to state and notify."""
        self._save_fonts_to_state()
        self.font_changed.emit()

    def _save_fonts_to_state(self):
        """Write current font control values into ApplicationState."""
        for key in ("title_font", "label_font", "tick_font", "ui_font"):
            fc = getattr(self.state, key)
            combo = self.font_family_combos[key]
            fc.family = "" if combo.currentIndex() == 0 else combo.currentFont().family()
            fc.size = self.font_size_spinboxes[key].value()

    def _pick_font_color(self, key: str):
        """Open QColorDialog and update the font color."""
        fc = getattr(self.state, key)
        current = QColor(fc.color) if fc.color else QColor()
        color = QColorDialog.getColor(current, self, f"Select Font Color")
        if color.isValid():
            fc.color = color.name()
            self._update_color_button(key)
            self.font_changed.emit()

    def _reset_font(self, key: str):
        """Reset a font config to defaults."""
        fc = getattr(self.state, key)
        fc.family = ""
        fc.size = 0
        fc.color = ""
        self.font_family_combos[key].blockSignals(True)
        self.font_family_combos[key].setCurrentIndex(0)
        self.font_family_combos[key].blockSignals(False)
        self.font_size_spinboxes[key].blockSignals(True)
        self.font_size_spinboxes[key].setValue(0)
        self.font_size_spinboxes[key].blockSignals(False)
        self._update_color_button(key)
        self.font_changed.emit()

    def _update_color_button(self, key: str):
        """Update color button background to reflect current font color."""
        fc = getattr(self.state, key)
        btn = self.font_color_buttons[key]
        if fc.color:
            btn.setStyleSheet(
                f"background-color: {fc.color}; border: 1px solid #888; border-radius: 2px;"
            )
        else:
            btn.setStyleSheet("")