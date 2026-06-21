## Architecture

### Layer Map

```
pqwave/bridge/qspice/
├── __init__.py          # Re-exports: QspiceBridgeRunner, resolve_qspice
└── wrapper.py           # Headless runner — NO Qt imports

pqwave/main.py           # New CLI flag: --qspice-bridge
pqwave/models/state.py   # New tool_paths entry: "qspice"
pqwave/ui/               # New field in External Converter Paths settings
```

### Dependency Direction

```
main.py → bridge/qspice/wrapper.py → subprocess (wine + QSPICE64.exe)
                                    → pqwave.models.rawfile (for .qraw opening)
                                    → pqwave.models.state (for tool_paths)
```

`wrapper.py` MUST NOT import Qt. It runs headless, before QApplication exists (same pattern as `bridge/qucs_s/wrapper.py`).

## Component Design

### 1. `resolve_qspice()` — QSPICE Path Resolution

Priority order:
1. `PQWAVE_QSPICE` environment variable
2. `ApplicationState().tool_paths.get("qspice", "")`
3. Filesystem search under common Wine prefixes
4. `shutil.which("QSPICE64.exe")` (works under Wine if in PATH)
5. Raise `FileNotFoundError`

```python
def resolve_qspice() -> str:
    """Resolve QSPICE64.exe path with priority chain."""
    env_path = os.environ.get("PQWAVE_QSPICE", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    state = ApplicationState()
    configured = state.tool_paths.get("qspice", "")
    if configured and os.path.isfile(configured):
        return configured

    # Search common Wine prefixes
    for prefix in _wine_prefixes():
        candidate = os.path.join(
            prefix, "drive_c", "Program Files", "QSPICE", "QSPICE64.exe"
        )
        if os.path.isfile(candidate):
            return candidate
        # Also try QSPICE.exe (32-bit)
        candidate = os.path.join(
            prefix, "drive_c", "Program Files", "QSPICE", "QSPICE.exe"
        )
        if os.path.isfile(candidate):
            return candidate

    found = shutil.which("QSPICE64.exe") or shutil.which("QSPICE.exe")
    if found:
        return found

    raise FileNotFoundError(
        "QSPICE64.exe not found. Install QSPICE under Wine or set "
        "PQWAVE_QSPICE environment variable."
    )
```

`_wine_prefixes()` returns common Wine prefix paths:
```python
def _wine_prefixes() -> list[str]:
    return [
        os.path.expanduser("~/.wine"),
        os.path.expanduser("~/.wine32"),
        os.path.expanduser("~/.wine64"),
        os.path.expanduser("~/Games/qspice"),  # common QSPICE-specific prefix
    ]
```

### 2. `QspiceBridgeRunner` — Simulation Orchestrator

```python
class QspiceBridgeRunner:
    """Run a QSPICE simulation from a netlist and return the .qraw path."""

    def __init__(self, qspice_path: str = "", auto_open: bool = True):
        self._qspice_path = qspice_path
        self._auto_open = auto_open

    def run(self, netlist_path: str) -> int:
        """Full pipeline:
        1. Resolve QSPICE and wine paths
        2. Run simulator in netlist's directory
        3. Wait for .qraw output
        4. Optionally launch pqwave GUI with .qraw
        Returns exit code (0 = success).
        """
```

Key behaviors:
- **Working directory = netlist's directory** — `.qraw` lands alongside the netlist, matching QSPICE's normal behavior
- `subprocess.run()` with configurable timeout (default 300s)
- Captures stdout/stderr for error reporting
- If `auto_open=True`, launches `pqwave <qraw_path>` after successful simulation
- Respects `PQWAVE_QSPICE_AUTO_OPEN=0` env var to suppress GUI launch

### 3. CLI Entry Point

```bash
# Run simulation from netlist, open results in pqwave
pqwave --qspice-bridge /path/to/circuit.cir

# With explicit QSPICE path
PQWAVE_QSPICE=~/.wine/drive_c/.../QSPICE64.exe pqwave --qspice-bridge circuit.cir

# Suppress GUI auto-open
PQWAVE_QSPICE_AUTO_OPEN=0 pqwave --qspice-bridge circuit.cir
```

The netlist file argument is positional — it's whatever follows `--qspice-bridge` in argv. No suffix assumption (`.cir`, `.sp`, `.net`, or no extension are all valid).

### 4. Tool Path Configuration

In `ApplicationState.tool_paths`:
```python
"qspice": "/home/user/.wine/drive_c/Program Files/QSPICE/QSPICE64.exe",
```

Settable via: **Settings > External Converter Paths > QSPICE Simulator (QSPICE64.exe)**.

No dedicated setup wizard — the existing Settings dialog handles path configuration, and `resolve_qspice()` auto-detects without configuration in the common case.

### 5. QUX-based `.qraw` Reader (Optional Enhancement)

When QSPICE is installed, pqwave *may* use `QUX.exe -Export` for data extraction instead of spicelib's binary parser:

```bash
wine QUX.exe -Export result.qraw "V(out),I(R1)" 4999 CSV -stdout
```

This produces CSV via stdout — the **official** QSPICE data export path with guaranteed-correct encoding.

**Important constraints**:
- QUX is the **primary** `.qraw` reader when QSPICE is installed — spicelib is the fallback
- QUX path is resolved from the same directory as `QSPICE64.exe` (they ship together)
- Skipped for non-QSPICE files (header detection) and for files without QSPICE installed

## Data Flow

```
User provides netlist (any extension or none)
        │
        ▼
pqwave --qspice-bridge /path/to/circuit.cir
        │
        ▼
QspiceBridgeRunner.run(netlist_path)
  1. resolve_qspice() → /home/user/.wine/.../QSPICE64.exe
  2. resolve_wine()    → /usr/bin/wine
  3. netlist_dir = os.path.dirname(netlist_path)
     netlist_base = os.path.splitext(os.path.basename(netlist_path))[0]
  4. subprocess.run([wine, qspice64, os.path.basename(netlist_path)],
                    cwd=netlist_dir, timeout=300)
  5. qraw_path = os.path.join(netlist_dir, netlist_base + ".qraw")
  6. Verify qraw_path exists
        │
        ▼
pqwave GUI opens qraw_path
  (via existing RawFile parser → spicelib)
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| QSPICE not found | `FileNotFoundError` with resolution chain details |
| Wine not found | `FileNotFoundError` with "install wine" message |
| Netlist doesn't exist | `FileNotFoundError` before invoking simulator |
| Simulation fails (non-zero exit) | Print stdout/stderr, return exit code, don't launch GUI |
| `.qraw` not produced after exit | Warn with stderr, return error code |
| Simulation timeout | `subprocess.TimeoutExpired` → kill process, warn user |

## Platform Coverage

| OS | Simulator | Notes |
|----|-----------|-------|
| Linux (Wine) | `wine QSPICE64.exe` | Primary target |
| Windows (native) | Direct `.exe` call | Incidental — `resolve_qspice()` detects native path |
| macOS (Wine) | Untested | Not a priority but should work if Wine + QSPICE are present |
