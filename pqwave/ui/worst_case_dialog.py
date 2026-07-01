#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""WorstCaseDialog - configure component tolerances for worst-case analysis."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QPushButton,
    QHBoxLayout,
    QDialogButtonBox,
    QLabel,
    QDoubleSpinBox,
    QLineEdit,
    QFileDialog,
    QComboBox,
    QFormLayout,
    QGroupBox,
)


class WorstCaseDialog(QDialog):
    """Dialog for configuring worst-case analysis parameters."""

    def __init__(self, parent=None, netlist_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Worst Case Analysis")
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        # Netlist selection
        netlist_group = QGroupBox("Netlist")
        netlist_layout = QHBoxLayout()
        self._netlist_edit = QLineEdit(netlist_path)
        self._netlist_edit.setPlaceholderText("Path to SPICE netlist...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_netlist)
        netlist_layout.addWidget(self._netlist_edit)
        netlist_layout.addWidget(browse_btn)
        netlist_group.setLayout(netlist_layout)
        layout.addWidget(netlist_group)

        # Temperature range
        temp_group = QGroupBox("Temperature")
        temp_form = QFormLayout()
        self._t_nom_spin = QDoubleSpinBox()
        self._t_nom_spin.setRange(-273.15, 300.0)
        self._t_nom_spin.setValue(27.0)
        self._t_nom_spin.setSuffix(" °C")
        temp_form.addRow("Nominal T:", self._t_nom_spin)

        self._t_min_spin = QDoubleSpinBox()
        self._t_min_spin.setRange(-273.15, 300.0)
        self._t_min_spin.setValue(-40.0)
        self._t_min_spin.setSuffix(" °C")
        temp_form.addRow("Min T:", self._t_min_spin)

        self._t_max_spin = QDoubleSpinBox()
        self._t_max_spin.setRange(-273.15, 300.0)
        self._t_max_spin.setValue(85.0)
        self._t_max_spin.setSuffix(" °C")
        temp_form.addRow("Max T:", self._t_max_spin)
        temp_group.setLayout(temp_form)
        layout.addWidget(temp_group)

        # Component tolerance table
        tol_group = QGroupBox("Component Tolerances")
        tol_layout = QVBoxLayout()
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["RefDes", "Nominal", "Tol %", "Tempco (ppm/°C)"]
        )
        tol_layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton("Remove Row")
        remove_btn.clicked.connect(self._remove_row)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        tol_layout.addLayout(btn_layout)
        tol_group.setLayout(tol_layout)
        layout.addWidget(tol_group)

        # Analysis type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Analysis Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["op", "ac", "tran"])
        type_layout.addWidget(self._type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse_netlist(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Netlist",
            "",
            "SPICE Netlists (*.cir *.sp *.spice *.net);;All Files (*)",
        )
        if path:
            self._netlist_edit.setText(path)

    def _add_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)

    def _remove_row(self):
        current = self._table.currentRow()
        if current >= 0:
            self._table.removeRow(current)

    def get_netlist_path(self) -> str:
        return self._netlist_edit.text().strip()

    def get_temperature_range(self) -> tuple[float, float, float]:
        return (
            self._t_min_spin.value(),
            self._t_max_spin.value(),
            self._t_nom_spin.value(),
        )

    def get_analysis_type(self) -> str:
        return self._type_combo.currentText()

    def get_components(self) -> dict:
        """Parse the tolerance table into components dict."""
        components = {}
        for row in range(self._table.rowCount()):
            refdes_item = self._table.item(row, 0)
            nominal_item = self._table.item(row, 1)
            tol_item = self._table.item(row, 2)
            tempco_item = self._table.item(row, 3)

            if refdes_item is None or nominal_item is None:
                continue

            refdes = refdes_item.text().strip()
            try:
                nominal = float(nominal_item.text().strip())
            except ValueError:
                continue

            tol_pct = 5.0
            if tol_item and tol_item.text().strip():
                try:
                    tol_pct = float(tol_item.text().strip())
                except ValueError:
                    pass

            tempco = 0.0
            if tempco_item and tempco_item.text().strip():
                try:
                    tempco = float(tempco_item.text().strip()) * 1e-6
                except ValueError:
                    pass

            if refdes:
                components[refdes] = {
                    "nominal": nominal,
                    "tolerance": tol_pct / 100.0,
                    "tempco": tempco,
                }

        return components
