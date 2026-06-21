## Tasks

### Task 1: Create `bridge/qspice/` module skeleton

- Create `pqwave/bridge/qspice/__init__.py` with re-exports
- Create `pqwave/bridge/qspice/wrapper.py` with stub classes (no implementation yet)
- Verify: `python -c "from pqwave.bridge.qspice import QspiceBridgeRunner"` succeeds

### Task 2: Implement `resolve_qspice()`

- Implement the 5-level priority chain (env var → tool_paths → Wine prefixes → PATH → error)
- Implement `_wine_prefixes()` helper
- Add `"qspice"` entry to `ApplicationState.tool_paths` defaults (empty string)
- Write unit tests: each priority level, file-not-found, Windows native path
- Verify: function returns correct path for each priority level

### Task 3: Implement `QspiceBridgeRunner`

- Implement `run(netlist_path)` method following the spec
- Handle Wine detection (`sys.platform` check for native Windows)
- Implement timeout handling (default 300s, configurable)
- Implement `auto_open` with `PQWAVE_QSPICE_AUTO_OPEN` env var override
- Implement `_launch_pqwave()` following the same detached-subprocess pattern as `QucsBridgeRunner`
- Write unit tests with mocked subprocess
- Verify: `python -m pqwave.bridge.qspice.wrapper` can be imported without Qt

### Task 4: Add CLI entry point in `main.py`

- Add `--qspice-bridge` flag handling before argparse (same pattern as `--qucs-bridge`)
- Implement `_run_qspice_bridge()` function
- Netlist argument: take the first arg after `--qspice-bridge`, no suffix filtering
- Verify: `pqwave --qspice-bridge /nonexistent/path` → exits with FileNotFoundError

### Task 5: Add Settings UI field

- Add "QSPICE Simulator (QSPICE64.exe)" field to External Converter Paths settings
- Wire it to `ApplicationState.tool_paths["qspice"]`
- Verify: field appears in Settings dialog, value persists across restart

### Task 6: Integration test

- Create a minimal `.cir` netlist (DC op point, 1 transistor)
- If QSPICE is available under Wine, run full end-to-end test
- If not available, verify graceful error path
- Verify `.qraw` lands in netlist's directory (not a temp dir)
- Verify pqwave can open the resulting `.qraw`

### Task 7: Register in bridge package

- Add `QspiceBridgeRunner` to `pqwave/bridge/__init__.py` exports
- Update `CLAUDE.md` with the new bridge module documentation
