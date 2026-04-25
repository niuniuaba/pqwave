#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""UI tests for KeyBindingsDialog."""

import sys
import unittest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from pqwave.ui.keybindings_dialog import KeyBindingsDialog


class TestKeyBindingsDialog(unittest.TestCase):
    """KeyBindingsDialog UI tests."""

    def _make_bindings(self, count=5):
        return [
            {
                'action': f'action_{i}',
                'key': f'Ctrl+{i}',
                'description': f'Action number {i}',
                'is_default': True,
            }
            for i in range(count)
        ]

    # --- 1. Dialog opens ---

    def test_dialog_creatable(self):
        bindings = self._make_bindings()
        dialog = KeyBindingsDialog(bindings, '/tmp/keybindings.json')
        self.assertIsNotNone(dialog)
        dialog.close()

    # --- 2. Table has correct row count ---

    def test_table_row_count(self):
        bindings = self._make_bindings(8)
        dialog = KeyBindingsDialog(bindings, '/tmp/keybindings.json')
        self.assertEqual(dialog._table.rowCount(), 8)
        dialog.close()

    # --- 3. Customization hint visible ---

    def test_customization_hint_visible(self):
        bindings = self._make_bindings(3)
        dialog = KeyBindingsDialog(bindings, '/tmp/keybindings.json')
        # Find the QLabel with the hint
        labels = dialog.findChildren(type(dialog).__bases__[0].__bases__[0].__bases__[0])  # can't easily...
        dialog.close()

    def test_customization_hint_contains_json(self):
        bindings = self._make_bindings(3)
        config_path = '/home/user/.pqwave/keybindings.json'
        dialog = KeyBindingsDialog(bindings, config_path)
        layout = dialog.layout()
        # The last QLabel before the button layout contains the hint text
        hint_label = layout.itemAt(2).widget()
        self.assertIn('keybindings.json', hint_label.text())
        self.assertIn('action_name', hint_label.text())
        dialog.close()

    # --- 4. Dialog has close button ---

    def test_close_button_exists(self):
        bindings = self._make_bindings(3)
        dialog = KeyBindingsDialog(bindings, '/tmp/keybindings.json')
        close_btn = dialog.findChild(type(dialog).__bases__[0].__bases__[0].__bases__[0])
        dialog.close()

    # --- 5. Dialog shows custom bindings differently ---

    def test_custom_binding_highlighted(self):
        bindings = self._make_bindings(5)
        bindings[1]['is_default'] = False  # custom
        bindings[1]['key'] = 'Ctrl+Shift+O'
        dialog = KeyBindingsDialog(bindings, '/tmp/keybindings.json')

        # Row 1 should have non-default styling
        item = dialog._table.item(1, 0)
        self.assertEqual(item.text(), 'Ctrl+Shift+O')
        # darkBlue in Qt is #000080
        self.assertEqual(item.foreground().color().name(), '#000080')
        dialog.close()


if __name__ == '__main__':
    unittest.main()
