"""Monte Carlo open configuration dialog."""
from dataclasses import dataclass, field
from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QFileDialog, QFormLayout, QSpinBox, QGroupBox, QListWidget,
    QDialogButtonBox, QMessageBox,
)


@dataclass
class MCConfig:
    """Configuration produced by the MC open dialog."""
    source_type: str  # "stepped", "multi", "pattern"
    file_path: str = ""
    file_paths: List[str] = field(default_factory=list)
    grouping_pattern: Optional[str] = None
    run_count_override: Optional[int] = None

    @property
    def is_stepped(self) -> bool:
        return self.source_type == "stepped"

    @property
    def is_multi_file(self) -> bool:
        return self.source_type == "multi"


class MCOpenDialog(QDialog):
    """Dialog for configuring how MC data is loaded."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Monte Carlo Data")
        self.setMinimumWidth(550)
        self._config: Optional[MCConfig] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Source type selector
        type_group = QGroupBox("Source")
        type_layout = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItem("Single stepped file (.step)", "stepped")
        self.source_combo.addItem("Multiple files (one per run)", "multi")
        self.source_combo.addItem("Single file with named runs (vout0..voutN)", "pattern")
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        type_layout.addWidget(QLabel("Type:"))
        type_layout.addWidget(self.source_combo, 1)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # File selection
        file_group = QGroupBox("File")
        file_layout = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("Select a raw file...")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_path_edit, 1)
        file_layout.addWidget(self.browse_btn)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Multi-file list (hidden initially)
        self.multi_file_list = QListWidget()
        self.multi_file_list.setVisible(False)
        self._add_files_btn = QPushButton("Add Files...")
        self._add_files_btn.clicked.connect(self._add_files)
        self._add_files_btn.setVisible(False)
        layout.addWidget(self.multi_file_list)
        layout.addWidget(self._add_files_btn)

        # Pattern configuration (hidden initially)
        self._pattern_group = QGroupBox("Run Grouping Pattern")
        pattern_layout = QFormLayout()
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("e.g., vout (matches vout0, vout1, ...)")
        self.run_count_spin = QSpinBox()
        self.run_count_spin.setRange(0, 10000)
        self.run_count_spin.setValue(0)
        self.run_count_spin.setSpecialValueText("Auto-detect")
        pattern_layout.addRow("Base name:", self.pattern_edit)
        pattern_layout.addRow("Run count:", self.run_count_spin)
        self._pattern_group.setLayout(pattern_layout)
        self._pattern_group.setVisible(False)
        layout.addWidget(self._pattern_group)

        # Preview info
        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_source_changed(0)

    def _on_source_changed(self, idx: int):
        source_type = self.source_combo.currentData()
        is_multi = source_type == "multi"
        is_pattern = source_type == "pattern"

        self.multi_file_list.setVisible(is_multi)
        self._add_files_btn.setVisible(is_multi)
        self.file_path_edit.setVisible(not is_multi)
        self.browse_btn.setVisible(not is_multi)
        self._pattern_group.setVisible(is_pattern)
        self.preview_label.setText("")

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Raw File", "",
            "Raw files (*.raw *.qraw);;All files (*)"
        )
        if path:
            self.file_path_edit.setText(path)
            self._update_preview(path)

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Raw Files", "",
            "Raw files (*.raw *.qraw);;All files (*)"
        )
        if paths:
            for p in paths:
                self.multi_file_list.addItem(p)

    def _update_preview(self, file_path: str):
        """Parse file header and show step/grouping preview."""
        try:
            from pqwave.models.rawfile import RawFile, detect_naming_pattern
            raw = RawFile(file_path)
            steps = raw.step_count
            params = raw.step_param_names
            if steps > 0:
                lines = [f"Detected {steps} simulation steps"]
                if params:
                    lines.append(f"Parameter(s): {', '.join(params)}")
                self.preview_label.setText("\n".join(lines))
                return

            names = raw.get_trace_names()
            groups = detect_naming_pattern(names)
            if groups:
                lines = ["Detected run groups:"]
                for base, info in groups.items():
                    lines.append(
                        f"  {base}: {info['count']} runs "
                        f"({base}{min(info['indices'])}..{base}{max(info['indices'])})"
                    )
                self.preview_label.setText("\n".join(lines))
                if self.source_combo.currentData() == "pattern":
                    first_group = list(groups.keys())[0]
                    self.pattern_edit.setText(first_group)
            else:
                self.preview_label.setText(
                    "No steps or run groups detected.\n"
                    "Use 'Multiple files' mode or specify a pattern manually."
                )
        except Exception as e:
            self.preview_label.setText(f"Preview error: {e}")

    def _on_accept(self):
        source_type = self.source_combo.currentData()
        if source_type == "stepped":
            path = self.file_path_edit.text()
            if not path:
                QMessageBox.warning(self, "Error", "Please select a file.")
                return
            self._config = MCConfig(source_type="stepped", file_path=path)
        elif source_type == "multi":
            paths = [
                self.multi_file_list.item(i).text()
                for i in range(self.multi_file_list.count())
            ]
            if not paths:
                QMessageBox.warning(self, "Error", "Please add at least one file.")
                return
            self._config = MCConfig(source_type="multi", file_paths=paths)
        elif source_type == "pattern":
            path = self.file_path_edit.text()
            pattern = self.pattern_edit.text()
            rc = self.run_count_spin.value()
            if not path:
                QMessageBox.warning(self, "Error", "Please select a file.")
                return
            self._config = MCConfig(
                source_type="pattern",
                file_path=path,
                grouping_pattern=pattern if pattern else None,
                run_count_override=rc if rc > 0 else None,
            )
        self.accept()

    def get_config(self) -> Optional[MCConfig]:
        return self._config
