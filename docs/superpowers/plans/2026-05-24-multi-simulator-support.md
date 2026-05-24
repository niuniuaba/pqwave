# Multi-Simulator Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend pqwave to open output files from Xyce, Verilator, and GHDL simulators.

**Architecture:** Follow the existing adapter pattern (VcdFile duck-type interface). RawFile gets a dialect fallback fix. FstAdapter and GhwAdapter each shell out to a CLI tool, pipe output through VcdFile, and expose `.datasets` / `.get_variable_names()` / `.get_variable_data()` / `.get_num_points()`. Tool paths stored in ApplicationState + global prefs.

**Tech Stack:** Python 3.14, spicelib, vcdvcd, subprocess, shutil.which

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pqwave/models/state.py` | Modify | Add `tool_paths` dict to ApplicationState |
| `pqwave/ui/main_window.py` | Modify | Save/load `tool_paths` in global prefs |
| `pqwave/ui/settings_widget.py` | Modify | Add tool_paths input fields |
| `pqwave/models/rawfile.py` | Modify | Xyce dialect fallback |
| `pqwave/models/fst_adapter.py` | Create | FST→VCD adapter |
| `pqwave/models/ghw_adapter.py` | Create | GHW→VCD adapter |
| `pqwave/session/api.py` | Modify | Dispatch `.fst` and `.ghw` |
| `pqwave/tests/test_rawfile.py` | Modify | Test Xyce raw parsing |
| `pqwave/tests/test_fst_adapter.py` | Create | Test FstAdapter |
| `pqwave/tests/test_ghw_adapter.py` | Create | Test GhwAdapter |

---

### Task 1: Add tool_paths to ApplicationState

**Files:**
- Modify: `pqwave/models/state.py:285-321`

- [ ] **Step 1: Add `tool_paths` to `_initialize`**

In `pqwave/models/state.py`, in the `_initialize` method, add after the existing initializations (before `self.mc_collection`):

```python
# Tool paths for external converters (none = use $PATH)
self.tool_paths: Dict[str, str] = {
    "fst2vcd": "",
    "ghwdump": "",
}
```

Run: `venv/bin/python -c "from pqwave.models.state import ApplicationState; s = ApplicationState(); print('tool_paths:', s.tool_paths)"`
Expected: `tool_paths: {'fst2vcd': '', 'ghwdump': ''}`

- [ ] **Step 2: Commit**

```bash
git add pqwave/models/state.py
git commit -m "feat: add tool_paths dict to ApplicationState

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Persist tool_paths in global preferences

**Files:**
- Modify: `pqwave/ui/main_window.py:3922-3933` (_save_global_prefs)
- Modify: `pqwave/ui/main_window.py:3940-3981` (_load_global_prefs)

- [ ] **Step 1: Add tool_paths to save**

In `_save_global_prefs`, add `'tool_paths'` to the data dict:

```python
data = {
    'viewbox_theme': self.state.viewbox_theme.value,
    'title_font': self.state.title_font.to_dict(),
    'label_font': self.state.label_font.to_dict(),
    'tick_font': self.state.tick_font.to_dict(),
    'ui_font': self.state.ui_font.to_dict(),
    'repl_font': self.state.repl_font.to_dict(),
    'repl_bg': self.state.repl_bg,
    'toolbar_visible': self.state.toolbar_visible,
    'status_bar_visible': self.state.status_bar_visible,
    'chat_panel_visible': self.state.chat_panel_visible,
    'tool_paths': dict(self.state.tool_paths),
}
```

- [ ] **Step 2: Add tool_paths to load**

In `_load_global_prefs`, after `self.state.repl_bg = ...` line:

```python
saved_paths = data.get('tool_paths', {})
if isinstance(saved_paths, dict):
    for key in ('fst2vcd', 'ghwdump'):
        val = saved_paths.get(key, '')
        if isinstance(val, str) and val.strip():
            self.state.tool_paths[key] = val.strip()
        else:
            self.state.tool_paths[key] = ''
```

- [ ] **Step 3: Verify with a quick test**

