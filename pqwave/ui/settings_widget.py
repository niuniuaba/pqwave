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
    QFontComboBox, QSpinBox, QColorDialog
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

    def _on_theme_changed(self, index: int) -> None:
        """Handle viewbox theme selection changes."""
        theme = self.theme_combo.itemData(index)
        if theme is not None:
            self.state.viewbox_theme = theme
            self.viewbox_theme_changed.emit(theme)

    def _on_log_mode_changed(self, axis_id: AxisId, state: int):
        """Handle log mode checkbox changes."""
        log_mode = (state == Qt.CheckState.Checked.value)
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