#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KeyBindingManager - Central registry for application keybindings.

Provides default keybindings, loads user overrides from ~/.pqwave/keybindings.json,
and returns effective key sequences for all application actions.
"""

import os
import json

from pqwave.logging_config import get_logger

logger = get_logger(__name__)


class KeyBindingManager:
    """Manages keybindings for the application.

    Defaults are defined in the DEFAULTS dict.  User overrides are loaded
    from ~/.pqwave/keybindings.json on startup and can be saved back.

    Each entry maps an action name (str) to a (key_sequence, description) tuple.
    The key_sequence is a string in QKeySequence format.
    """

    DEFAULTS = {
        # === File operations ===
        'open_file':               ('Ctrl+O',       'Open Raw File'),
        'open_new_window':         ('Ctrl+N',       'Open New Window'),
        'save_current_state':      ('Ctrl+S',       'Save Current State'),

        # === Edit / Settings ===
        'edit_trace_properties':   ('Ctrl+E',       'Edit Trace Properties'),
        'show_settings':           ('Shift+E',      'Settings'),

        # === View: toggles ===
        'toggle_grids':            ('Ctrl+G',       'Toggle Grids'),
        'toggle_cross_hair':       ('+',            'Toggle Cross-hair'),
        'toggle_xa_cursor':        ('A',            'Toggle Xa Cursor'),
        'toggle_xb_cursor':        ('B',            'Toggle Xb Cursor'),
        'toggle_ya_cursor':        ('Shift+A',      'Toggle YA Cursor'),
        'toggle_yb_cursor':        ('Shift+B',      'Toggle YB Cursor'),
        'toggle_zoom_box':         ('Z',            'Toggle Zoom Box'),
        'zoom_to_fit':             ('Ctrl+0',       'Zoom to Fit'),
        'zoom_to_fit_alt':         ('F',            'Zoom to Fit (alt)'),

        # === Zoom ===
        'zoom_in':                 ('Ctrl+=',       'Zoom In'),
        'zoom_out':                ('Ctrl+-',       'Zoom Out'),

        # === Axis ===
        'log_x':                   ('Ctrl+Shift+X', 'Toggle Log X'),
        'log_y1':                  ('Ctrl+Shift+Y', 'Toggle Log Y1'),
        'log_y2':                  ('Ctrl+Shift+Z', 'Toggle Log Y2'),
        'auto_range_x':            ('Ctrl+Right',   'Auto-range X-axis'),
        'auto_range_y':            ('Ctrl+Up',      'Auto-range Y1 & Y2'),

        # === Cursor movement ===
        'move_x_cursor_left':      ('Left',         'Move X cursor left'),
        'move_x_cursor_right':     ('Right',        'Move X cursor right'),
        'move_y_cursor_up':        ('Up',           'Move Y cursor up'),
        'move_y_cursor_down':      ('Down',         'Move Y cursor down'),
    }

    def __init__(self):
        self._user_overrides: dict = {}
        self._load_user_overrides()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_sequence(self, action_name: str) -> str:
        """Return the effective key sequence for *action_name*.

        Falls back to the default when no user override is present.
        Returns an empty string if the action name is unknown.
        """
        default = self.DEFAULTS.get(action_name)
        if default is None:
            logger.warning("Unknown action '%s'", action_name)
            return ''
        return self._user_overrides.get(action_name, default[0])

    def set_override(self, action_name: str, key_sequence: str) -> None:
        """Set a user override for *action_name*."""
        if action_name not in self.DEFAULTS:
            logger.warning("Ignoring override for unknown action '%s'", action_name)
            return
        self._user_overrides[action_name] = key_sequence

    def save_user_overrides(self) -> None:
        """Write current overrides to the config file."""
        path = self._config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._user_overrides, f, indent=2)
            logger.info("Keybindings saved to %s", path)
        except OSError as e:
            logger.warning("Failed to save keybindings to %s: %s", path, e)

    def get_all_bindings(self) -> list[dict]:
        """Return a complete list of all bindings for display.

        Each entry::
            {'action': str, 'key': str, 'description': str, 'is_default': bool}
        """
        result = []
        for action, (default_key, description) in self.DEFAULTS.items():
            effective_key = self._user_overrides.get(action, default_key)
            is_default = action not in self._user_overrides
            result.append({
                'action': action,
                'key': effective_key,
                'description': description,
                'is_default': is_default,
            })
        return result

    def get_actions_with_shortcut_context(self) -> tuple[list[str], list[str]]:
        """Separate actions into global vs plot-contextual.

        Returns (global_actions, plot_actions) where each is a list of action
        names whose shortcuts should be installed at the window level vs only
        when the plot widget has focus.
        """
        global_actions = []
        plot_actions = []
        for action in self.DEFAULTS:
            seq = self.get_sequence(action)
            # Single lower-case letters -> plot-only (avoid text-input conflict)
            # Single upper-case letters  -> plot-only
            # '+'                          -> plot-only
            # Arrow keys                  -> plot-only
            # Everything else with Ctrl   -> global (or no conflict)
            is_single = len(seq) == 1
            is_arrow = seq in ('Left', 'Right', 'Up', 'Down')
            if is_single or is_arrow:
                plot_actions.append(action)
            else:
                global_actions.append(action)
        return global_actions, plot_actions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _config_path(self) -> str:
        return os.path.join(os.path.expanduser("~"), ".pqwave", "keybindings.json")

    def _load_user_overrides(self) -> None:
        """Load user overrides from the config file.  Silently handle errors."""
        path = self._config_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Keybindings file is not a JSON object, ignoring")
                return
            # Only keep entries that match known actions
            self._user_overrides = {
                k: v for k, v in data.items()
                if k in self.DEFAULTS and isinstance(v, str)
            }
            logger.debug("Loaded %d user keybinding overrides", len(self._user_overrides))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load keybindings from %s: %s", path, e)
