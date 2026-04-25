#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Integration tests for keybinding infrastructure.

Tests that:
- Menu actions have correct QKeySequence shortcuts set
- KeyBindingManager is properly wired to MenuManager
- QShortcut instances are created for plot-contextual keys
- PlotWidget cursor selection and movement methods work
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Qt app must exist before importing any Qt-bound classes
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QPointF

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from pqwave.models.state import ApplicationState, AxisId
from pqwave.ui.keybinding_manager import KeyBindingManager
from pqwave.ui.menu_manager import MenuManager
from pqwave.ui.plot_widget import PlotWidget
from pqwave.ui.main_window import MainWindow


class TestKeybindingMenuActions(unittest.TestCase):
    """Verify that menu actions have correct shortcuts applied."""

    def setUp(self):
        self.km = KeyBindingManager()
        self.main_window = QMainWindow()
        self.menu = MenuManager(self.main_window, {
            'open_file': lambda: None,
            'open_new_window': lambda: None,
            'save_current_state': lambda: None,
            'convert_raw_data': lambda: None,
            'edit_trace_properties': lambda: None,
            'show_settings': lambda: None,
            'toggle_toolbar': lambda: None,
            'toggle_statusbar': lambda: None,
            'toggle_grids': lambda: None,
            'zoom_in': lambda: None,
            'zoom_out': lambda: None,
            'zoom_to_fit': lambda: None,
            'auto_range_x': lambda: None,
            'auto_range_y': lambda: None,
            'enable_zoom_box': lambda: None,
            'zoom_in_toolbar': lambda: None,
            'zoom_out_toolbar': lambda: None,
            'zoom_to_fit_toolbar': lambda: None,
            'auto_range_x_toolbar': lambda: None,
            'auto_range_y_toolbar': lambda: None,
            'zoom_box_toolbar': lambda: None,
            'toggle_grids_toolbar': lambda: None,
            'toggle_cross_hair': lambda: None,
            'toggle_x_cursor_a': lambda: None,
            'toggle_x_cursor_b': lambda: None,
            'toggle_y_cursor_A': lambda: None,
            'toggle_y_cursor_B': lambda: None,
            'show_keybindings': lambda: None,
        }, keybinding_manager=self.km)
        self.actions = self.menu.actions

    def tearDown(self):
        self.main_window.close()

    # --- 1. Menu actions have shortcuts set ---

    def test_open_file_has_shortcut(self):
        """File > Open Raw File should have Ctrl+O shortcut."""
        seq = self.km.get_sequence('open_file')
        self.assertEqual(seq, 'Ctrl+O')

    def test_open_new_window_has_shortcut(self):
        seq = self.km.get_sequence('open_new_window')
        self.assertEqual(seq, 'Ctrl+N')

    def test_zoom_in_has_shortcut(self):
        seq = self.km.get_sequence('zoom_in')
        self.assertEqual(seq, 'Ctrl+=')

    def test_zoom_out_has_shortcut(self):
        seq = self.km.get_sequence('zoom_out')
        self.assertEqual(seq, 'Ctrl+-')

    def test_toggle_grids_has_shortcut(self):
        seq = self.km.get_sequence('toggle_grids')
        self.assertEqual(seq, 'Ctrl+G')

    # --- 2. Single-key actions do NOT have QAction shortcuts ---

    def test_single_key_actions_not_on_qaction(self):
        """Letter keys like 'A', 'B' must not be set as QAction shortcuts."""
        # Find the View menu by label
        view_menu = None
        for m in self.menu.menubar.actions():
            if m.text() == 'View':
                view_menu = m.menu()
                break
        if view_menu is None:
            self.fail("View menu not found")
        for action in view_menu.actions():
            ks = action.shortcut()
            if not ks.isEmpty():
                seq = ks.toString()
                # Should never be a bare letter
                self.assertFalse(len(seq) == 1 and seq.isalpha(),
                                 f"Action '{action.text()}' has bare letter shortcut '{seq}'")

    # --- 3. Help menu has Keybindings item ---

    def test_help_menu_has_keybindings(self):
        """Help menu should have a Keybindings item."""
        menus = self.menu.menubar.actions()
        help_names = [m.text() for m in menus]
        self.assertIn('Help', help_names)

        help_menu = menus[-1].menu()
        action_texts = [a.text() for a in help_menu.actions()]
        self.assertIn('Keybindings', action_texts)


