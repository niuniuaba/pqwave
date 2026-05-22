"""CorrelationMatrixEditor — dialog for editing MC correlation matrices."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QFileDialog, QMessageBox, QLabel, QSpinBox,
    QDoubleSpinBox, QFormLayout, QGroupBox, QComboBox, QLineEdit,
    QDialogButtonBox, QHeaderView,
)
from PyQt6.QtCore import Qt
import csv
import os

from pqwave.models.state import ApplicationState
from pqwave.models.mc_collection import CorrelationMatrix


class CorrelationMatrixEditor(QDialog):
    """Dialog for editing correlation matrices and generating MC output."""

    def __init__(self, parent=None, mc_collection=None):
        super().__init__(parent)
        self.setWindowTitle("MC Correlation Tools")
        self.setMinimumSize(640, 540)
        self._params: list[dict] = []  # all parsed params
        self._mc_collection = mc_collection  # MCRunCollection | None
        self._suppress_cell_changed: bool = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Step 1: Model file loading ---
        model_group = QGroupBox("Step 1: Load Model File")
        model_layout = QVBoxLayout(model_group)

        file_row = QHBoxLayout()
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setPlaceholderText("Path to .model or .lib file...")
        file_row.addWidget(self.model_path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_model_file)
        file_row.addWidget(browse_btn)
        load_btn = QPushButton("Parse")
        load_btn.clicked.connect(self._load_model_file)
        file_row.addWidget(load_btn)
        model_layout.addLayout(file_row)

        self.param_count_label = QLabel("No model file loaded")
        model_layout.addWidget(self.param_count_label)

        layout.addWidget(model_group)

        # --- Step 2: Correlation matrix editor ---
        matrix_group = QGroupBox("Step 2: Correlation Matrix")
        matrix_layout = QVBoxLayout(matrix_group)

        self.matrix_table = QTableWidget()
        self.matrix_table.setMinimumHeight(150)
        self.matrix_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.matrix_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        matrix_layout.addWidget(self.matrix_table)
        self.matrix_table.cellChanged.connect(self._on_cell_changed)

        matrix_buttons = QHBoxLayout()
        load_csv_btn = QPushButton("Load Matrix (CSV)")
        load_csv_btn.clicked.connect(self._load_correlation_csv)
        matrix_buttons.addWidget(load_csv_btn)
        export_csv_btn = QPushButton("Export Matrix (CSV)")
        export_csv_btn.clicked.connect(self._export_correlation_csv)
        matrix_buttons.addWidget(export_csv_btn)
        rebuild_btn = QPushButton("Rebuild from Parsed Params")
        rebuild_btn.clicked.connect(self._rebuild_matrix_from_params)
        matrix_buttons.addWidget(rebuild_btn)
        matrix_layout.addLayout(matrix_buttons)

        layout.addWidget(matrix_group)

        # --- Step 3: Generation ---
        gen_group = QGroupBox("Step 3: Generate Output")
        gen_layout = QFormLayout(gen_group)

        self.n_runs_spin = QSpinBox()
        self.n_runs_spin.setRange(1, 100000)
        self.n_runs_spin.setValue(100)
        self.n_runs_spin.setToolTip(
            "Number of perturbed MC runs (run 0 is always nominal)")
        gen_layout.addRow("MC Runs:", self.n_runs_spin)

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2 ** 31 - 1)
        self.seed_spin.setValue(12345)
        gen_layout.addRow("Seed:", self.seed_spin)

        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "csv — simulator-agnostic (recommended for LTspice/QSPICE)",
            "ngspice — .control script",
            "param — .param snippet",
            "tsv — tab-separated CSV",
        ])
        gen_layout.addRow("Format:", self.format_combo)

        self.sim_command_edit = QLineEdit("tran 1n 100n 0")
        gen_layout.addRow("Sim Command:", self.sim_command_edit)

        # Only show sim_command for ngspice format
        self.sim_command_edit.setVisible(False)
        lbl = gen_layout.labelForField(self.sim_command_edit)
        if lbl:
            lbl.setVisible(False)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)

        self.output_path_edit = QLineEdit()
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path_edit)
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(self._browse_output)
        output_row.addWidget(output_browse)
        gen_layout.addRow("Output:", output_row)

        layout.addWidget(gen_group)

        # --- Bottom buttons ---
        bottom = QHBoxLayout()
        generate_btn = QPushButton("Generate")
        generate_btn.clicked.connect(self._on_generate)
        bottom.addStretch()
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        bottom.addWidget(generate_btn)
        bottom.addWidget(close_box)
        layout.addLayout(bottom)

    def _on_format_changed(self, idx: int):
        fmt = self.format_combo.currentText()
        visible = "ngspice" in fmt
        self.sim_command_edit.setVisible(visible)

    # ---- Model file handling ----

    def _browse_model_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Model File", "",
            "SPICE Files (*.lib *.sp *.cir *.net);;All Files (*)",
        )
        if path:
            self.model_path_edit.setText(path)

    def _load_model_file(self):
        path = self.model_path_edit.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "File not found.")
            return

        from pqwave.analysis.correlation import parse_model_file
        try:
            self._params = parse_model_file(path)
        except Exception as e:
            QMessageBox.warning(self, "Parse Error", str(e))
            return

        model_count = len(set(p["model"] for p in self._params))
        self.param_count_label.setText(
            f"Parsed {len(self._params)} parameters from {model_count} model(s)"
        )
        self._rebuild_matrix_from_params()

    def _rebuild_matrix_from_params(self):
        """Rebuild the matrix table from self._params."""
        self._suppress_cell_changed = True
        n = len(self._params)
        self.matrix_table.clear()
        if n == 0:
            self.matrix_table.setRowCount(0)
            self.matrix_table.setColumnCount(0)
            self._suppress_cell_changed = False
            return

        headers = [p["logical_name"] for p in self._params]
        self.matrix_table.setRowCount(n)
        self.matrix_table.setColumnCount(n)
        self.matrix_table.setHorizontalHeaderLabels(headers)
        self.matrix_table.setVerticalHeaderLabels(headers)

        for r in range(n):
            for c in range(n):
                item = QTableWidgetItem()
                if r == c:
                    item.setText("1.0")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(Qt.GlobalColor.lightGray)
                elif r < c:
                    item.setText("0.0")
                else:
                    item.setText("")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(Qt.GlobalColor.lightGray)
                self.matrix_table.setItem(r, c, item)

        self._suppress_cell_changed = False

    def _on_cell_changed(self, row: int, col: int):
        """Validate range and mirror upper triangle to lower triangle."""
        if self._suppress_cell_changed:
            return
        if row < col:
            item = self.matrix_table.item(row, col)
            raw = item.text() if item else "0.0"
            try:
                val = float(raw)
            except ValueError:
                item.setText("0.0")
                return
            if not -1.0 <= val <= 1.0:
                val = max(-1.0, min(1.0, val))
                item.setText(str(val))
            self._suppress_cell_changed = True
            mirror = self.matrix_table.item(col, row)
            if mirror is not None:
                mirror.setText(str(val))
            self._suppress_cell_changed = False

    # ---- Correlation matrix import/export ----

    def _load_correlation_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Correlation Matrix", "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to read CSV: {e}")
            return

        if len(rows) < 2:
            QMessageBox.warning(self, "Error", "CSV must have header row + at least one data row")
            return

        headers = rows[0][1:]  # first cell is empty or "param"
        n = len(headers)

        # Preserve nominals from previously parsed model file if names match
        existing_nominals = {p["logical_name"]: p["nominal"] for p in self._params}
        self._params = [
            {
                "model": "",
                "param": h,
                "nominal": existing_nominals.get(h, 0.0),
                "logical_name": h,
            }
            for h in headers
        ]
        self._rebuild_matrix_from_params()

        # Fill matrix from CSV
        for r in range(n):
            for c in range(r, n):
                try:
                    val = float(rows[r + 1][c + 1])
                except (IndexError, ValueError):
                    val = 0.0 if r != c else 1.0
                item = QTableWidgetItem(str(val))
                if r == c:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.matrix_table.setItem(r, c, item)
                if r != c:
                    mirror = QTableWidgetItem(str(val))
                    mirror.setFlags(mirror.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.matrix_table.setItem(c, r, mirror)

    def _export_correlation_csv(self):
        n = self.matrix_table.rowCount()
        if n == 0:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Correlation Matrix", "correlation.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            headers = ["param"] + [
                self.matrix_table.horizontalHeaderItem(c).text()
                for c in range(n)
            ]
            writer.writerow(headers)
            for r in range(n):
                row = [self.matrix_table.verticalHeaderItem(r).text()]
                for c in range(n):
                    item = self.matrix_table.item(r, c)
                    row.append(item.text() if item else "0.0")
                writer.writerow(row)

    # ---- Output path ----

    def _browse_output(self):
        fmt = self.format_combo.currentText()
        if "csv" in fmt and "tsv" not in fmt:
            ext = "CSV Files (*.csv)"
        elif "tsv" in fmt:
            ext = "TSV Files (*.tsv)"
        else:
            ext = "SPICE Files (*.sp);;All Files (*)"

        path, _ = QFileDialog.getSaveFileName(self, "Save Output", "", ext)
        if path:
            self.output_path_edit.setText(path)

    # ---- Generate ----

    def _on_generate(self):
        """Collect matrix, call formatter, write output."""
        n = self.matrix_table.rowCount()
        if n == 0:
            QMessageBox.warning(self, "Error", "No parameters configured.")
            return

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Error", "Specify an output file.")
            return

        # Build CorrelationMatrix from table
        param_names = [
            self.matrix_table.verticalHeaderItem(r).text() for r in range(n)
        ]
        flat = []
        for r in range(n):
            for c in range(n):
                item = self.matrix_table.item(r, c)
                flat.append(float(item.text()) if item else 0.0)

        try:
            cm = CorrelationMatrix(params=param_names, matrix=flat)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Invalid matrix: {e}")
            return

        from pqwave.analysis.correlation import (
            compute_cholesky, generate_correlated_values,
            generate_control_script, generate_csv, generate_param_snippet,
        )

        try:
            L = compute_cholesky(cm)
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        # Collect nominals and sigmas from parsed params
        nominals = []
        sigmas = []
        for p in self._params:
            if p["logical_name"] in param_names:
                nominal = p.get("nominal", 0.0)
                nominals.append(nominal)
                sigma_val = abs(nominal * 0.1) if abs(nominal) > 1e-30 else 0.1
                sigmas.append(sigma_val)

        if len(nominals) != n:
            nominals = [0.0] * n
            sigmas = [0.1] * n

        n_runs = self.n_runs_spin.value()
        seed = self.seed_spin.value()

        values = generate_correlated_values(L, nominals, sigmas, n_runs, seed)

        fmt = self.format_combo.currentText()
        if "csv" in fmt and "tsv" not in fmt:
            generate_csv(values, param_names, output_path)
        elif "tsv" in fmt:
            generate_csv(values, param_names, output_path, delimiter="\t")
        elif "ngspice" in fmt:
            # Validate model names: ngspice altermod requires non-empty model
            missing = [p["logical_name"] for p in self._params
                       if p["logical_name"] in param_names and not p.get("model")]
            if missing:
                QMessageBox.warning(
                    self, "Missing Model Names",
                    "The following parameters have no model name — "
                    "ngspice altermod requires model@param syntax.\n\n"
                    f"Parameters: {', '.join(missing)}\n\n"
                    "Load a .model file first, or use CSV output format.",
                )
                return
            sim_cmd = self.sim_command_edit.text()
            generate_control_script(
                params=self._params,
                nominals=nominals,
                L=L,
                output_path=output_path,
                sim_command=sim_cmd,
                n_runs=n_runs,
                seed=seed,
            )
        elif "param" in fmt:
            generate_param_snippet(values, param_names, output_path)

        # Store on MC collection if active
        mc = self._mc_collection
        if mc is None:
            mc = ApplicationState().mc_collection
        if mc is not None:
            mc._correlation = cm

        QMessageBox.information(
            self, "Done",
            f"Generated {n_runs} runs × {n} parameters → {output_path}",
        )

    def get_correlation_matrix(self):
        """Return the current correlation matrix, or None if no data."""
        n = self.matrix_table.rowCount()
        if n == 0:
            return None
        param_names = [
            self.matrix_table.verticalHeaderItem(r).text() for r in range(n)
        ]
        flat = []
        for r in range(n):
            for c in range(n):
                item = self.matrix_table.item(r, c)
                flat.append(float(item.text()) if item else 0.0)
        return CorrelationMatrix(params=param_names, matrix=flat)