```bash
venv/bin/python -c "
from pqwave.models.state import ApplicationState
s = ApplicationState()
s.tool_paths['fst2vcd'] = '/opt/gtkwave/bin/fst2vcd'
print('Set:', s.tool_paths)
# Reset
s.tool_paths['fst2vcd'] = ''
print('Reset:', s.tool_paths)
"
```

- [ ] **Step 4: Commit**

```bash
git add pqwave/ui/main_window.py
git commit -m "feat: persist tool_paths in global preferences

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Add tool path fields to Settings UI

**Files:**
- Modify: `pqwave/ui/settings_widget.py`

- [ ] **Step 1: Add tool_paths group to SettingsWidget**

After the existing REPL appearance group in `_create_ui`, add a new Tool Paths group box before the close button. Add this code after line 343 (after `content_layout.addWidget(repl_group)`):

```python
# Tool paths for external converters
tool_paths_group = QGroupBox("External Converter Paths")
tool_paths_layout = QGridLayout()

# fst2vcd
tool_paths_layout.addWidget(QLabel("fst2vcd:"), 0, 0)
self._fst2vcd_edit = QLineEdit()
self._fst2vcd_edit.setPlaceholderText("Use $PATH (e.g. /usr/bin/fst2vcd)")
self._fst2vcd_edit.setMinimumWidth(200)
self._fst2vcd_edit.textChanged.connect(self._on_tool_path_changed)
tool_paths_layout.addWidget(self._fst2vcd_edit, 0, 1)

fst2vcd_reset = QPushButton("Reset")
fst2vcd_reset.clicked.connect(lambda: self._reset_tool_path("fst2vcd"))
tool_paths_layout.addWidget(fst2vcd_reset, 0, 2)

# ghwdump
tool_paths_layout.addWidget(QLabel("ghwdump:"), 1, 0)
self._ghwdump_edit = QLineEdit()
self._ghwdump_edit.setPlaceholderText("Use $PATH (e.g. /usr/local/bin/ghwdump)")
self._ghwdump_edit.setMinimumWidth(200)
self._ghwdump_edit.textChanged.connect(self._on_tool_path_changed)
tool_paths_layout.addWidget(self._ghwdump_edit, 1, 1)

ghwdump_reset = QPushButton("Reset")
ghwdump_reset.clicked.connect(lambda: self._reset_tool_path("ghwdump"))
tool_paths_layout.addWidget(ghwdump_reset, 1, 2)

tool_paths_group.setLayout(tool_paths_layout)
content_layout.addWidget(tool_paths_group)
```

- [ ] **Step 2: Add _load_current_settings tool_paths loading**

In `_load_current_settings`, after the REPL settings loading (after line 511), add:

```python
# Load tool paths
self._fst2vcd_edit.blockSignals(True)
self._fst2vcd_edit.setText(self.state.tool_paths.get("fst2vcd", ""))
self._fst2vcd_edit.blockSignals(False)
self._ghwdump_edit.blockSignals(True)
self._ghwdump_edit.setText(self.state.tool_paths.get("ghwdump", ""))
self._ghwdump_edit.blockSignals(False)
```

- [ ] **Step 3: Add handler methods**

Add these methods to the SettingsWidget class:

```python
def _on_tool_path_changed(self) -> None:
    """Write tool path edits back to ApplicationState."""
    self.state.tool_paths["fst2vcd"] = self._fst2vcd_edit.text().strip()
    self.state.tool_paths["ghwdump"] = self._ghwdump_edit.text().strip()

def _reset_tool_path(self, key: str) -> None:
    """Reset a tool path to default (empty = use $PATH)."""
    self.state.tool_paths[key] = ""
    if key == "fst2vcd":
        self._fst2vcd_edit.blockSignals(True)
        self._fst2vcd_edit.setText("")
        self._fst2vcd_edit.blockSignals(False)
    elif key == "ghwdump":
        self._ghwdump_edit.blockSignals(True)
        self._ghwdump_edit.setText("")
        self._ghwdump_edit.blockSignals(False)
```

- [ ] **Step 4: Commit**

```bash
git add pqwave/ui/settings_widget.py
git commit -m "feat: add external converter tool path fields to settings UI

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Fix Xyce dialect auto-detection in RawFile