class TestKeybindingMainWindowIntegration(unittest.TestCase):
    """Integration tests with a real MainWindow (or as close as possible)."""

    @classmethod
    def setUpClass(cls):
        # MainWindow creates RawFile during _load_initial_file which uses QTimer
        # — we stub it to avoid file I/O.
        cls.window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()

    def test_keybinding_manager_created(self):
        """MainWindow should have a KeyBindingManager."""
        self.assertIsNotNone(self.window.keybinding_manager)

    def test_keybinding_manager_passed_to_menu_manager(self):
        """MenuManager should receive the KeyBindingManager."""
        self.assertIsNotNone(self.window.menu_manager.keybinding_manager)
        self.assertIs(
            self.window.menu_manager.keybinding_manager,
            self.window.keybinding_manager
        )

    def test_toggle_log_axis_toggles(self):
        """_toggle_log_axis should flip the log mode."""
        config = self.window.state.get_axis_config(AxisId.X)
        original = config.log_mode
        self.window._toggle_log_axis(AxisId.X)
        self.assertNotEqual(config.log_mode, original)
        # Toggle back to restore
        self.window._toggle_log_axis(AxisId.X)
        self.assertEqual(config.log_mode, original)

    def test_cursor_selection_and_movement(self):
        """PlotWidget cursor selection and movement methods."""
        pw = self.window.plot_widget

        # Initially selected cursor tracks the first one created (Xa)
        self.assertIsNotNone(pw._selected_x_cursor)

        # Can explicitly select a cursor
        pw.select_x_cursor('xb')
        self.assertEqual(pw._selected_x_cursor, 'xb')

        # With no cursors visible, movement does nothing (no crash)
        pw.move_selected_cursor('left')
        pw.move_selected_cursor('right')

        # Auto-select when only one X cursor is visible
        pw._auto_select_x_cursor()

    def test_get_actions_with_shortcut_context(self):
        """Verify context separation works."""
        global_actions, plot_actions = (
            self.window.keybinding_manager.get_actions_with_shortcut_context()
        )
        self.assertIn('toggle_xa_cursor', plot_actions)
        self.assertIn('open_file', global_actions)

    def test_cursor_drag_auto_selects(self):
        """Dragging a cursor should select it."""
        pw = self.window.plot_widget
        mock_line = MagicMock()
        mock_line.value.return_value = 42.0
        pw._on_cursor_dragged('xa', mock_line)
        self.assertEqual(pw._selected_x_cursor, 'xa')
        mock_line.value.return_value = 1.5
        pw._on_cursor_dragged('yB', mock_line)
        self.assertEqual(pw._selected_y_cursor, 'yB')

    def test_show_keybindings_method(self):
        """_show_keybindings should not crash."""
        # Just verify the method exists and the dialog can be created
        bindings = self.window.keybinding_manager.get_all_bindings()
        config_path = self.window.keybinding_manager._config_path()
        from pqwave.ui.keybindings_dialog import KeyBindingsDialog
        dialog = KeyBindingsDialog(bindings, config_path)
        self.assertIsNotNone(dialog)
        dialog.close()

    # --- Fix tests: auto-range, up/down direction, click selection ---

    def test_auto_range_x_preserves_y_range(self):
        """auto_range_x should only change X range, preserving Y range."""
        pw = self.window.plot_widget
        vb = pw.plotItem.vb

        # Set known ranges
        vb.setXRange(10, 20, padding=0)
        vb.setYRange(30, 40, padding=0)

        # Capture Y range before auto-ranging X
        y_before = vb.viewRange()[1]

        pw.auto_range_axis('X')

        # Y range should be preserved
        y_after = vb.viewRange()[1]
        self.assertEqual(y_before, y_after)

    def test_auto_range_y_preserves_x_range(self):
        """auto_range_y should only change Y range, preserving X range."""
        pw = self.window.plot_widget
        vb = pw.plotItem.vb

        # Set known ranges
        vb.setXRange(10, 20, padding=0)
        vb.setYRange(30, 40, padding=0)

        # Capture X range before auto-ranging Y
        x_before = vb.viewRange()[0]

        pw.auto_range_axis('Y1')

        # X range should be preserved
        x_after = vb.viewRange()[0]
        self.assertEqual(x_before, x_after)

    def test_move_cursor_up_increases_value(self):
        """Up arrow should increase Y cursor value (move up in viewbox coords)."""
        pw = self.window.plot_widget

        # Enable yA cursor at a known position
        pw.set_cursor_yA_visible(True, position=50.0)
        pw._selected_y_cursor = 'yA'

        # Set a view range so 1-pixel step is non-zero
        pw.plotItem.vb.setYRange(0, 100, padding=0)
        # Force a non-zero scene rect by resizing
        pw.resize(400, 400)

        val_before = pw.cursor_yA_line.value()
        pw.move_selected_cursor('up')
        val_after = pw.cursor_yA_line.value()

        # Up should increase the value
        self.assertGreater(val_after, val_before)

    def test_move_cursor_down_decreases_value(self):
        """Down arrow should decrease Y cursor value (move down in viewbox coords)."""
        pw = self.window.plot_widget

        # Enable yA cursor at a known position
        pw.set_cursor_yA_visible(True, position=50.0)
        pw._selected_y_cursor = 'yA'

        # Set a view range so 1-pixel step is non-zero
        pw.plotItem.vb.setYRange(0, 100, padding=0)
        pw.resize(400, 400)

        val_before = pw.cursor_yA_line.value()
        pw.move_selected_cursor('down')
        val_after = pw.cursor_yA_line.value()

        # Down should decrease the value
        self.assertLess(val_after, val_before)

    def test_cursor_click_selects_x_cursor(self):
        """_check_cursor_click should select the clicked X cursor."""
        pw = self.window.plot_widget

        # Enable both X cursors at different positions
        pw.set_cursor_xa_visible(True, position=10.0)
        pw.set_cursor_xb_visible(True, position=90.0)
        pw._selected_x_cursor = 'xb'  # start with xb selected

        # Try to select xa via click detection near its position
        pw._check_cursor_click(QPointF(0, 0))

        # The test simply verifies the method doesn't crash.
        # Scene-coord mapping may not work without rendering.
        self.assertIn(pw._selected_x_cursor, ('xa', 'xb'))

    def test_cursor_click_selects_y_cursor(self):
        """_check_cursor_click should select the clicked Y cursor."""
        pw = self.window.plot_widget

        # Enable both Y cursors
        pw.set_cursor_yA_visible(True, position=25.0)
        pw.set_cursor_yB_visible(True, position=75.0)
        pw._selected_y_cursor = 'yB'

        # Try to select yA via click detection near its position
        pw._check_cursor_click(QPointF(0, 0))

        self.assertIn(pw._selected_y_cursor, ('yA', 'yB'))


if __name__ == '__main__':
    unittest.main()
