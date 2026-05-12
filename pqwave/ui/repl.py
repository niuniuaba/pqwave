#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
REPL executor for pqwave chat panel.

Wraps code.InteractiveInterpreter and runs execution in a QThread
so the GUI stays responsive during code execution.
"""

from __future__ import annotations

import io
import sys
from typing import Optional

import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal


class ReplThread(QThread):
    """Background thread for executing Python code."""

    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, code: str, namespace: dict, parent=None):
        super().__init__(parent)
        self._code = code
        self._namespace = namespace

    def run(self):
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = stdout_capture
            sys.stderr = stdout_capture

            # Try eval first for expressions that return a value
            try:
                result = eval(self._code, self._namespace)
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                if result is not None:
                    self.result_ready.emit(result)
                    return
            except SyntaxError:
                pass

            # Fall back to exec for statements
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            exec(self._code, self._namespace)
            output = stdout_capture.getvalue()
            if output.strip():
                self.result_ready.emit(output.strip())
        except Exception as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.error_occurred.emit(str(e))


class ReplExecutor:
    """Manages Python code execution in a background thread."""

    def __init__(self, session=None):
        from pqwave.session.api import SessionAPI
        self._session = session or SessionAPI()
        self._thread: Optional[ReplThread] = None

    def signals(self) -> list[str]:
        """List available signal names."""
        return self._session.signals()

    @property
    def _namespace(self) -> dict:
        from pqwave.session.api import get_command_registry

        from functools import partial
        ns = {"session": self._session, "np": np}
        for name, entry in get_command_registry().items():
            ns[name] = partial(entry["fn"], self._session)
        return ns

    def execute(self, code: str) -> ReplThread:
        """Execute code in a background thread. Returns the thread for signal
        connection."""
        thread = ReplThread(code, self._namespace)
        self._thread = thread
        thread.start()
        return thread

    def run_sync(self, code: str) -> dict:
        """Execute code synchronously (for AI-generated code or headless)."""
        try:
            ns = self._namespace
            result = eval(code, ns)
            return {"ok": True, "result": result}
        except SyntaxError:
            try:
                exec(code, ns)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_completions(self, prefix: str) -> list[str]:
        """Return tab-completion suggestions for a prefix."""
        from pqwave.session.api import get_command_registry

        suggestions = []
        for name in get_command_registry():
            if name.startswith(prefix):
                suggestions.append(name)
        for attr in dir(self._session):
            if not attr.startswith("_") and attr.startswith(prefix):
                suggestions.append(attr + "()")
        try:
            for sig in self._session.signals():
                if sig.lower().startswith(prefix.lower()):
                    suggestions.append(sig)
        except Exception:
            pass
        return sorted(set(suggestions))