**Files:**
- Modify: `pqwave/models/rawfile.py:553-554`

- [ ] **Step 1: Write failing test**

In `pqwave/tests/test_rawfile.py`, add after line 41:

```python
def test_xyce_dialect_fallback():
    """Test that RawFile falls back to xyce/ngspice dialect when auto-detect fails."""
    from pqwave.models.rawfile import RawFile

    # bridge_xyce.raw is a Qucs+Xyce file without a Command: header line
    # that spicelib cannot auto-detect
    xyce_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "bridge_xyce.raw"
    )
    if not os.path.exists(xyce_file):
        print("SKIP: bridge_xyce.raw not found")
        return

    rf = RawFile(xyce_file)
    assert len(rf.datasets) == 1, f"Expected 1 dataset, got {len(rf.datasets)}"
    var_names = rf.get_variable_names()
    assert len(var_names) == 10, f"Expected 10 variables, got {len(var_names)}"
    assert "time" in var_names, "Expected 'time' variable"
    assert "VOUT" in var_names, "Expected 'VOUT' variable"
    assert rf.get_num_points() == 499, f"Expected 499 points, got {rf.get_num_points()}"
    print("OK: Xyce dialect fallback works")
```

Run: `venv/bin/python -c "from pqwave.tests.test_rawfile import test_xyce_dialect_fallback; test_xyce_dialect_fallback()"`
Expected: FAIL — SpiceReadException about auto-detection

- [ ] **Step 2: Implement the fix**

In `pqwave/models/rawfile.py`, in the `parse()` method around line 553-554, change:

```python
try:
    self.raw_data = RawRead(load_path)
```

To:

```python
from spicelib.raw.raw_classes import SpiceReadException

try:
    self.raw_data = RawRead(load_path)
except SpiceReadException:
    for dialect in ('ngspice', 'xyce'):
        try:
            self.raw_data = RawRead(load_path, dialect=dialect)
            break
        except Exception:
            continue
    else:
        raise
```

- [ ] **Step 3: Run test — should pass**

Run: `venv/bin/python -c "from pqwave.tests.test_rawfile import test_xyce_dialect_fallback; test_xyce_dialect_fallback()"`
Expected: "OK: Xyce dialect fallback works"

- [ ] **Step 4: Run existing tests to verify no regression**

```bash
venv/bin/python -m pytest pqwave/tests/test_rawfile.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add pqwave/models/rawfile.py pqwave/tests/test_rawfile.py
git commit -m "fix: add Xyce/ngspice dialect fallback when spicelib auto-detect fails

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Create FstAdapter

**Files:**
- Create: `pqwave/models/fst_adapter.py`
- Create: `pqwave/tests/test_fst_adapter.py`

- [ ] **Step 1: Write failing test**

Create `pqwave/tests/test_fst_adapter.py`:

```python
"""Tests for FstAdapter"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


def test_fst_adapter_missing_tool():
    """FstAdapter raises when fst2vcd is not found."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    # Ensure tool_paths is empty and shutil.which returns None
    state = ApplicationState()
    state.tool_paths["fst2vcd"] = ""

    with patch("shutil.which", return_value=None):
        try:
            from pqwave.models.fst_adapter import FstAdapter
            FstAdapter("/nonexistent.fst")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            msg = str(e)
            assert "fst2vcd" in msg, f"Expected message to mention fst2vcd, got: {msg}"
            assert "gtkwave" in msg, f"Expected message to mention gtkwave, got: {msg}"


