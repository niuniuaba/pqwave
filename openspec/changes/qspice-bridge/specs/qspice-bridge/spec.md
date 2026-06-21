## QSPICE Bridge — Specification

### SPEC-1: QSPICE Path Resolution

`resolve_qspice()` SHALL locate `QSPICE64.exe` (or `QSPICE.exe` as fallback) using the following priority chain:

1. `PQWAVE_QSPICE` environment variable — if set and the file exists, return it
2. `ApplicationState().tool_paths.get("qspice")` — if configured and file exists, return it
3. Filesystem search under common Wine prefixes (`~/.wine`, `~/.wine32`, `~/.wine64`, `~/Games/qspice`) for `drive_c/Program Files/QSPICE/QSPICE64.exe` or `QSPICE.exe`
4. `shutil.which("QSPICE64.exe")` or `shutil.which("QSPICE.exe")` — works when QSPICE is on Wine's PATH
5. Raise `FileNotFoundError` with a descriptive message listing what was tried

The function SHALL NOT import Qt. It SHALL be importable from headless contexts.

### SPEC-2: Simulator Invocation

`QspiceBridgeRunner.run(netlist_path)` SHALL:

1. Verify `netlist_path` exists (raise `FileNotFoundError` if not)
2. Resolve QSPICE path via `resolve_qspice()`
3. Detect `wine` on PATH (unless running natively on Windows, detected via `sys.platform == "win32"` — then invoke QSPICE64.exe directly)
4. Set working directory to `os.path.dirname(os.path.abspath(netlist_path))`
5. Invoke the simulator with only the netlist filename (not full path), so QSPICE writes `.qraw` to the netlist's directory
6. Wait for process completion with a default timeout of 300 seconds
7. On non-zero exit: print stdout/stderr to stderr, return the exit code, do NOT launch GUI
8. On success: construct expected `.qraw` path as `os.path.splitext(netlist_path)[0] + ".qraw"`, verify it exists, return 0

### SPEC-3: CLI Entry Point

`pqwave --qspice-bridge <netlist_path>` SHALL:

1. Extract the netlist path from the first argument after `--qspice-bridge`
2. Instantiate `QspiceBridgeRunner` and call `.run(netlist_path)`
3. On success, if `auto_open=True` (default, suppressed by `PQWAVE_QSPICE_AUTO_OPEN=0`), launch pqwave GUI with the `.qraw` path
4. Return the exit code

The netlist path SHALL NOT be filtered by suffix. Any filename is accepted.

### SPEC-4: Tool Path Configuration

`ApplicationState.tool_paths` SHALL accept a `"qspice"` key storing a string path to `QSPICE64.exe`.

The Settings > External Converter Paths dialog SHALL expose a "QSPICE Simulator (QSPICE64.exe)" field for this path.

The field SHALL be optional — if empty, `resolve_qspice()` falls through to auto-detection.

### SPEC-5: spicelib Fallback + QUX Reader

The existing spicelib-based `RawFile` parser SHALL remain as fallback. When QSPICE is installed, `RawFile.parse()` SHALL prefer QUX.exe -Export for data extraction (official QSPICE path, no encoding issues), falling back to spicelib transparently when QUX is unavailable or the file is non-QSPICE.

### SPEC-6: No PyQSPICE Dependency

The implementation SHALL NOT import, copy, or depend on any code from the PyQSPICE package. All QSPICE interaction goes through subprocess calls to `QSPICE64.exe` / `QUX.exe`.
