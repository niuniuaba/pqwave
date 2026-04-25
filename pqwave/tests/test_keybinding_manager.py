#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unit tests for KeyBindingManager."""

import os
import json
import tempfile
import unittest
from unittest.mock import patch

from pqwave.ui.keybinding_manager import KeyBindingManager


class TestKeyBindingManager(unittest.TestCase):
    """KeyBindingManager unit tests."""

    def setUp(self):
        # Use a temp config path to avoid contaminating ~/.pqwave
        self.patcher = patch.object(
            KeyBindingManager, '_config_path',
            return_value=os.path.join(tempfile.gettempdir(), f'test_kb_{os.getpid()}.json')
        )
        self.mock_path = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        # Clean up temp file
        path = KeyBindingManager._config_path(self)
        if os.path.exists(path):
            os.unlink(path)

    # --- 1. All 24 defaults present ---

    def test_defaults_count(self):
        km = KeyBindingManager()
        self.assertGreaterEqual(len(km.DEFAULTS), 24)

    # --- 2. get_sequence returns default when no override ---

    def test_get_sequence_returns_default(self):
        km = KeyBindingManager()
        seq = km.get_sequence('open_file')
        self.assertEqual(seq, 'Ctrl+O')

    # --- 3. User override takes precedence ---

    def test_user_override_takes_precedence(self):
        km = KeyBindingManager()
        km.set_override('open_file', 'Ctrl+Shift+O')
        self.assertEqual(km.get_sequence('open_file'), 'Ctrl+Shift+O')

    # --- 4. Load overrides from file ---

    def test_load_overrides_from_file(self):
        path = KeyBindingManager._config_path(self)
        with open(path, 'w') as f:
            json.dump({'open_file': 'Ctrl+Shift+O'}, f)
        # Re-create so it reads from the file
        km = KeyBindingManager()
        self.assertEqual(km.get_sequence('open_file'), 'Ctrl+Shift+O')
        # Other actions should still use defaults
        self.assertEqual(km.get_sequence('save_current_state'), 'Ctrl+S')

    # --- 5. Save and reload overrides ---

    def test_save_and_reload_overrides(self):
        km = KeyBindingManager()
        km.set_override('zoom_in', 'Ctrl++')
        km.save_user_overrides()

        km2 = KeyBindingManager()
        self.assertEqual(km2.get_sequence('zoom_in'), 'Ctrl++')

    # --- 6. Missing config file uses defaults ---

    def test_missing_config_file_uses_defaults(self):
        path = KeyBindingManager._config_path(self)
        if os.path.exists(path):
            os.unlink(path)
        km = KeyBindingManager()
        self.assertEqual(km.get_sequence('zoom_to_fit'), 'Ctrl+0')

    # --- 7. Corrupted config ignored ---

    def test_corrupted_config_ignored(self):
        path = KeyBindingManager._config_path(self)
        with open(path, 'w') as f:
            f.write('{not json')
        km = KeyBindingManager()
        self.assertEqual(km.get_sequence('open_file'), 'Ctrl+O')

    # --- 8. get_all_bindings structure ---

    def test_get_all_bindings_structure(self):
        km = KeyBindingManager()
        km.set_override('open_file', 'Ctrl+Shift+O')
        bindings = km.get_all_bindings()
        self.assertIsInstance(bindings, list)
        self.assertGreaterEqual(len(bindings), 24)

        # Each entry has the required keys
        for b in bindings:
            self.assertIn('action', b)
            self.assertIn('key', b)
            self.assertIn('description', b)
            self.assertIn('is_default', b)

        # The overridden one should show as non-default
        file_binding = [b for b in bindings if b['action'] == 'open_file'][0]
        self.assertFalse(file_binding['is_default'])
        self.assertEqual(file_binding['key'], 'Ctrl+Shift+O')

    # --- 9. Unknown action returns empty string ---

    def test_unknown_action_returns_empty(self):
        km = KeyBindingManager()
        seq = km.get_sequence('nonexistent_action')
        self.assertEqual(seq, '')

    # --- 10. set_override ignores unknown actions ---

    def test_set_override_unknown_action(self):
        km = KeyBindingManager()
        km.set_override('not_real', 'Ctrl+X')
        # Should not be stored
        self.assertNotIn('not_real', km._user_overrides)

    # --- 11. Plot-contextual vs global separation ---

    def test_shortcut_context_separation(self):
        km = KeyBindingManager()
        global_actions, plot_actions = km.get_actions_with_shortcut_context()
        # Single-letter actions should be in plot_actions
        self.assertIn('toggle_xa_cursor', plot_actions)
        self.assertIn('toggle_cross_hair', plot_actions)
        self.assertIn('toggle_zoom_box', plot_actions)
        # Ctrl-modified actions should be in global_actions
        self.assertIn('open_file', global_actions)
        self.assertIn('save_current_state', global_actions)
        self.assertIn('zoom_in', global_actions)


if __name__ == '__main__':
    unittest.main()
