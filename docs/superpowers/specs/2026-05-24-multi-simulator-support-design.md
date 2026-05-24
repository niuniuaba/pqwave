# Multi-Simulator Support — Design

Date: 2026-05-24

## Overview

Extend pqwave to open output files from Xyce, Icarus Verilog, Verilator, and GHDL simulators. Passive parsing only — open files, display waveforms, run data analysis. No live simulator integration.

## Supported Formats

| Extension | Backend      | Simulators               | Status    |
|-----------|-------------|--------------------------|-----------|
| `.raw`    | RawFile     | ngspice, LTspice          | Existing   |
| `.raw`    | RawFile     | Xyce                     | **Fixed**  |
| `.qraw`   | RawFile     | QSPICE                   | Existing   |
| `.vcd`    | VcdFile     | iverilog, GHDL, Verilator | Existing   |
| `.fst`    | FstAdapter  | GHDL, Verilator          | **New**    |
| `.ghw`    | GhwAdapter  | GHDL                     | **New**    |

Analog traces (`.raw`, `.qraw`) and digital traces (`.vcd`, `.fst`, `.ghw`) follow existing rendering separation.

## Architecture

```
SessionAPI.load()
  ext in (".raw", ".qraw") → _load_raw() → RawFile → spicelib → Dataset
  ext == ".vcd"            → _load_vcd() → VcdFile → vcdvcd  → Dataset
  ext == ".fst"            → _load_fst() → FstAdapter → fst2vcd → VcdFile → Dataset
  ext == ".ghw"            → _load_ghw() → GhwAdapter → ghwdump → VcdFile → Dataset
```

No new class hierarchy. Each adapter is standalone with the same duck-type interface: `.datasets`, `.get_variable_names()`, `.get_variable_data()`, `.get_num_points()`.

## Component 1: Xyce Dialect Auto-Detection

**File:** `pqwave/models/rawfile.py`

**Problem:** spicelib auto-detects dialect by finding a `Command:` header line. Xyce (and Qucs-using-Xyce) files lack this line, causing `SpiceReadException`.

**Fix:** In `RawFile.parse()`, wrap the `RawRead(load_path)` call. On dialect detection failure, brute-force try `('ngspice', 'xyce')` dialects. Both use identical binary layouts — whichever accepts the header first wins.

```python
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

No new files, no header sniffing, no simulator guessing.

## Component 2: FST Adapter

**File:** `pqwave/models/fst_adapter.py` (new)

**Tool:** `fst2vcd` from gtkwave (`sudo apt install gtkwave`)

**Flow:**
1. Resolve tool path: check settings `tool_paths.fst2vcd`, fall back to `$PATH`
2. If tool not found, raise with install instructions
3. Convert `.fst` → temp `.vcd` via `fst2vcd input.fst -o output.vcd`
4. Parse temp VCD through `VcdFile`
5. Clean up temp file
6. Expose `.datasets`, `.get_variable_names()`, `.get_variable_data()`, `.get_num_points()`

## Component 3: GHW Adapter

**File:** `pqwave/models/ghw_adapter.py` (new)

**Tool:** `ghwdump` from GHDL

**Flow:** Same pattern as FstAdapter but uses `ghwdump input.ghw --vcd > output.vcd`.

## Component 4: Tool Path Resolution

**Files:** `pqwave/models/fst_adapter.py`, `pqwave/models/ghw_adapter.py`

Settings structure:
```python
"tool_paths": {
    "fst2vcd": null,   # null = use $PATH, or "/opt/gtkwave/bin/fst2vcd"
    "ghwdump": null
}
```

Each adapter resolves its own tool path during `__init__`:
1. Read `settings.tool_paths.<tool>` — if set to a non-null path, use it
2. Fall back to `shutil.which(<tool>)` — scan `$PATH`
3. Neither → raise `FileNotFoundError` with install instructions

Settings are read from `ApplicationState` (existing singleton). Custom paths are configured via Edit > Settings dialog (existing UI).

## Component 5: Error Messages

| Failure | Message |
|---------|---------|
| Tool not found | `fst2vcd not found. Install gtkwave and make sure fst2vcd is in $PATH or set the location of your gtkwave installation in Edit > Settings` |
| Conversion failed | `Failed to convert <filename> to VCD: <stderr>` |
| Parse error | Bubble up VcdFile/spicelib error as-is (existing error dialog) |

## Component 6: File Extension Dispatch

**File:** `pqwave/session/api.py` (modify)

Add `.fst` and `.ghw` to the extension dispatch in `load()`:

```python
elif ext == ".fst":
    info = self._load_fst(abs_path)
elif ext == ".ghw":
    info = self._load_ghw(abs_path)
```

New private methods `_load_fst()` and `_load_ghw()` follow the same structure as `_load_vcd()`.

## Test Plan

| Test | File | Approach |
|------|------|----------|
| Xyce dialect fallback | `test_rawfile.py` | Parse `tests/bridge_xyce.raw`, assert 10 variables, 499 points |
| FstAdapter parsing | `test_fst_adapter.py` | Mock `subprocess.run`, verify VcdFile receives VCD output |
| GhwAdapter parsing | `test_ghw_adapter.py` | Same pattern |
| Missing tool error | adapter tests | Assert `FileNotFoundError` with expected message |
| Tool path override | adapter tests | Assert custom path used when set in settings |
| End-to-end | Manual | Open `.fst`/`.ghw`/Xyce `.raw` in pqwave, verify waveforms render |

Unit tests mock subprocess — no real CLI tools needed in CI.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `pqwave/models/rawfile.py` | Modify | ~8 |
| `pqwave/models/fst_adapter.py` | Create | ~80 |
| `pqwave/models/ghw_adapter.py` | Create | ~80 |
| `pqwave/session/api.py` | Modify | ~30 |
