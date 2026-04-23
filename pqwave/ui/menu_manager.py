#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MenuManager - Creates and manages menus, toolbars, and their actions.

This module provides a class that handles the creation of the application's
menu bar, menus, toolbars, and status bar, centralizing UI element creation
and action management.
"""

from PyQt6.QtWidgets import (
    QMenuBar, QMenu, QToolBar, QStatusBar, QLabel, QStyle
)
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import Qt


class MenuManager:
    """Manages menus, toolbars, and status bar for the main window."""

    def __init__(self, parent, callbacks=None):
        """Initialize MenuManager.

        Args:
            parent: The parent QMainWindow
            callbacks: Dictionary mapping action names to callback functions.
                      Required keys: 'open_file', 'open_new_window', 'convert_raw_data',
                      'edit_trace_properties',
                      'show_settings', 'toggle_toolbar', 'toggle_statusbar', 'toggle_grids',
                      'zoom_in', 'zoom_out', 'zoom_to_fit', 'auto_range_x', 'auto_range_y',
                      'enable_zoom_box', 'zoom_in_toolbar', 'zoom_out_toolbar',
                      'zoom_to_fit_toolbar', 'auto_range_x_toolbar', 'auto_range_y_toolbar',
                      'zoom_box_toolbar', 'toggle_grids_toolbar', 'toggle_cross_hair',
                      'toggle_x_cursor_a', 'toggle_x_cursor_b',
                      'toggle_y_cursor_A', 'toggle_y_cursor_B'
        """
        self.parent = parent
        self.callbacks = callbacks or {}

        # Action references for external access
        self.actions = {}

        # Create menu bar
        self.menubar = QMenuBar(parent)
        self._create_menus()
        parent.setMenuBar(self.menubar)

        # Create toolbar
        self.toolbar = QToolBar("Main Toolbar", parent)
        parent.addToolBar(self.toolbar)
        self.toolbar.setVisible(True)
        self._create_toolbar()

        # Create status bar
        self.statusbar = QStatusBar(parent)
        parent.setStatusBar(self.statusbar)
        self._create_status_bar()

    def _create_menus(self):
        """Create menus and their actions."""
        # File menu
        file_menu = QMenu("File", self.parent)

        open_raw_action = QAction("Open Raw File", self.parent)
        open_raw_action.triggered.connect(self.callbacks.get('open_file', lambda: None))
        file_menu.addAction(open_raw_action)

        open_new_window_action = QAction("Open New Window", self.parent)
        open_new_window_action.triggered.connect(self.callbacks.get('open_new_window', lambda: None))
        file_menu.addAction(open_new_window_action)

        convert_raw_action = QAction("Convert Raw Data...", self.parent)
        convert_raw_action.triggered.connect(self.callbacks.get('convert_raw_data', lambda: None))
        file_menu.addAction(convert_raw_action)

        self.menubar.addMenu(file_menu)

        # Edit menu
        edit_menu = QMenu("Edit", self.parent)

        edit_properties_action = QAction("Edit Trace Properties", self.parent)
        edit_properties_action.triggered.connect(self.callbacks.get('edit_trace_properties', lambda: None))
        edit_menu.addAction(edit_properties_action)

        settings_action = QAction("Settings", self.parent)
        settings_action.triggered.connect(self.callbacks.get('show_settings', lambda: None))
        edit_menu.addAction(settings_action)

        self.menubar.addMenu(edit_menu)

        # View menu
        view_menu = QMenu("View", self.parent)

        # Toggle actions (checkable)
        self.toggle_toolbar_action = QAction("Toggle Toolbar", self.parent, checkable=True)
        self.toggle_toolbar_action.setChecked(True)
        self.toggle_toolbar_action.triggered.connect(self.callbacks.get('toggle_toolbar', lambda: None))
        view_menu.addAction(self.toggle_toolbar_action)
        self.actions['toggle_toolbar'] = self.toggle_toolbar_action

        self.toggle_statusbar_action = QAction("Toggle Status Bar", self.parent, checkable=True)
        self.toggle_statusbar_action.setChecked(True)
        self.toggle_statusbar_action.triggered.connect(self.callbacks.get('toggle_statusbar', lambda: None))
        view_menu.addAction(self.toggle_statusbar_action)
        self.actions['toggle_statusbar'] = self.toggle_statusbar_action

        self.toggle_grids_action = QAction("Toggle Grids", self.parent, checkable=True)
        self.toggle_grids_action.setChecked(True)
        self.toggle_grids_action.setShortcut(QKeySequence("Ctrl+G"))
        self.toggle_grids_action.triggered.connect(self.callbacks.get('toggle_grids', lambda: None))
        view_menu.addAction(self.toggle_grids_action)
        self.actions['toggle_grids'] = self.toggle_grids_action

        self.toggle_cross_hair_action = QAction("Toggle Cross-hair", self.parent, checkable=True)
        self.toggle_cross_hair_action.setChecked(False)
        self.toggle_cross_hair_action.triggered.connect(self.callbacks.get('toggle_cross_hair', lambda: None))
        view_menu.addAction(self.toggle_cross_hair_action)
        self.actions['toggle_cross_hair'] = self.toggle_cross_hair_action

        view_menu.addSeparator()

        # Individual X/Y cursor toggles (independent checkable items)
        self.toggle_x_cursor_a_action = QAction("X Cursor a", self.parent, checkable=True)
        self.toggle_x_cursor_a_action.triggered.connect(self.callbacks.get('toggle_x_cursor_a', lambda: None))
        view_menu.addAction(self.toggle_x_cursor_a_action)
        self.actions['x_cursor_a'] = self.toggle_x_cursor_a_action

        self.toggle_x_cursor_b_action = QAction("X Cursor b", self.parent, checkable=True)
        self.toggle_x_cursor_b_action.triggered.connect(self.callbacks.get('toggle_x_cursor_b', lambda: None))
        view_menu.addAction(self.toggle_x_cursor_b_action)
        self.actions['x_cursor_b'] = self.toggle_x_cursor_b_action

        self.toggle_y_cursor_A_action = QAction("Y Cursor A", self.parent, checkable=True)
        self.toggle_y_cursor_A_action.triggered.connect(self.callbacks.get('toggle_y_cursor_A', lambda: None))
        view_menu.addAction(self.toggle_y_cursor_A_action)
        self.actions['y_cursor_A'] = self.toggle_y_cursor_A_action

        self.toggle_y_cursor_B_action = QAction("Y Cursor B", self.parent, checkable=True)
        self.toggle_y_cursor_B_action.triggered.connect(self.callbacks.get('toggle_y_cursor_B', lambda: None))
        view_menu.addAction(self.toggle_y_cursor_B_action)
        self.actions['y_cursor_B'] = self.toggle_y_cursor_B_action

        view_menu.addSeparator()

        # Zoom actions
        self.zoom_in_action = QAction("Zoom In", self.parent)
        self.zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        self.zoom_in_action.triggered.connect(self.callbacks.get('zoom_in', lambda: None))
        view_menu.addAction(self.zoom_in_action)
        self.actions['zoom_in'] = self.zoom_in_action

        self.zoom_out_action = QAction("Zoom Out", self.parent)
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self.zoom_out_action.triggered.connect(self.callbacks.get('zoom_out', lambda: None))
        view_menu.addAction(self.zoom_out_action)
        self.actions['zoom_out'] = self.zoom_out_action

        self.zoom_to_fit_action = QAction("Zoom to Fit", self.parent)
        self.zoom_to_fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self.zoom_to_fit_action.triggered.connect(self.callbacks.get('zoom_to_fit', lambda: None))
        view_menu.addAction(self.zoom_to_fit_action)
        self.actions['zoom_to_fit'] = self.zoom_to_fit_action

        self.auto_range_x_action = QAction("Auto-range X-axis", self.parent)
        self.auto_range_x_action.triggered.connect(self.callbacks.get('auto_range_x', lambda: None))
        view_menu.addAction(self.auto_range_x_action)
        self.actions['auto_range_x'] = self.auto_range_x_action

        self.auto_range_y_action = QAction("Auto-range Y1 & Y2 axes", self.parent)
        self.auto_range_y_action.triggered.connect(self.callbacks.get('auto_range_y', lambda: None))
        view_menu.addAction(self.auto_range_y_action)
        self.actions['auto_range_y'] = self.auto_range_y_action

        self.zoom_box_action = QAction("Zoom Box", self.parent, checkable=True)
        self.zoom_box_action.setChecked(False)
        self.zoom_box_action.triggered.connect(self.callbacks.get('enable_zoom_box', lambda: None))
        view_menu.addAction(self.zoom_box_action)
        self.actions['zoom_box'] = self.zoom_box_action

        self.menubar.addMenu(view_menu)

    def _create_toolbar(self):
        """Create toolbar with actions."""
        style = self.parent.style()

        # Open File
        open_file_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Open File", self.parent)
        open_file_action.setToolTip("Open RAW file")
        open_file_action.triggered.connect(self.callbacks.get('open_file', lambda: None))
        self.toolbar.addAction(open_file_action)
        self.actions['open_file_toolbar'] = open_file_action

        # Open New Window
        open_new_window_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "Open New Window", self.parent)
        open_new_window_action.setToolTip("Open new window")
        open_new_window_action.triggered.connect(self.callbacks.get('open_new_window', lambda: None))
        self.toolbar.addAction(open_new_window_action)
        self.actions['open_new_window_toolbar'] = open_new_window_action

        self.toolbar.addSeparator()

        # Zoom In
        self.zoom_in_action_toolbar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp), "Zoom In", self.parent)
        self.zoom_in_action_toolbar.setToolTip("Zoom in (Ctrl++)")
        self.zoom_in_action_toolbar.triggered.connect(self.callbacks.get('zoom_in_toolbar', lambda: None))
        self.toolbar.addAction(self.zoom_in_action_toolbar)
        self.actions['zoom_in_toolbar'] = self.zoom_in_action_toolbar

        # Zoom Out
        self.zoom_out_action_toolbar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown), "Zoom Out", self.parent)
        self.zoom_out_action_toolbar.setToolTip("Zoom out (Ctrl+-)")
        self.zoom_out_action_toolbar.triggered.connect(self.callbacks.get('zoom_out_toolbar', lambda: None))
        self.toolbar.addAction(self.zoom_out_action_toolbar)
        self.actions['zoom_out_toolbar'] = self.zoom_out_action_toolbar

        # Zoom to Fit
        self.zoom_to_fit_action_toolbar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton), "Zoom to Fit", self.parent)
        self.zoom_to_fit_action_toolbar.setToolTip("Auto-range all axes (Ctrl+0)")
        self.zoom_to_fit_action_toolbar.triggered.connect(self.callbacks.get('zoom_to_fit_toolbar', lambda: None))
        self.toolbar.addAction(self.zoom_to_fit_action_toolbar)
        self.actions['zoom_to_fit_toolbar'] = self.zoom_to_fit_action_toolbar

        # Auto-range X-axis
        self.auto_range_x_action_toolbar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight), "Auto-range X-axis", self.parent)
        self.auto_range_x_action_toolbar.setToolTip("Auto-range X-axis")
        self.auto_range_x_action_toolbar.triggered.connect(self.callbacks.get('auto_range_x_toolbar', lambda: None))
        self.toolbar.addAction(self.auto_range_x_action_toolbar)
        self.actions['auto_range_x_toolbar'] = self.auto_range_x_action_toolbar

        # Auto-range Y axes
        self.auto_range_y_action_toolbar = QAction("Y", self.parent)
        self.auto_range_y_action_toolbar.setToolTip("Auto-range Y1 & Y2 axes")
        self.auto_range_y_action_toolbar.triggered.connect(self.callbacks.get('auto_range_y_toolbar', lambda: None))
        self.toolbar.addAction(self.auto_range_y_action_toolbar)
        self.actions['auto_range_y_toolbar'] = self.auto_range_y_action_toolbar

        # Zoom Box (checkable)
        self.zoom_box_action_toolbar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton), "Zoom Box", self.parent)
        self.zoom_box_action_toolbar.setToolTip("Rectangle zoom mode (toggle)")
        self.zoom_box_action_toolbar.setCheckable(True)
        self.zoom_box_action_toolbar.triggered.connect(self.callbacks.get('zoom_box_toolbar', lambda: None))
        self.toolbar.addAction(self.zoom_box_action_toolbar)
        self.actions['zoom_box_toolbar'] = self.zoom_box_action_toolbar

        # Toggle Grids (checkable)
        self.toggle_grids_action_toolbar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView), "Toggle Grids", self.parent)
        self.toggle_grids_action_toolbar.setToolTip("Toggle grid visibility (Ctrl+G)")
        self.toggle_grids_action_toolbar.setCheckable(True)
        self.toggle_grids_action_toolbar.setChecked(True)
        self.toggle_grids_action_toolbar.triggered.connect(self.callbacks.get('toggle_grids_toolbar', lambda: None))
        self.toolbar.addAction(self.toggle_grids_action_toolbar)
        self.actions['toggle_grids_toolbar'] = self.toggle_grids_action_toolbar

        # Toggle Cross-hair (checkable)
        self.toggle_cross_hair_action_toolbar = QAction("+", self.parent)
        self.toggle_cross_hair_action_toolbar.setToolTip("Toggle cross-hair cursor (click to place marks)")
        self.toggle_cross_hair_action_toolbar.setCheckable(True)
        self.toggle_cross_hair_action_toolbar.setChecked(False)
        self.toggle_cross_hair_action_toolbar.triggered.connect(self.callbacks.get('toggle_cross_hair', lambda: None))
        self.toolbar.addAction(self.toggle_cross_hair_action_toolbar)
        self.actions['toggle_cross_hair_toolbar'] = self.toggle_cross_hair_action_toolbar

        self.toolbar.addSeparator()

        # Individual X/Y cursor toggle buttons in toolbar
        self.toggle_x_cursor_a_toolbar = QAction("Xa", self.parent, checkable=True)
        self.toggle_x_cursor_a_toolbar.setToolTip("Toggle X cursor a")
        self.toggle_x_cursor_a_toolbar.triggered.connect(self.callbacks.get('toggle_x_cursor_a', lambda: None))
        self.toolbar.addAction(self.toggle_x_cursor_a_toolbar)
        self.actions['x_cursor_a_toolbar'] = self.toggle_x_cursor_a_toolbar

        self.toggle_x_cursor_b_toolbar = QAction("Xb", self.parent, checkable=True)
        self.toggle_x_cursor_b_toolbar.setToolTip("Toggle X cursor b")
        self.toggle_x_cursor_b_toolbar.triggered.connect(self.callbacks.get('toggle_x_cursor_b', lambda: None))
        self.toolbar.addAction(self.toggle_x_cursor_b_toolbar)
        self.actions['x_cursor_b_toolbar'] = self.toggle_x_cursor_b_toolbar

        self.toggle_y_cursor_A_toolbar = QAction("YA", self.parent, checkable=True)
        self.toggle_y_cursor_A_toolbar.setToolTip("Toggle Y cursor A")
        self.toggle_y_cursor_A_toolbar.triggered.connect(self.callbacks.get('toggle_y_cursor_A', lambda: None))
        self.toolbar.addAction(self.toggle_y_cursor_A_toolbar)
        self.actions['y_cursor_A_toolbar'] = self.toggle_y_cursor_A_toolbar

        self.toggle_y_cursor_B_toolbar = QAction("YB", self.parent, checkable=True)
        self.toggle_y_cursor_B_toolbar.setToolTip("Toggle Y cursor B")
        self.toggle_y_cursor_B_toolbar.triggered.connect(self.callbacks.get('toggle_y_cursor_B', lambda: None))
        self.toolbar.addAction(self.toggle_y_cursor_B_toolbar)
        self.actions['y_cursor_B_toolbar'] = self.toggle_y_cursor_B_toolbar

    def _create_status_bar(self):
        """Create status bar with labels."""
        self.coord_label = QLabel("X: -, Y1: -, Y2: -")
        self.cursor_status_label = QLabel("")
        self.dataset_label = QLabel("Dataset: -")
        self.statusbar.addPermanentWidget(self.coord_label)
        self.statusbar.addPermanentWidget(self.cursor_status_label)
        self.statusbar.addPermanentWidget(self.dataset_label)

    def update_coordinate_label(self, x, y1, y2):
        """Update coordinate display in status bar."""
        import math

        def format_value(val):
            if val is None:
                return "-"
            try:
                if math.isnan(val):
                    return "-"
                return f"{val:.6g}"
            except (TypeError, ValueError):
                return "-"

        x_str = format_value(x)
        y1_str = format_value(y1)
        y2_str = format_value(y2)
        self.coord_label.setText(f"X: {x_str}, Y1: {y1_str}, Y2: {y2_str}")

    def update_dataset_label(self, dataset_info):
        """Update dataset info in status bar."""
        self.dataset_label.setText(f"Dataset: {dataset_info}")

    def set_toolbar_visible(self, visible):
        """Show/hide toolbar."""
        self.toolbar.setVisible(visible)
        self.toggle_toolbar_action.setChecked(visible)

    def set_statusbar_visible(self, visible):
        """Show/hide status bar."""
        self.statusbar.setVisible(visible)
        self.toggle_statusbar_action.setChecked(visible)

    def set_grids_visible(self, visible):
        """Update grid toggle state."""
        self.toggle_grids_action.setChecked(visible)
        self.toggle_grids_action_toolbar.setChecked(visible)

    def set_cross_hair_visible(self, visible):
        """Update cross-hair toggle state."""
        self.toggle_cross_hair_action.setChecked(visible)
        self.toggle_cross_hair_action_toolbar.setChecked(visible)

    def set_x_cursor_a_checked(self, checked: bool) -> None:
        """Update X cursor a menu and toolbar checked state."""
        self.toggle_x_cursor_a_action.setChecked(checked)
        self.toggle_x_cursor_a_toolbar.setChecked(checked)

    def set_x_cursor_b_checked(self, checked: bool) -> None:
        """Update X cursor b menu and toolbar checked state."""
        self.toggle_x_cursor_b_action.setChecked(checked)
        self.toggle_x_cursor_b_toolbar.setChecked(checked)

    def set_y_cursor_A_checked(self, checked: bool) -> None:
        """Update Y cursor A menu and toolbar checked state."""
        self.toggle_y_cursor_A_action.setChecked(checked)
        self.toggle_y_cursor_A_toolbar.setChecked(checked)

    def set_y_cursor_B_checked(self, checked: bool) -> None:
        """Update Y cursor B menu and toolbar checked state."""
        self.toggle_y_cursor_B_action.setChecked(checked)
        self.toggle_y_cursor_B_toolbar.setChecked(checked)

    def update_cursor_status(self, positions: dict, deltas: dict) -> None:
        """Update cursor delta display in status bar.

        Args:
            positions: dict with keys xa, xb, yA, yB, y2
            deltas: dict with keys dx, dy1, dy2
        """
        import math

        def fmt(val):
            if val is None:
                return None
            try:
                if math.isnan(val):
                    return None
                return f"{val:.6g}"
            except (TypeError, ValueError):
                return None

        parts = []

        # X cursor section
        x_parts = []
        x1_s = fmt(positions.get('xa'))
        x2_s = fmt(positions.get('xb'))
        dx_s = fmt(deltas.get('dx'))
        if x1_s is not None:
            x_parts.append(f"Xa:{x1_s}")
        if x2_s is not None:
            x_parts.append(f"Xb:{x2_s}")
        if dx_s is not None:
            x_parts.append(f"ΔX:{dx_s}")
        if x_parts:
            parts.append(" | " + " ".join(x_parts))

        # Y cursor section
        y_parts = []
        ya_s = fmt(positions.get('yA'))
        yb_s = fmt(positions.get('yB'))
        dy1_s = fmt(deltas.get('dy1'))
        dy2_s = fmt(deltas.get('dy2'))
        if ya_s is not None:
            y_parts.append(f"YA:{ya_s}")
        if yb_s is not None:
            y_parts.append(f"YB:{yb_s}")
        if dy1_s is not None:
            y_parts.append(f"ΔY1:{dy1_s}")
        if dy2_s is not None:
            y_parts.append(f"ΔY2:{dy2_s}")
        if y_parts:
            parts.append(" | " + " ".join(y_parts))

        self.cursor_status_label.setText("".join(parts))