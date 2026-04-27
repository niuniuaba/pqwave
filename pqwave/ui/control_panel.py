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

    def __init__(self, parent=None):
        super().__init__(parent)

        self.dataset_combo = None
        self.vector_combo = None
        self.func_combo = None
        self.trace_expr = None
        self.x_button = None
        self.y1_button = None
        self.y2_button = None

        self._setup_ui()

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

        # Vector controls
        vector_label = QLabel("Vector:")
        self.vector_combo = QComboBox()
        self.vector_combo.textActivated.connect(self.vector_selected.emit)
        self.vector_combo.setMaximumWidth(200)
        self.vector_combo.setEditable(True)
        self.vector_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self.vector_combo.model(), self.vector_combo)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.vector_combo.setCompleter(completer)
        self.vector_combo.lineEdit().editingFinished.connect(self._on_vector_editing_finished)
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

        self.setLayout(main_layout)

    def _on_vector_editing_finished(self):
        """Restore the last valid selection if the typed text doesn't match any item."""
        text = self.vector_combo.currentText()
        if text and self.vector_combo.findText(text) < 0:
            self.vector_combo.setEditText(
                self.vector_combo.itemText(self.vector_combo.currentIndex())
            )

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

    def set_variables(self, variables):
        """Update vector combo with list of variable names."""
        # Block signals to prevent spurious vector_selected emissions during population
        self.vector_combo.blockSignals(True)
        self.vector_combo.clear()
        for var in variables:
            self.vector_combo.addItem(var)
        self.vector_combo.blockSignals(False)

    def set_current_variable(self, name):
        """Set current variable selection."""
        index = self.vector_combo.findText(name)
        if index >= 0:
            self.vector_combo.setCurrentIndex(index)

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
