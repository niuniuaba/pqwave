#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MainWindow - Main application window orchestrating all UI components.

This module provides the MainWindow class that composes all modular UI components
(MenuManager, ControlPanel, PlotWidget, TraceManager, AxisManager) and integrates
them with the ApplicationState singleton.
"""

import sys
import traceback
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QDialog, QCheckBox, QDialogButtonBox, QLabel
)
from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtGui import QColor

from pqwave.models.state import ApplicationState, AxisId, ViewboxTheme
from pqwave.models.rawfile import RawFile
from pqwave.models.raw_converter import write_raw_file, FORMAT_CONFIG
from pqwave.models.dataset import Dataset
from pqwave.models.trace import AxisAssignment
from pqwave.ui.menu_manager import MenuManager
from pqwave.ui.control_panel import ControlPanel
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.trace_manager import TraceManager
from pqwave.ui.settings_widget import SettingsWidget
from pqwave.ui.axis_manager import AxisManager
from pqwave.ui.mark_panel import MarkPanel
from pqwave.utils.colors import ColorManager
from pqwave.logging_config import get_logger


logger = get_logger(__name__)

class MainWindow(QMainWindow):
    """Main application window orchestrating all UI components."""

    def __init__(self, initial_file=None):
        """
        Initialize MainWindow.

        Args:
            initial_file: Optional path to initial raw file to load
        """
        super().__init__()
        self.setWindowTitle("pqwave - SPICE Waveform Viewer")
        self.setGeometry(100, 100, 1200, 800)

        # Initialize application state singleton
        self.state = ApplicationState()

        # Store initial file for delayed loading
        self.initial_file = initial_file

        # Component references (will be initialized in _setup_ui)
        self.menu_manager = None
        self.plot_widget = None
        self.control_panel = None
        self.trace_manager = None
        self.axis_manager = None
        self.color_manager = None

        # Raw file reference
        self.raw_file = None

        # Zoom box state
        self.zoom_box_enabled = False

        # Cross-hair cursor state
        self.cross_hair_visible = False
        self.mark_panel = None

        # Setup UI
        self._setup_ui()

        # Connect signals
        self._connect_signals()

        # Flag to prevent double loading from timer
        self.initial_file_loaded = False

        # Load initial file if provided
        if self.initial_file:
            QTimer.singleShot(100, self._load_initial_file)

    def _setup_ui(self):
        """Create and arrange UI components."""
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Create color manager
        self.color_manager = ColorManager()

        # Create plot widget (with cursor support)
        self.plot_widget = PlotWidget()

        # Create legend (attached to plot widget)
        legend = self.plot_widget.addLegend()
        self.legend = legend

        # Create axis manager
        self.axis_manager = AxisManager(self.plot_widget, self.state)

        # Create trace manager
        self.trace_manager = TraceManager(
            plot_widget=self.plot_widget,
            legend=legend,
            application_state=self.state,
            color_manager=self.color_manager
        )

        # Create control panel
        self.control_panel = ControlPanel()

        # Create menu manager with callbacks
        callbacks = self._create_menu_callbacks()
        self.menu_manager = MenuManager(self, callbacks)

        # Add plot widget to layout (with stretch factor)
        main_layout.addWidget(self.plot_widget, 1)

        # Add control panel to layout
        main_layout.addWidget(self.control_panel)

        # Set layout
        central_widget.setLayout(main_layout)

        # Initialize log mode flags in trace manager
        self._update_trace_manager_log_modes()

    def _create_menu_callbacks(self):
        """Create callback dictionary for menu manager."""
        return {
            'open_file': self.open_file,
            'open_new_window': self.open_new_window,
            'convert_raw_data': self.convert_raw_data,
            'edit_trace_properties': self.edit_trace_properties,
            'show_settings': self.show_settings,
            'toggle_toolbar': self.toggle_toolbar,
            'toggle_statusbar': self.toggle_statusbar,
            'toggle_grids': self.toggle_grids,
            'zoom_in': self.zoom_in,
            'zoom_out': self.zoom_out,
            'zoom_to_fit': self.zoom_to_fit,
            'auto_range_x': self.auto_range_x,
            'auto_range_y': self.auto_range_y,
            'enable_zoom_box': self.enable_zoom_box,
            'zoom_in_toolbar': self.zoom_in,
            'zoom_out_toolbar': self.zoom_out,
            'zoom_to_fit_toolbar': self.zoom_to_fit,
            'auto_range_x_toolbar': self.auto_range_x,
            'auto_range_y_toolbar': self.auto_range_y,
            'zoom_box_toolbar': self.enable_zoom_box,
            'toggle_grids_toolbar': self.toggle_grids,
            'toggle_cross_hair': self.toggle_cross_hair
        }

    def _connect_signals(self):
        """Connect signals between components."""
        # Connect control panel signals
        self.control_panel.dataset_changed.connect(self._on_dataset_changed)
        self.control_panel.vector_selected.connect(self._on_vector_selected)
        self.control_panel.add_trace_to_axis.connect(self._on_add_trace_to_axis)
        self.control_panel.expression_changed.connect(self._on_expression_changed)

        # Connect plot widget signals
        self.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.plot_widget.mouse_left.connect(self._on_mouse_left)
        self.plot_widget.cursor_x_changed.connect(self._on_cursor_x_changed)
        self.plot_widget.cursor_y1_changed.connect(self._on_cursor_y1_changed)
        self.plot_widget.cursor_y2_changed.connect(self._on_cursor_y2_changed)
        self.plot_widget.axis_log_mode_changed.connect(self._on_axis_log_mode_changed)
        self.plot_widget.mark_clicked.connect(self._on_mark_clicked)

        # Connect axis manager signals
        self.axis_manager.axis_log_mode_changed.connect(self._on_axis_log_mode_changed_from_manager)
        self.axis_manager.axis_range_changed.connect(self._on_axis_range_changed)
        self.axis_manager.axis_label_changed.connect(self._on_axis_label_changed)

    def _connect_mark_panel(self):
        """Connect mark panel signals (called when panel is created)."""
        if self.mark_panel is not None:
            self.mark_panel.mark_deleted_last.connect(self._on_mark_deleted_last)
            self.mark_panel.window_closed.connect(self._on_mark_panel_closed)

    def _update_trace_manager_log_modes(self):
        """Update trace manager with current log mode settings."""
        x_config = self.state.get_axis_config(AxisId.X)
        y1_config = self.state.get_axis_config(AxisId.Y1)
        y2_config = self.state.get_axis_config(AxisId.Y2)

        self.trace_manager.set_log_modes(
            x_log=x_config.log_mode,
            y1_log=y1_config.log_mode,
            y2_log=y2_config.log_mode
        )

    # Menu callbacks

    def open_file(self):
        """Open a raw file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Raw File", "", "Raw Files (*.raw);;All Files (*)"
        )
        if filename:
            self._load_raw_file(filename)

    def open_new_window(self):
        """Open a new MainWindow instance."""
        new_window = MainWindow()
        new_window.show()

    def convert_raw_data(self):
        """Convert currently loaded raw data to another format."""
        if not self.raw_file or not self.raw_file.datasets:
            QMessageBox.warning(
                self, "No Data",
                "No raw data loaded. Open a raw file first before converting."
            )
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QPushButton

        dataset = self.raw_file.datasets[0]  # Use first dataset
        title = dataset.get('title', 'pqwave conversion')
        date = dataset.get('date', '')
        plotname = dataset.get('plotname', '')
        flags = dataset.get('flags', '')
        variables = dataset.get('variables', [])
        data = dataset.get('data', np.array([]))
        is_ac_or_complex = dataset.get('_is_ac_or_complex', False)

        # Detect source format from spicelib's dialect detection
        if self.raw_file.raw_data:
            detected = self.raw_file.raw_data.dialect
            if detected in ('ltspice', 'qspice', 'ngspice', 'xyce'):
                src_format = detected
            else:
                # Fallback to extension-based detection
                src_file = self.raw_file.filename.lower()
                if src_file.endswith('.qraw'):
                    src_format = 'qspice'
                else:
                    src_format = 'ltspice'
        else:
            src_format = 'ltspice'

        # Show format selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Convert Raw Data")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout()

        info_label = QLabel(
            f"Source: {src_format.upper()}\n"
            f"Variables: {len(variables)}\n"
            f"Points: {data.shape[0] if data.ndim > 0 else 0}"
        )
        layout.addWidget(info_label)

        layout.addWidget(QLabel("Target format:"))

        format_group = []
        for fmt_key, fmt_config in FORMAT_CONFIG.items():
            label = f"{fmt_key.upper()} ({fmt_config['extension']})"
            rb = QRadioButton(label)
            if fmt_key == src_format:
                rb.setEnabled(False)  # Disable current format
            else:
                rb.setChecked(True)  # Default to first non-source format
            format_group.append((fmt_key, rb))
            layout.addWidget(rb)

        # Button box
        button_layout = QHBoxLayout()
        convert_btn = QPushButton("Convert")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(convert_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        def do_convert():
            target_fmt = None
            for fmt_key, rb in format_group:
                if rb.isChecked():
                    target_fmt = fmt_key
                    break

            if target_fmt is None:
                QMessageBox.warning(dialog, "Error", "Please select a target format.")
                return

            dialog.accept()

            # Show save file dialog
            ext = FORMAT_CONFIG[target_fmt]['extension']
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Converted Raw File",
                "",
                f"Raw Files (*{ext});;All Files (*)"
            )

            if not save_path:
                return

            try:
                write_raw_file(
                    output_path=save_path,
                    title=title,
                    date=date,
                    plotname=plotname,
                    flags=flags,
                    variables=variables,
                    data=data,
                    target_format=target_fmt,
                    is_ac_or_complex=is_ac_or_complex,
                )
                QMessageBox.information(
                    self, "Conversion Successful",
                    f"Converted to {target_fmt.upper()} format:\n{save_path}"
                )
                logger.info(f"Raw data converted to {save_path} ({target_fmt})")
            except Exception as e:
                logger.exception(f"Conversion failed: {e}")
                QMessageBox.critical(
                    self, "Conversion Failed",
                    f"Failed to convert raw data:\n{e}"
                )

        convert_btn.clicked.connect(do_convert)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def edit_trace_properties(self):
        """Edit trace properties (alias, color, line width)"""
        logger.debug(f"edit_trace_properties called, traces count: {len(self.trace_manager.traces)}")
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLineEdit, QPushButton, QHBoxLayout, QLabel, QComboBox

        # Get traces from trace manager
        traces = self.trace_manager.traces
        if not traces:
            QMessageBox.information(self, "No Traces", "No traces to edit.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Trace Properties")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # Create list widget for traces
        list_widget = QListWidget()
        for i, (var, plot_item, y_axis) in enumerate(traces):
            list_widget.addItem(f"{i+1}. {var} @ {y_axis}")

        layout.addWidget(list_widget)

        # Create alias edit
        alias_layout = QHBoxLayout()
        alias_label = QLabel("Alias:")
        self.alias_edit = QLineEdit()
        alias_layout.addWidget(alias_label)
        alias_layout.addWidget(self.alias_edit)
        layout.addLayout(alias_layout)

        # Create color combo
        color_layout = QHBoxLayout()
        color_label = QLabel("Color:")
        self.color_combo = QComboBox()
        # Add color options
        colors = [
            ("Default (auto)", None),
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
            ("Yellow", (255, 255, 0)),
            ("Magenta", (255, 0, 255)),
            ("Cyan", (0, 255, 255)),
            ("Orange", (255, 165, 0)),
            ("Purple", (128, 0, 128)),
            ("Brown", (165, 42, 42))
        ]
        for color_name, color_value in colors:
            self.color_combo.addItem(color_name, color_value)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_combo)
        layout.addLayout(color_layout)

        # Create line width combo
        width_layout = QHBoxLayout()
        width_label = QLabel("Line width:")
        self.width_combo = QComboBox()
        # Add line width options
        widths = [1, 2, 3, 4, 5]
        for width in widths:
            self.width_combo.addItem(str(width), width)
        width_layout.addWidget(width_label)
        width_layout.addWidget(self.width_combo)
        layout.addLayout(width_layout)

        # Connect list selection change to update all fields
        list_widget.currentRowChanged.connect(lambda row: self._update_trace_properties(row, list_widget))

        # Create buttons
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(lambda: self._apply_trace_properties(list_widget.currentRow(), list_widget))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        # Select first trace if available
        if traces:
            list_widget.setCurrentRow(0)
            self._update_trace_properties(0, list_widget)

        dialog.exec()

    def _update_trace_properties(self, row, list_widget):
        """Update trace properties fields with current trace values"""
        if 0 <= row < len(self.trace_manager.traces):
            var, plot_item, y_axis = self.trace_manager.traces[row]
            # Update alias field
            self.alias_edit.setText(var)

            # Update color combo
            current_color = plot_item.opts['pen'].color()
            current_rgb = (current_color.red(), current_color.green(), current_color.blue())

            # Find matching color in combo
            color_index = 0  # Default to "Default (auto)"
            for i in range(self.color_combo.count()):
                color_value = self.color_combo.itemData(i)
                if color_value == current_rgb:
                    color_index = i
                    break
            self.color_combo.setCurrentIndex(color_index)

            # Update line width combo
            current_width = plot_item.opts['pen'].width()
            width_index = 0  # Default to 1
            for i in range(self.width_combo.count()):
                width_value = self.width_combo.itemData(i)
                if width_value == current_width:
                    width_index = i
                    break
            self.width_combo.setCurrentIndex(width_index)

    def _apply_trace_properties(self, row, list_widget):
        """Apply trace properties (alias, color, line width)"""

        if 0 <= row < len(self.trace_manager.traces):
            var, plot_item, y_axis = self.trace_manager.traces[row]

            # Get new values
            new_alias = self.alias_edit.text().strip()
            new_color = self.color_combo.currentData()
            new_width = self.width_combo.currentData()

            # Find matching Trace object in state
            trace_obj = None
            for trace in self.state.traces:
                if trace.name == var:
                    trace_obj = trace
                    break

            # Update alias if provided
            if new_alias and new_alias != var:
                # Update plot item name
                plot_item.opts['name'] = new_alias
                # Update trace manager traces list
                self.trace_manager.traces[row] = (new_alias, plot_item, y_axis)
                # Update Trace object name if found
                if trace_obj:
                    trace_obj.name = new_alias
                # Update list widget display
                list_widget.item(row).setText(f"{row+1}. {new_alias} @ {y_axis}")

            # Update color if not None (None means "Default (auto)")
            if new_color is not None:
                qcolor = QColor(*new_color)
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=qcolor, width=pen.width())
                plot_item.setPen(new_pen)
                # Update Trace object color if found
                if trace_obj:
                    trace_obj.color = new_color

            # Update line width
            if new_width:
                pen = plot_item.opts['pen']
                new_pen = pg.mkPen(color=pen.color(), width=new_width)
                plot_item.setPen(new_pen)
                # Update Trace object line width if found
                if trace_obj:
                    trace_obj.line_width = new_width

            # Refresh legend - trace manager should handle this
            # We'll call trace manager's method to update legend for this trace
            self._refresh_legend_for_trace(row, new_alias if new_alias else var, y_axis)

    def _refresh_legend_for_trace(self, trace_idx, trace_name, y_axis):
        """Refresh legend entry for a specific trace"""
        # The legend is managed by trace manager, but we need to update the legend item.
        # Since trace manager's legend items are added with format "{name} @ {y_axis}",
        # we can clear and re-add all legend items, or find and update the specific one.
        # For simplicity, we'll clear and re-add all legend items.
        legend = self.trace_manager.legend
        if legend:
            legend.clear()
            # Re-add all traces to legend
            for i, (var, plot_item, axis) in enumerate(self.trace_manager.traces):
                legend_name = f"{var} @ {axis}"
                legend.addItem(plot_item, legend_name)

    def show_settings(self):
        """Show application settings widget."""
        # Create settings widget if it doesn't exist or was closed
        if not hasattr(self, '_settings_widget') or self._settings_widget is None:
            self._settings_widget = SettingsWidget(
                axis_manager=self.axis_manager,
                application_state=self.state,
                parent=self
            )
            # Connect signals
            self._settings_widget.plot_title_changed.connect(self._on_plot_title_changed)
            self._settings_widget.viewbox_theme_changed.connect(self._on_viewbox_theme_changed)
            self._settings_widget.destroyed.connect(lambda: setattr(self, '_settings_widget', None))

        # Show and raise the widget
        self._settings_widget.show()
        self._settings_widget.raise_()
        self._settings_widget.activateWindow()

    def _on_plot_title_changed(self, title: str):
        """Handle plot title changes from settings widget."""
        # Update plot widget title
        self.plot_widget.set_plot_title(title)

    def _on_viewbox_theme_changed(self, theme: ViewboxTheme) -> None:
        """Handle viewbox theme changes from settings widget."""
        self.plot_widget.set_viewbox_theme(theme)

    def toggle_toolbar(self):
        """Toggle toolbar visibility."""
        self.set_toolbar_visible(not self.menu_manager.toolbar.isVisible())

    def toggle_statusbar(self):
        """Toggle status bar visibility."""
        self.set_statusbar_visible(not self.menu_manager.statusbar.isVisible())

    def toggle_grids(self):
        """Toggle grid visibility."""
        visible = self.axis_manager.get_grid_visible()
        self.axis_manager.set_grid_visible(not visible)

        # Update menu manager toggle state
        self.menu_manager.set_grids_visible(not visible)

    def set_toolbar_visible(self, visible):
        """Set toolbar visibility and update state."""
        self.menu_manager.set_toolbar_visible(visible)
        self.state.toolbar_visible = visible

    def set_statusbar_visible(self, visible):
        """Set status bar visibility and update state."""
        self.menu_manager.set_statusbar_visible(visible)
        self.state.status_bar_visible = visible

    def set_legend_visible(self, visible):
        """Set legend visibility and update state."""
        if self.legend:
            self.legend.setVisible(visible)
        self.state.legend_visible = visible

    def zoom_in(self):
        """Zoom in."""
        if self.plot_widget and self.plot_widget.plotItem:
            self.plot_widget.plotItem.vb.scaleBy(s=(0.8, 0.8))

    def zoom_out(self):
        """Zoom out."""
        if self.plot_widget and self.plot_widget.plotItem:
            self.plot_widget.plotItem.vb.scaleBy(s=(1.25, 1.25))

    def zoom_to_fit(self):
        """Auto-range all axes."""
        self.axis_manager.auto_range_axis(AxisId.X)
        self.axis_manager.auto_range_axis(AxisId.Y1)
        self.axis_manager.auto_range_axis(AxisId.Y2)

    def auto_range_x(self):
        """Auto-range X-axis."""
        self.axis_manager.auto_range_axis(AxisId.X)

    def auto_range_y(self):
        """Auto-range Y axes."""
        self.axis_manager.auto_range_axis(AxisId.Y1)
        self.axis_manager.auto_range_axis(AxisId.Y2)

    def enable_zoom_box(self):
        """Enable/disable zoom box mode."""
        # Toggle zoom box state
        self.zoom_box_enabled = not self.zoom_box_enabled

        # Update plot widget
        if self.plot_widget:
            self.plot_widget.enable_zoom_box(self.zoom_box_enabled)

        # Synchronize menu and toolbar actions
        if self.menu_manager:
            self.menu_manager.actions['zoom_box'].setChecked(self.zoom_box_enabled)
            self.menu_manager.actions['zoom_box_toolbar'].setChecked(self.zoom_box_enabled)

    # Cross-hair cursor and marks

    def toggle_cross_hair(self):
        """Toggle cross-hair cursor ON/OFF.

        When turning ON: shows cross-hair and opens the mark data panel.
        When turning OFF: hides cross-hair, clears all marks, closes mark panel.
        """
        self.cross_hair_visible = not self.cross_hair_visible

        # Update plot widget
        self.plot_widget.set_cross_hair_visible(self.cross_hair_visible)

        # Update menu and toolbar state
        if self.menu_manager:
            self.menu_manager.set_cross_hair_visible(self.cross_hair_visible)

        if self.cross_hair_visible:
            self._open_mark_panel()
        else:
            self._close_mark_panel()

    def _open_mark_panel(self):
        """Create and show the mark data panel."""
        if self.mark_panel is None:
            self.mark_panel = MarkPanel(parent=self)
            self._connect_mark_panel()
        self.mark_panel.clear_all_marks()
        self.mark_panel.show()
        self.mark_panel.raise_()
        self.mark_panel.activateWindow()

    def _close_mark_panel(self):
        """Close the mark panel and clear all marks."""
        self.plot_widget.clear_marks()
        if self.mark_panel is not None:
            self.mark_panel.close()
            self.mark_panel = None

    @pyqtSlot(float, float, float, float, float)
    def _on_mark_clicked(self, x_vb, y1_vb, x_linear, y1_linear, y2_linear):
        """Handle mark placement from plot widget click.

        Args:
            x_vb, y1_vb: Viewbox coordinates (for mark rendering in plot space)
            x_linear, y1_linear, y2_linear: Linear display values (for data panel)
        """
        self.plot_widget.add_mark_at_position(x_vb, y1_vb)
        if self.mark_panel is not None:
            # Re-show panel if user had closed it via window close button
            self.mark_panel.show()
            self.mark_panel.raise_()
            self.mark_panel.activateWindow()
            self.mark_panel.add_mark(x_linear, y1_linear, y2_linear)

    @pyqtSlot()
    def _on_mark_panel_closed(self):
        """Handle mark panel window close button — hide without destroying."""
        if self.mark_panel is not None:
            self.mark_panel.hide()

    @pyqtSlot()
    def _on_mark_deleted_last(self):
        """Handle mark deletion from mark panel button."""
        self.plot_widget.remove_last_mark()

    # Raw file handling

    def _load_raw_file(self, filename):
        """Load raw file and update UI."""
        try:
            # 1. Clear existing traces from plot widget BEFORE replacing raw_file.
            #    This ensures Qt objects don't hold references to old data when
            #    the old RawFile is garbage-collected and its temp files deleted.
            self.trace_manager.clear_traces()
            self.trace_manager.set_raw_file(None)

            # 2. Parse the new file (does NOT touch self.raw_file yet)
            new_raw_file = RawFile(filename)

            # 3. Clear application state (releases old datasets)
            self.state.clear_datasets()

            # 4. Now safe to replace self.raw_file — old one has no remaining refs
            self.raw_file = new_raw_file

            # 5. Populate UI with new data
            for i in range(len(self.raw_file.datasets)):
                dataset = Dataset(self.raw_file, i)
                self.state.add_dataset(dataset)

            # Set current dataset to first one
            if self.state.datasets:
                self.state.current_dataset_idx = 0
                # Set current X variable to first variable
                var_names = self.raw_file.get_variable_names(0)
                if var_names:
                    self.state.current_x_var = var_names[0]
                    logger.info(f"Auto-set X variable to: {self.state.current_x_var}")
                    # Update X-axis label
                    self.axis_manager.set_axis_label(AxisId.X, self.state.current_x_var)

            # Update control panel
            self._update_dataset_combo()
            self._update_variable_combo()
            self.control_panel.clear_expression()  # Clear trace expression for new file

            # Set raw file reference in trace manager
            self.trace_manager.set_raw_file(self.raw_file)

            # Update trace manager with current log mode settings from state
            self._update_trace_manager_log_modes()

            # Auto-range axes
            self.auto_range_x()
            self.auto_range_y()

            # Update window title
            self.setWindowTitle(f"pqwave - {filename}")

            # Update status bar dataset label
            self._update_dataset_label()

            logger.info(f"Successfully loaded: {filename}")

        except FileNotFoundError as e:
            self._show_error("File not found", f"File not found: {filename}\n\n{e}")
        except Exception as e:
            logger.exception(f"Error opening file: {filename}")
            error_msg = str(e)
            if "Invalid RAW file" in error_msg:
                self._show_error("Invalid RAW file", f"Invalid RAW file format: {filename}\n\n{error_msg}")
            else:
                self._show_error("Error opening file", f"Error opening file: {filename}\n\n{error_msg}")

    def _load_initial_file(self):
        """Load the initial file provided via command line."""
        if self.initial_file_loaded:
            return
        if self.initial_file:
            logger.info(f"Loading initial file: {self.initial_file}")
            self._load_raw_file(self.initial_file)
            self.initial_file_loaded = True

    def _update_dataset_combo(self):
        """Update dataset combo box in control panel."""
        if self.raw_file:
            datasets = []
            for i, dataset in enumerate(self.raw_file.datasets):
                plotname = dataset.get('plotname', f'Dataset {i+1}')
                datasets.append(f"Dataset {i+1}: {plotname}")
            self.control_panel.set_datasets(datasets)

    def _update_variable_combo(self):
        """Update variable combo box in control panel."""
        if self.raw_file and self.state.current_dataset_idx is not None:
            var_names = self.raw_file.get_variable_names(self.state.current_dataset_idx)
            self.control_panel.set_variables(var_names)

    def _update_dataset_label(self):
        """Update dataset label in status bar."""
        if self.raw_file and self.raw_file.datasets:
            total_datasets = len(self.raw_file.datasets)
            current_dataset = self.state.current_dataset_idx + 1
            self.menu_manager.update_dataset_label(f"{current_dataset}/{total_datasets}")
        else:
            self.menu_manager.update_dataset_label("-")

    # Signal handlers

    @pyqtSlot(int)
    def _on_dataset_changed(self, index):
        """Handle dataset selection change."""
        self.state.current_dataset_idx = index
        self.trace_manager.set_current_dataset(index)
        self._update_variable_combo()
        self._update_dataset_label()
        # Clear trace expression as previous expression may not be valid for new dataset
        self.control_panel.clear_expression()

        # TODO: Update traces for new dataset

    @pyqtSlot(str)
    def _on_vector_selected(self, vector):
        """Handle vector selection."""
        # Add selected vector to trace expression, avoiding duplicates
        if not vector:
            return
        current_text = self.control_panel.trace_expr.text()
        if current_text:
            # Split by whitespace to check if vector already present
            parts = current_text.split()
            if vector in parts:
                # Vector already in expression, do nothing
                return
            new_text = f"{current_text} {vector}"
        else:
            new_text = vector
        self.control_panel.trace_expr.setText(new_text)

    @pyqtSlot(str)
    def _on_add_trace_to_axis(self, axis):
        """Handle add trace to axis button click."""
        expression = self.control_panel.trace_expr.text().strip()
        if not expression:
            QMessageBox.warning(self, "No Expression", "Please enter an expression first.")
            return

        if axis == "X":
            # X button sets X-axis variable
            # For simplicity, treat whole expression as variable name
            x_var = expression.strip()
            # Validate it's a single variable (no spaces)
            if ' ' in x_var:
                QMessageBox.warning(self, "Invalid X-axis", "X-axis can only have one variable/expression.")
                return

            # Store X-axis variable
            self.state.current_x_var = x_var

            # Update X-axis label
            self.axis_manager.set_axis_label(AxisId.X, x_var)

            # Auto-range X-axis based on new variable
            if self.raw_file and self.state.current_dataset_idx is not None:
                x_data = self.raw_file.get_variable_data(x_var, self.state.current_dataset_idx)
                if x_data is not None:
                    self.axis_manager.auto_range_x_from_data(x_data, x_var)

            # Clear expression after successful addition
            self.control_panel.trace_expr.clear()
            logger.info(f"Set X-axis variable to: {x_var}")

        elif axis in ["Y1", "Y2"]:
            # Y1/Y2 buttons add traces
            # Get current X-axis variable
            x_var = self._get_current_x_var()
            if not x_var:
                QMessageBox.warning(self, "No X-axis", "Please select an X-axis variable.")
                return

            # Map axis string to AxisAssignment
            if axis == "Y1":
                y_axis = AxisAssignment.Y1
            else:  # Y2
                y_axis = AxisAssignment.Y2

            # Add trace
            trace = self.trace_manager.add_trace(expression, x_var, y_axis)
            if trace:
                logger.info(f"Added trace: {trace.name} to {y_axis.value}")
                # Clear expression after successful addition
                self.control_panel.trace_expr.clear()
            else:
                QMessageBox.warning(self, "Error", f"Failed to add trace for expression: {expression}")
        else:
            logger.warning(f"Unknown axis: {axis}")

    @pyqtSlot(str)
    def _on_expression_changed(self, expression):
        """Handle trace expression text change."""
        # Nothing to do here for now
        pass

    @pyqtSlot(float, float, float)
    def _on_mouse_moved(self, x, y1, y2):
        """Handle mouse movement in plot."""
        self.menu_manager.update_coordinate_label(x, y1, y2)

    @pyqtSlot()
    def _on_mouse_left(self):
        """Handle mouse leaving plot."""
        self.menu_manager.update_coordinate_label(None, None, None)

    @pyqtSlot(float)
    def _on_cursor_x_changed(self, value):
        """Handle X cursor position change."""
        # TODO: Update cursor display
        pass

    @pyqtSlot(float)
    def _on_cursor_y1_changed(self, value):
        """Handle Y1 cursor position change."""
        # TODO: Update cursor display
        pass

    @pyqtSlot(float)
    def _on_cursor_y2_changed(self, value):
        """Handle Y2 cursor position change."""
        # TODO: Update cursor display
        pass

    @pyqtSlot(str, bool)
    def _on_axis_log_mode_changed(self, orientation, log_mode):
        """Handle axis log mode change from plot widget."""
        # This signal comes from plot widget's LogAxisItem
        # AxisManager should already handle this via its connection
        # We just need to update trace manager
        self._update_trace_manager_log_modes()

        # Update traces for new log mode
        self.trace_manager.update_traces_for_log_mode()

    @pyqtSlot(str, bool)
    def _on_axis_log_mode_changed_from_manager(self, axis_id, log_mode):
        """Handle axis log mode change from axis manager."""
        # Update trace manager
        self._update_trace_manager_log_modes()

        # Update traces for new log mode
        self.trace_manager.update_traces_for_log_mode()

    @pyqtSlot(str, float, float)
    def _on_axis_range_changed(self, axis_id, min_val, max_val):
        """Handle axis range change."""
        # TODO: Update range display if needed
        pass

    @pyqtSlot(str, str)
    def _on_axis_label_changed(self, axis_id, label):
        """Handle axis label change."""
        # TODO: Update label display if needed
        pass

    # Helper methods

    def _get_current_x_var(self):
        """Get current X-axis variable name."""
        # Return stored X variable if set
        if self.state.current_x_var:
            return self.state.current_x_var

        # Otherwise return first variable if available
        if self.raw_file and self.state.current_dataset_idx is not None:
            var_names = self.raw_file.get_variable_names(self.state.current_dataset_idx)
            if var_names:
                return var_names[0]
        return None

    def _show_error(self, title, message):
        """Show error message dialog."""
        logger.error(f"{title}: {message}")
        QMessageBox.warning(self, title, message)

    # Public API for testing

    def get_plot_widget(self):
        """Get plot widget reference (for testing)."""
        return self.plot_widget

    def get_control_panel(self):
        """Get control panel reference (for testing)."""
        return self.control_panel

    def get_trace_manager(self):
        """Get trace manager reference (for testing)."""
        return self.trace_manager

    def get_axis_manager(self):
        """Get axis manager reference (for testing)."""
        return self.axis_manager


if __name__ == "__main__":
    # Simple test runner
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())