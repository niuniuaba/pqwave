#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ControlPanel - Dataset/vector selection and trace addition controls.

This module provides a widget containing dataset and vector comboboxes,
expression entry field, and X/Y1/Y2 buttons for adding traces.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
    QCompleter,
)
from PyQt6.QtCore import pyqtSignal, Qt

from pqwave.ui.functions_combo import FunctionsCombo
from pqwave.ui.measures_combo import MeasuresCombo
from pqwave.ui.grouped_vector_combo import GroupedVectorCombo


class ControlPanel(QWidget):
    """Control panel for dataset/vector selection and trace addition.

    Signals:
        dataset_changed(int): Emitted when dataset combo selection changes
        vector_selected(str): Emitted when vector combo selection changes
        add_trace_to_axis(str): Emitted when X/Y1/Y2 button clicked
        expression_changed(str): Emitted when trace expression text changes
    """

    dataset_changed = pyqtSignal(int)
    vector_selected = pyqtSignal(str)
    add_trace_to_axis = pyqtSignal(str)  # "X", "Y1", "Y2"
    expression_changed = pyqtSignal(str)
    function_selected = pyqtSignal(object)  # carries FunctionInfo
    measure_selected = pyqtSignal(object)  # carries FunctionInfo
    run_measure_requested = pyqtSignal()
    from_script_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.dataset_combo = None
        self.vector_combo = None
        self.func_combo = None
        self.measure_combo = None
        self.trace_expr = None
        self.measure_expr = None
        self.from_script_btn = None
        self.run_btn = None
        self.x_button = None
        self.y1_button = None
        self.y2_button = None
        self._last_focused_expr: QLineEdit | None = None

        self._setup_ui()
        self._last_focused_expr = self.trace_expr

    def _setup_ui(self):
        """Create UI layout."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        # First row: Dataset and Vector combos
        first_row = QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(10)

        # Dataset controls
        dataset_label = QLabel("Dataset:")
        self.dataset_combo = QComboBox()
        self.dataset_combo.currentIndexChanged.connect(self.dataset_changed.emit)
        self.dataset_combo.setMaximumWidth(200)
        first_row.addWidget(dataset_label)
        first_row.addWidget(self.dataset_combo)

        # Add spacing
        first_row.addSpacing(20)

        # Vector controls (grouped, multi-select)
        vector_label = QLabel("Vector:")
        self.vector_combo = GroupedVectorCombo()
        self.vector_combo.vectors_selected.connect(self._on_vectors_selected)
        first_row.addWidget(vector_label)
        first_row.addWidget(self.vector_combo)

        # Add spacing
        first_row.addSpacing(20)

        # Function controls
        func_label = QLabel("Func:")
        self.func_combo = FunctionsCombo()
        self.func_combo.setMaximumWidth(160)
        self.func_combo.function_selected.connect(self.function_selected.emit)
        first_row.addWidget(func_label)
        first_row.addWidget(self.func_combo)

        # Add spacing
        first_row.addSpacing(20)

        # Measure function controls
        measure_label = QLabel("Measure:")
        self.measure_combo = MeasuresCombo()
        self.measure_combo.setMaximumWidth(200)
        self.measure_combo.function_selected.connect(self.measure_selected.emit)
        first_row.addWidget(measure_label)
        first_row.addWidget(self.measure_combo)

        # Add stretch to push controls to the left
        first_row.addStretch()

        main_layout.addLayout(first_row)

        # Second row: Add Trace and buttons
        second_row = QHBoxLayout()
        second_row.setContentsMargins(0, 0, 0, 0)
        second_row.setSpacing(10)

        # Add Trace controls
        trace_label = QLabel("Add Trace:")
        trace_label.setToolTip("Expressions must be quoted inside \"\" or ''")
        self.trace_expr = QLineEdit()
        self.trace_expr.setMinimumWidth(200)
        self.trace_expr.setToolTip("Expressions must be quoted inside \"\" or ''")
        self.trace_expr.textChanged.connect(self.expression_changed.emit)
        second_row.addWidget(trace_label)
        second_row.addWidget(self.trace_expr, 1)  # Stretch factor 1

        # Create button layout for X, Y1, Y2 buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(5)

        # X button - for adding X-axis trace
        self.x_button = QPushButton("X")
        self.x_button.setToolTip("Expressions must be quoted inside \"\" or ''")
        self.x_button.clicked.connect(lambda: self.add_trace_to_axis.emit("X"))
        self.x_button.setMaximumWidth(40)
        button_layout.addWidget(self.x_button)

        # Y1 button - for adding Y1-axis trace
        self.y1_button = QPushButton("Y1")
        self.y1_button.setToolTip("Expressions must be quoted inside \"\" or ''")
        self.y1_button.clicked.connect(lambda: self.add_trace_to_axis.emit("Y1"))
        self.y1_button.setMaximumWidth(40)
        button_layout.addWidget(self.y1_button)

        # Y2 button - for adding Y2-axis trace
        self.y2_button = QPushButton("Y2")
        self.y2_button.setToolTip("Expressions must be quoted inside \"\" or ''")
        self.y2_button.clicked.connect(lambda: self.add_trace_to_axis.emit("Y2"))
        self.y2_button.setMaximumWidth(40)
        button_layout.addWidget(self.y2_button)

        # Add button layout to second row
        second_row.addLayout(button_layout)

        main_layout.addLayout(second_row)

        # Third row: Measurement expression / script path + From Script + RUN
        third_row = QHBoxLayout()
        third_row.setContentsMargins(0, 0, 0, 0)
        third_row.setSpacing(10)

        measure_expr_label = QLabel("Measurement:")
        self.measure_expr = QLineEdit()
        self.measure_expr.setMinimumWidth(200)
        self.measure_expr.setToolTip("Enter a measurement expression, e.g. avg(v(out)), or a script path.")
        third_row.addWidget(measure_expr_label)
        third_row.addWidget(self.measure_expr, 1)

        self.from_script_btn = QPushButton("From Script")
        self.from_script_btn.setToolTip("Load a .meas-style script file for batch execution")
        self.from_script_btn.clicked.connect(self.from_script_requested.emit)
        third_row.addWidget(self.from_script_btn)

        self.run_btn = QPushButton("RUN")
        self.run_btn.setToolTip("Evaluate measurement expression or batch script")
        self.run_btn.clicked.connect(self.run_measure_requested.emit)
        third_row.addWidget(self.run_btn)

        main_layout.addLayout(third_row)

        self.setLayout(main_layout)

        # Install focus tracking on both expression fields
        self.trace_expr.installEventFilter(self)
        self.measure_expr.installEventFilter(self)

    def _on_vectors_selected(self, text: str):
        """Handle multi-selection from the grouped vector popup."""
        if text:
            self.vector_selected.emit(text)

    def eventFilter(self, obj, event):
        """Track which QLineEdit last received focus."""
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QLineEdit):
            self._last_focused_expr = obj
        return super().eventFilter(obj, event)

    @property
    def last_focused_expr(self) -> QLineEdit:
        """Return the expression field that last had focus (trace_expr or measure_expr)."""
        return self._last_focused_expr

    # Public API for measurement controls

    def set_measure_expression(self, text: str):
        """Set measurement expression text."""
        self.measure_expr.setText(text)

    def get_measure_expression(self) -> str:
        """Get current measurement expression text."""
        return self.measure_expr.text()

    def clear_measure_expression(self):
        """Clear measurement expression."""
        self.measure_expr.clear()

    def set_script_mode(self, filepath: str):
        """Switch measure_expr to script path display."""
        self.measure_expr.setToolTip(f"Script: {filepath}")
        self.measure_expr.setText(filepath)

    def set_expression_mode(self):
        """Restore measure_expr tooltip for expression entry."""
        self.measure_expr.setToolTip("Enter a measurement expression, e.g. avg(v(out)), or a script path.")

    def set_run_enabled(self, enabled: bool):
        """Enable/disable the RUN button."""
        self.run_btn.setEnabled(enabled)

    # Public API for updating controls

    def set_datasets(self, datasets):
        """Update dataset combo with list of dataset names."""
        self.dataset_combo.clear()
        for i, dataset in enumerate(datasets):
            self.dataset_combo.addItem(dataset, i)

    def set_current_dataset(self, index):
        """Set current dataset selection."""
        if 0 <= index < self.dataset_combo.count():
            self.dataset_combo.setCurrentIndex(index)

    def set_variables(self, groups):
        """Update vector combo with grouped variable names.

        Args:
            groups: dict mapping source-file label → list of variable names.
        """
        self.vector_combo.set_groups(groups)

    def set_current_variable(self, name):
        """Set current variable selection (no-op for grouped combo)."""
        self.vector_combo.set_check_state(name, True)

    def set_expression(self, text):
        """Set trace expression text."""
        self.trace_expr.setText(text)

    def get_expression(self):
        """Get current trace expression text."""
        return self.trace_expr.text()

    def clear_expression(self):
        """Clear trace expression."""
        self.trace_expr.clear()

    def set_buttons_enabled(self, enabled):
        """Enable/disable all buttons."""
        self.x_button.setEnabled(enabled)
        self.y1_button.setEnabled(enabled)
        self.y2_button.setEnabled(enabled)
