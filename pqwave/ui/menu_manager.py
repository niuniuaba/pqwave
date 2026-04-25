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
from PyQt6.QtGui import QAction, QKeySequence, QIcon
from PyQt6.QtCore import Qt


class MenuManager:
    """Manages menus, toolbars, and status bar for the main window."""

    def __init__(self, parent, callbacks=None, keybinding_manager=None):
        """Initialize MenuManager.

        Args:
            parent: The parent QMainWindow
            callbacks: Dictionary mapping action names to callback functions.
                      Required keys: 'open_file', 'open_new_window', 'save_current_state', 'convert_raw_data',
                      'edit_trace_properties',
                      'show_settings', 'toggle_toolbar', 'toggle_statusbar', 'toggle_grids',
                      'zoom_in', 'zoom_out', 'zoom_to_fit', 'auto_range_x', 'auto_range_y',
                      'enable_zoom_box', 'zoom_in_toolbar', 'zoom_out_toolbar',
                      'zoom_to_fit_toolbar', 'auto_range_x_toolbar', 'auto_range_y_toolbar',
                      'zoom_box_toolbar', 'toggle_grids_toolbar', 'toggle_cross_hair',
                      'toggle_x_cursor_a', 'toggle_x_cursor_b',
                      'toggle_y_cursor_A', 'toggle_y_cursor_B',
                      'show_keybindings'
            keybinding_manager: Optional KeyBindingManager instance.
        """
        self.parent = parent
        self.callbacks = callbacks or {}
        self.keybinding_manager = keybinding_manager

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

    def _set_action_shortcut(self, action, action_name):
        """Set a QAction's shortcut from the keybinding manager, if available.

        Only sets shortcuts with a Ctrl modifier (or other modifiers) — skips
        bare single-key and arrow-key sequences to prevent double-fire when
        the same shortcut is also installed via QShortcut on the plot widget.
        """
        if self.keybinding_manager is not None:
            seq = self.keybinding_manager.get_sequence(action_name)
            if not seq:
                return
            # Skip bare letter keys and arrow keys — they are installed
            # as WidgetWithChildrenShortcut on the plot area instead.
            if seq in ('A', 'B', 'Z', 'F', '+', 'Left', 'Right', 'Up', 'Down',
                       'Shift+A', 'Shift+B'):
                return
            if len(seq) == 1 and seq.isalpha():
                return
            action.setShortcut(QKeySequence(seq))

    def _create_menus(self):
        """Create menus and their actions."""
        # File menu
        file_menu = QMenu("File", self.parent)

        save_current_state_action = QAction("Save Current State", self.parent)
        save_current_state_action.triggered.connect(self.callbacks.get('save_current_state', lambda: None))
        self._set_action_shortcut(save_current_state_action, 'save_current_state')
        file_menu.addAction(save_current_state_action)

        open_raw_action = QAction("Open Raw File", self.parent)
        open_raw_action.triggered.connect(self.callbacks.get('open_file', lambda: None))
        self._set_action_shortcut(open_raw_action, 'open_file')
        file_menu.addAction(open_raw_action)

        open_new_window_action = QAction("Open New Window", self.parent)
        open_new_window_action.triggered.connect(self.callbacks.get('open_new_window', lambda: None))
        self._set_action_shortcut(open_new_window_action, 'open_new_window')
        file_menu.addAction(open_new_window_action)

        convert_raw_action = QAction("Convert Raw Data...", self.parent)
        convert_raw_action.triggered.connect(self.callbacks.get('convert_raw_data', lambda: None))
        file_menu.addAction(convert_raw_action)

        self.menubar.addMenu(file_menu)

        # Edit menu
        edit_menu = QMenu("Edit", self.parent)

        edit_properties_action = QAction("Edit Trace Properties", self.parent)
        edit_properties_action.triggered.connect(self.callbacks.get('edit_trace_properties', lambda: None))
        self._set_action_shortcut(edit_properties_action, 'edit_trace_properties')
        edit_menu.addAction(edit_properties_action)

        settings_action = QAction("Settings", self.parent)
        settings_action.triggered.connect(self.callbacks.get('show_settings', lambda: None))
        self._set_action_shortcut(settings_action, 'show_settings')
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
        self._set_action_shortcut(self.toggle_grids_action, 'toggle_grids')
        self.toggle_grids_action.triggered.connect(self.callbacks.get('toggle_grids', lambda: None))
        view_menu.addAction(self.toggle_grids_action)
        self.actions['toggle_grids'] = self.toggle_grids_action

        self.toggle_cross_hair_action = QAction("Toggle Cross-hair", self.parent, checkable=True)
        self.toggle_cross_hair_action.setChecked(False)
        self._set_action_shortcut(self.toggle_cross_hair_action, 'toggle_cross_hair')
        self.toggle_cross_hair_action.triggered.connect(self.callbacks.get('toggle_cross_hair', lambda: None))
        view_menu.addAction(self.toggle_cross_hair_action)
        self.actions['toggle_cross_hair'] = self.toggle_cross_hair_action

        view_menu.addSeparator()

        # Individual X/Y cursor toggles (independent checkable items)
        self.toggle_x_cursor_a_action = QAction("X Cursor a", self.parent, checkable=True)
        self._set_action_shortcut(self.toggle_x_cursor_a_action, 'toggle_xa_cursor')
        self.toggle_x_cursor_a_action.triggered.connect(self.callbacks.get('toggle_x_cursor_a', lambda: None))
        view_menu.addAction(self.toggle_x_cursor_a_action)
        self.actions['x_cursor_a'] = self.toggle_x_cursor_a_action

        self.toggle_x_cursor_b_action = QAction("X Cursor b", self.parent, checkable=True)
        self._set_action_shortcut(self.toggle_x_cursor_b_action, 'toggle_xb_cursor')
        self.toggle_x_cursor_b_action.triggered.connect(self.callbacks.get('toggle_x_cursor_b', lambda: None))
        view_menu.addAction(self.toggle_x_cursor_b_action)
        self.actions['x_cursor_b'] = self.toggle_x_cursor_b_action

        self.toggle_y_cursor_A_action = QAction("Y Cursor A", self.parent, checkable=True)
        self._set_action_shortcut(self.toggle_y_cursor_A_action, 'toggle_ya_cursor')
        self.toggle_y_cursor_A_action.triggered.connect(self.callbacks.get('toggle_y_cursor_A', lambda: None))
        view_menu.addAction(self.toggle_y_cursor_A_action)
        self.actions['y_cursor_A'] = self.toggle_y_cursor_A_action

        self.toggle_y_cursor_B_action = QAction("Y Cursor B", self.parent, checkable=True)
        self._set_action_shortcut(self.toggle_y_cursor_B_action, 'toggle_yb_cursor')
        self.toggle_y_cursor_B_action.triggered.connect(self.callbacks.get('toggle_y_cursor_B', lambda: None))
        view_menu.addAction(self.toggle_y_cursor_B_action)
        self.actions['y_cursor_B'] = self.toggle_y_cursor_B_action

        view_menu.addSeparator()

        # Zoom actions
        self.zoom_in_action = QAction("Zoom In", self.parent)
        self._set_action_shortcut(self.zoom_in_action, 'zoom_in')
        self.zoom_in_action.triggered.connect(self.callbacks.get('zoom_in', lambda: None))
        view_menu.addAction(self.zoom_in_action)
        self.actions['zoom_in'] = self.zoom_in_action

        self.zoom_out_action = QAction("Zoom Out", self.parent)
        self._set_action_shortcut(self.zoom_out_action, 'zoom_out')
        self.zoom_out_action.triggered.connect(self.callbacks.get('zoom_out', lambda: None))
        view_menu.addAction(self.zoom_out_action)
        self.actions['zoom_out'] = self.zoom_out_action

        self.zoom_to_fit_action = QAction("Zoom to Fit", self.parent)
        self._set_action_shortcut(self.zoom_to_fit_action, 'zoom_to_fit')
        self.zoom_to_fit_action.triggered.connect(self.callbacks.get('zoom_to_fit', lambda: None))
        view_menu.addAction(self.zoom_to_fit_action)
        self.actions['zoom_to_fit'] = self.zoom_to_fit_action

        self.auto_range_x_action = QAction("Auto-range X-axis", self.parent)
        self._set_action_shortcut(self.auto_range_x_action, 'auto_range_x')
        self.auto_range_x_action.triggered.connect(self.callbacks.get('auto_range_x', lambda: None))
        view_menu.addAction(self.auto_range_x_action)
        self.actions['auto_range_x'] = self.auto_range_x_action

        self.auto_range_y_action = QAction("Auto-range Y1 & Y2 axes", self.parent)
        self._set_action_shortcut(self.auto_range_y_action, 'auto_range_y')
        self.auto_range_y_action.triggered.connect(self.callbacks.get('auto_range_y', lambda: None))
        view_menu.addAction(self.auto_range_y_action)
        self.actions['auto_range_y'] = self.auto_range_y_action

        self.zoom_box_action = QAction("Zoom Box", self.parent, checkable=True)
        self.zoom_box_action.setChecked(False)
        self._set_action_shortcut(self.zoom_box_action, 'toggle_zoom_box')
        self.zoom_box_action.triggered.connect(self.callbacks.get('enable_zoom_box', lambda: None))
        view_menu.addAction(self.zoom_box_action)
        self.actions['zoom_box'] = self.zoom_box_action

        self.menubar.addMenu(view_menu)

        # Help menu
        help_menu = QMenu("Help", self.parent)

        keybindings_action = QAction("Keybindings", self.parent)
        keybindings_action.triggered.connect(self.callbacks.get('show_keybindings', lambda: None))
        help_menu.addAction(keybindings_action)

        self.menubar.addMenu(help_menu)

    @staticmethod
    def _make_icon(theme_name: str, fallback: QStyle.StandardPixmap, style) -> QIcon:
        """Create a QIcon from theme with QStyle fallback."""
        if QIcon.hasThemeIcon(theme_name):
            return QIcon.fromTheme(theme_name)
        return style.standardIcon(fallback)

    def _create_toolbar(self):
        """Create toolbar with actions using system icon theme."""
        style = self.parent.style()
        SI = QStyle.StandardPixmap  # shorthand

        def add_action(key: str, text: str, tooltip: str, theme: str,
                       fallback: QStyle.StandardPixmap, checkable: bool = False,
                       checked: bool = False):
            icon = self._make_icon(theme, fallback, style)
            action = QAction(icon, text, self.parent)
            action.setToolTip(tooltip)
            action.setCheckable(checkable)
            action.setChecked(checked)
            action.triggered.connect(self.callbacks.get(key, lambda: None))
            self.toolbar.addAction(action)
            self.actions[key] = action
            return action

        # Open File
        add_action('open_file', "Open File", "Open RAW file",
                   'document-open', SI.SP_DialogOpenButton)

        # Open New Window
        add_action('open_new_window', "Open New Window", "Open new window",
                   'window-new', SI.SP_ComputerIcon)

        self.toolbar.addSeparator()

        # Zoom In
        self.zoom_in_action_toolbar = add_action(
            'zoom_in_toolbar', "Zoom In", "Zoom in (Ctrl+=)",
            'zoom-in', SI.SP_ArrowUp)

        # Zoom Out
        self.zoom_out_action_toolbar = add_action(
            'zoom_out_toolbar', "Zoom Out", "Zoom out (Ctrl+-)",
            'zoom-out', SI.SP_ArrowDown)

        # Zoom to Fit
        self.zoom_to_fit_action_toolbar = add_action(
            'zoom_to_fit_toolbar', "Zoom to Fit", "Auto-range all axes (Ctrl+0)",
            'zoom-fit-best', SI.SP_BrowserReload)

        # Auto-range X-axis
        self.auto_range_x_action_toolbar = add_action(
            'auto_range_x_toolbar', "Auto-range X-axis", "Auto-range X-axis",
            'zoom-fit-width', SI.SP_ArrowRight)

        # Auto-range Y axes
        self.auto_range_y_action_toolbar = add_action(
            'auto_range_y_toolbar', "Auto-range Y-axis", "Auto-range Y1 & Y2 axes",
            'zoom-fit-height', SI.SP_ArrowDown)

        # Zoom Box (checkable)
        self.zoom_box_action_toolbar = add_action(
            'zoom_box_toolbar', "Zoom Box", "Rectangle zoom mode (toggle)",
            'select-rectangular', SI.SP_FileDialogContentsView, checkable=True)

        # Toggle Grids (checkable)
        self.toggle_grids_action_toolbar = add_action(
            'toggle_grids_toolbar', "Toggle Grids", "Toggle grid visibility (Ctrl+G)",
            'view-grid', SI.SP_FileDialogDetailedView, checkable=True, checked=True)

        # Toggle Cross-hair (checkable)
        self.toggle_cross_hair_action_toolbar = add_action(
            'toggle_cross_hair_toolbar', "Toggle Cross-hair", "Toggle cross-hair cursor (click to place marks)",
            'cursor-cross', SI.SP_DialogHelpButton, checkable=True)

        self.toolbar.addSeparator()

        # Individual X/Y cursor toggle buttons in toolbar
        self.toggle_x_cursor_a_toolbar = add_action(
            'toggle_x_cursor_a', "Xa", "Toggle X cursor A",
            'go-first', SI.SP_MediaSeekBackward, checkable=True)
        self.toggle_x_cursor_b_toolbar = add_action(
            'toggle_x_cursor_b', "Xb", "Toggle X cursor B",
            'go-last', SI.SP_MediaSeekForward, checkable=True)
        self.toggle_y_cursor_A_toolbar = add_action(
            'toggle_y_cursor_A', "YA", "Toggle Y cursor A",
            'go-top', SI.SP_ArrowUp, checkable=True)
        self.toggle_y_cursor_B_toolbar = add_action(
            'toggle_y_cursor_B', "YB", "Toggle Y cursor B",
            'go-bottom', SI.SP_ArrowDown, checkable=True)

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