def test_fst_adapter_custom_tool_path():
    """FstAdapter uses custom tool_path from settings."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    custom = "/opt/my/gtkwave/bin/fst2vcd"
    state.tool_paths["fst2vcd"] = custom

    # Mock subprocess.run to succeed and create a minimal VCD file
    vcd_content = (
        "$date test $end\n"
        "$version test $end\n"
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n#10\n1!\n"
    )

    def fake_run(args, **kwargs):
        # Write the VCD to the output file
        import os
        if args[0] == custom:
            with open(args[3], 'w') as f:
                f.write(vcd_content)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        from pqwave.models.fst_adapter import FstAdapter
        adapter = FstAdapter("/test.fst")
        names = adapter.get_variable_names()
        assert "clk" in names, f"Expected 'clk' in signal names, got: {names}"
        data = adapter.get_variable_data("clk")
        assert data is not None
        assert len(data) > 0

    # Cleanup
    state.tool_paths["fst2vcd"] = ""


def test_fst_adapter_conversion_failure():
    """FstAdapter raises when fst2vcd conversion fails."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    state.tool_paths["fst2vcd"] = ""

    def fake_run(*args, **kwargs):
        raise Exception("Simulated conversion failure")

    with patch("shutil.which", return_value="/usr/bin/fst2vcd"), \
         patch("subprocess.run", side_effect=fake_run):
        try:
            from pqwave.models.fst_adapter import FstAdapter
            FstAdapter("/test.fst")
            assert False, "Should have raised"
        except Exception as e:
            assert "test.fst" in str(e).lower() or "conversion" in str(e).lower(), \
                f"Expected error about conversion, got: {e}"
```

Run: `venv/bin/python -m pytest pqwave/tests/test_fst_adapter.py::test_fst_adapter_missing_tool -v`
Expected: FAIL — no module named `pqwave.models.fst_adapter`

- [ ] **Step 2: Implement FstAdapter**

Create `pqwave/models/fst_adapter.py`:

```python
"""FstAdapter — parse FST files by converting to VCD via fst2vcd."""

import os
import shutil
import subprocess
import tempfile
import logging

import numpy as np

from pqwave.models.state import ApplicationState
from pqwave.models.vcdfile import VcdFile

logger = logging.getLogger(__name__)


class FstAdapter:
    """Adapter that converts .fst files to VCD and parses them via VcdFile.

    Requires fst2vcd from gtkwave. Install via:
        sudo apt install gtkwave
    """

    def __init__(self, filename: str):
        self.filename = filename
        self._vcd_file = None
        tool = self._resolve_tool()
        self._convert_and_parse(tool)

    def _resolve_tool(self) -> str:
        """Resolve fst2vcd path: settings override first, then $PATH."""
        state = ApplicationState()
        custom = state.tool_paths.get("fst2vcd", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("fst2vcd")
        if found:
            return found
        raise FileNotFoundError(
            "fst2vcd not found. Install gtkwave and make sure fst2vcd "
            "is in $PATH or set the location of your gtkwave installation "
            "in Edit > Settings"
        )

    def _convert_and_parse(self, tool: str) -> None:
        """Convert .fst to temp VCD and parse it."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".vcd", prefix="pqwave_fst_")
        os.close(tmp_fd)
        try:
            result = subprocess.run(
                [tool, self.filename, "-o", tmp_path],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to convert {self.filename} to VCD: {result.stderr.strip()}"
                )
            self._vcd_file = VcdFile(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @property
    def datasets(self) -> list:
        if self._vcd_file is None:
            return []
        return self._vcd_file.datasets

    def get_variable_names(self, dataset_idx: int = 0) -> list:
        if self._vcd_file is None:
            return []
        return self._vcd_file.get_variable_names(dataset_idx)

    def get_variable_data(self, name: str, dataset_idx: int = 0) -> np.ndarray:
        if self._vcd_file is None:
            return None
        return self._vcd_file.get_variable_data(name, dataset_idx)

    def get_num_points(self, dataset_idx: int = 0) -> int:
        if self._vcd_file is None:
            return 0
        return self._vcd_file.get_num_points(dataset_idx)
```

- [ ] **Step 3: Run tests — should pass**

```bash
venv/bin/python -m pytest pqwave/tests/test_fst_adapter.py -v
```
Expected: 3 PASS

- [ ] **Step 4: Commit**

```bash
git add pqwave/models/fst_adapter.py pqwave/tests/test_fst_adapter.py
git commit -m "feat: add FstAdapter for parsing FST files via fst2vcd

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Create GhwAdapter

**Files:**
- Create: `pqwave/models/ghw_adapter.py`
- Create: `pqwave/tests/test_ghw_adapter.py`

- [ ] **Step 1: Write failing test**

Create `pqwave/tests/test_ghw_adapter.py`:

```python
"""Tests for GhwAdapter"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_ghw_adapter_missing_tool():
    """GhwAdapter raises when ghwdump is not found."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    state.tool_paths["ghwdump"] = ""

    with patch("shutil.which", return_value=None):
        try:
            from pqwave.models.ghw_adapter import GhwAdapter
            GhwAdapter("/nonexistent.ghw")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            msg = str(e)
            assert "ghwdump" in msg, f"Expected message to mention ghwdump, got: {msg}"
            assert "GHDL" in msg, f"Expected message to mention GHDL, got: {msg}"


def test_ghw_adapter_custom_tool_path():
    """GhwAdapter uses custom tool_path from settings."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    custom = "/opt/ghdl/bin/ghwdump"
    state.tool_paths["ghwdump"] = custom

    vcd_content = (
        "$date test $end\n"
        "$version test $end\n"
        "$timescale 1ns $end\n"
        "$scope module top $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "#0\n0!\n#10\n1!\n"
    )

    def fake_run(args, **kwargs):
        if args[0] == custom:
            out = kwargs.get("stdout")
            if out is not None:
                out.write(vcd_content)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        from pqwave.models.ghw_adapter import GhwAdapter
        adapter = GhwAdapter("/test.ghw")
        names = adapter.get_variable_names()
        assert "clk" in names, f"Expected 'clk' in signal names, got: {names}"

    state.tool_paths["ghwdump"] = ""


def test_ghw_adapter_conversion_failure():
    """GhwAdapter raises when ghwdump conversion fails."""
    from unittest.mock import patch
    from pqwave.models.state import ApplicationState

    state = ApplicationState()
    state.tool_paths["ghwdump"] = ""

    def fake_run(*args, **kwargs):
        raise Exception("Simulated conversion failure")

    with patch("shutil.which", return_value="/usr/bin/ghwdump"), \
         patch("subprocess.run", side_effect=fake_run):
        try:
            from pqwave.models.ghw_adapter import GhwAdapter
            GhwAdapter("/test.ghw")
            assert False, "Should have raised"
        except Exception as e:
            assert "test.ghw" in str(e).lower() or "conversion" in str(e).lower(), \
                f"Expected error about conversion, got: {e}"
```

Run: `venv/bin/python -m pytest pqwave/tests/test_ghw_adapter.py::test_ghw_adapter_missing_tool -v`
Expected: FAIL — no module named `pqwave.models.ghw_adapter`

- [ ] **Step 2: Implement GhwAdapter**

Create `pqwave/models/ghw_adapter.py`:

```python
"""GhwAdapter — parse GHW files by converting to VCD via ghwdump."""

import os
import shutil
import subprocess
import tempfile
import logging

import numpy as np

from pqwave.models.state import ApplicationState
from pqwave.models.vcdfile import VcdFile

logger = logging.getLogger(__name__)


class GhwAdapter:
    """Adapter that converts .ghw files to VCD and parses them via VcdFile.

    Requires ghwdump from GHDL. Install GHDL to get ghwdump.
    """

    def __init__(self, filename: str):
        self.filename = filename
        self._vcd_file = None
        tool = self._resolve_tool()
        self._convert_and_parse(tool)

    def _resolve_tool(self) -> str:
        """Resolve ghwdump path: settings override first, then $PATH."""
        state = ApplicationState()
        custom = state.tool_paths.get("ghwdump", "")
        if custom and os.path.isfile(custom):
            return custom
        found = shutil.which("ghwdump")
        if found:
            return found
        raise FileNotFoundError(
            "ghwdump not found. Install GHDL and make sure ghwdump "
            "is in $PATH or set the location of your GHDL installation "
            "in Edit > Settings"
        )

    def _convert_and_parse(self, tool: str) -> None:
        """Convert .ghw to temp VCD and parse it."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".vcd", prefix="pqwave_ghw_")
        os.close(tmp_fd)
        try:
            with open(tmp_path, 'w') as out:
                result = subprocess.run(
                    [tool, self.filename, "--vcd"],
                    stdout=out,
                    stderr=subprocess.PIPE,
                    text=True
                )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to convert {self.filename} to VCD: "
                    f"{result.stderr.strip()}"
                )
            self._vcd_file = VcdFile(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @property
    def datasets(self) -> list:
        if self._vcd_file is None:
            return []
        return self._vcd_file.datasets

    def get_variable_names(self, dataset_idx: int = 0) -> list:
        if self._vcd_file is None:
            return []
        return self._vcd_file.get_variable_names(dataset_idx)

    def get_variable_data(self, name: str, dataset_idx: int = 0) -> np.ndarray:
        if self._vcd_file is None:
            return None
        return self._vcd_file.get_variable_data(name, dataset_idx)

    def get_num_points(self, dataset_idx: int = 0) -> int:
        if self._vcd_file is None:
            return 0
        return self._vcd_file.get_num_points(dataset_idx)
```

Note: `ghwdump` sends VCD to stdout with `--vcd` (no `-o` option), so we pipe stdout to the temp file.

- [ ] **Step 3: Run tests — should pass**

```bash
venv/bin/python -m pytest pqwave/tests/test_ghw_adapter.py -v
```
Expected: 3 PASS

- [ ] **Step 4: Commit**

```bash
git add pqwave/models/ghw_adapter.py pqwave/tests/test_ghw_adapter.py
git commit -m "feat: add GhwAdapter for parsing GHW files via ghwdump

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Add .fst and .ghw dispatch in SessionAPI

**Files:**
- Modify: `pqwave/session/api.py:499-509`

- [ ] **Step 1: Update the load() method**

In `SessionAPI.load()`, change the extension dispatch block:

```python
ext = os.path.splitext(path)[1].lower()
abs_path = os.path.abspath(path)

if ext == ".json":
    info = self._load_project(abs_path)
elif ext == ".vcd":
    info = self._load_vcd(abs_path)
elif ext == ".fst":
    info = self._load_fst(abs_path)
elif ext == ".ghw":
    info = self._load_ghw(abs_path)
else:
    info = self._load_raw(abs_path)

self._state.source_files.append(SourceFile(path=abs_path, file_type=ext.lstrip(".")))
return info
```

- [ ] **Step 2: Add _load_fst and _load_ghw methods**

Add these methods after `_load_vcd`:

```python
def _load_fst(self, path: str) -> dict:
    from pqwave.models.fst_adapter import FstAdapter
    from pqwave.models.dataset import Dataset

    fst = FstAdapter(path)
    dataset = Dataset(fst, 0)
    self._state.add_dataset(dataset)

    if not self._state.active_panel_id:
        self._state.register_panel("panel_0")

    if self._state.datasets:
        self._state.current_dataset_idx = len(self._state.datasets) - 1

    return {
        "file_type": "fst",
        "n_points": dataset.n_points,
        "n_variables": dataset.n_variables,
        "signals": dataset.get_variable_names(),
    }

def _load_ghw(self, path: str) -> dict:
    from pqwave.models.ghw_adapter import GhwAdapter
    from pqwave.models.dataset import Dataset

    ghw = GhwAdapter(path)
    dataset = Dataset(ghw, 0)
    self._state.add_dataset(dataset)

    if not self._state.active_panel_id:
        self._state.register_panel("panel_0")

    if self._state.datasets:
        self._state.current_dataset_idx = len(self._state.datasets) - 1

    return {
        "file_type": "ghw",
        "n_points": dataset.n_points,
        "n_variables": dataset.n_variables,
        "signals": dataset.get_variable_names(),
    }
```

- [ ] **Step 3: Verify import works**

```bash
venv/bin/python -c "from pqwave.session.api import SessionAPI; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add pqwave/session/api.py
git commit -m "feat: add .fst and .ghw file dispatch in SessionAPI.load()

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Run full test suite and verify no regressions

- [ ] **Step 1: Run all tests**

```bash
venv/bin/python -m pytest pqwave/tests/ -v --timeout=30 2>&1 | tail -30
```

- [ ] **Step 2: Verify all tests pass**

Check output for any failures. Address if needed.

- [ ] **Step 3: Run the app smoke test**

```bash
venv/bin/python pqwave.py --test 2>&1 | tail -20
```

- [ ] **Step 4: Commit any fixes if needed**

```bash
git add -A
git commit -m "chore: fix test regressions from multi-simulator support

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
