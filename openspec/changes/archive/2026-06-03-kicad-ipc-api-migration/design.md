## Context

The current `KiCadBridge` (built May 2026) shells out to `kicad-cli` for SPICE netlist export and parses `.kicad_sch` S-expression files with regex to extract `Sim.Pins` metadata. Cross-probe back-annotation was specified to use TCP port 4243 but was never functional — that port is KiCad's internal Eeschema↔Pcbnew channel, not a public API.

KiCad 9.0 introduced the IPC API (Protobuf over Unix socket/NNG), initially PCB-editor only. KiCad 10 expanded coverage. KiCad 11 (currently 10.99.0-dev) adds full schematic support: netlist export, symbol/pin/net querying, hierarchical navigation, plot exports, BOM export, and hit-testing. The `kicad-python` library (official KiCad team bindings) has an open MR (!46) adding `Schematic` class wrappers for all these capabilities.

We have a local build of KiCad 10.99.0 at `/home/wing/Apps/kicad` and a patched `kicad-python` clone at `/home/wing/Apps/kicad-python.git` with MR !46 applied. Smoke tests confirm all schematic IPC API methods work against the local build.

## Goals / Non-Goals

**Goals:**
- Replace `subprocess.run(["kicad-cli", "sch", "export", "netlist", ...])` with `schematic.export_netlist(SNF_SPICE)` via IPC API
- Replace regex-based `.kicad_sch` parsing with `schematic.get_symbols()` for structured Sim.Pins extraction
- Implement working cross-probe via IPC API (the primary motivation — port 4243 never worked)
- Gracefully degrade to `kicad-cli` when IPC API is unavailable (KiCad < 10, or API disabled)
- Make `kicad-python` a user-installed prerequisite, detected lazily at runtime

**Non-Goals:**
- Adding `kicad-python` to pqwave's `setup.py`/`requirements.txt`
- Headless simulation via IPC API (keep ngspice subprocess — IPC doesn't run SPICE)
- Schematic editing or item creation via IPC API (read-only: query + export + cross-probe)
- Plot export or BOM generation (out of scope for pqwave's waveform-viewing mission)
- Modifying the Lepton-EDA or xschem bridges

## Decisions

### Decision 1: IPC API primary, kicad-cli fallback

**Choice:** Two-tier netlist export: try IPC API first, fall back to `kicad-cli` subprocess if the IPC connection fails or `kicad-python` is not installed.

**Rationale:** Maintains backward compatibility with KiCad 8/9 users who can't use the IPC API, while giving KiCad 10+ users the full experience (cross-probe, structured data). The `kicad-cli` fallback code already exists and is tested — we're adding an alternative path, not removing one.

**Alternatives considered:**
- *IPC-only, drop kicad-cli* — would break all KiCad 8/9 users. Too aggressive.
- *Keep kicad-cli, add IPC for cross-probe only* — would bifurcate the code path. Using IPC for everything when available is cleaner.

### Decision 2: kicad-python as user prerequisite, detected by functionality

**Choice:** `kicad-python` is NOT listed in `setup.py` or `requirements.txt`. pqwave detects it at runtime via a lazy `import kipy` when the user initiates KiCad integration. Compatibility is verified by **functionality checks** (`hasattr(kipy.KiCad, 'get_schematic')`, `hasattr(schematic, 'export_netlist')`), NOT by version number comparison. If the import fails or required APIs are absent, a clear error message tells the user what to install.

**Rationale:** `kicad-python` depends on `protobuf`, `pynng` (which needs a C compiler), and is tightly version-coupled to the installed KiCad. Forcing this on all pqwave users — including those who only use xschem, Lepton, or raw file viewing — is unnecessary. Users who want KiCad integration opt into the dependency.

Functionality checks are superior to version checks because:
- kicad-python's published version (0.7.1 on PyPI) may lag behind the APIs available in its Git main branch
- A user might install from Git (which reports 0.0.0) but have all required functionality
- Checking for the actual methods we need (`get_schematic`, `export_netlist`) is robust against version numbering quirks and future API renames

**Alternatives considered:**
- *Version number check (`__version__ >= "0.8.0"`)* — fragile; PyPI package is 0.7.1 while Git main is 0.0.0, yet Git main has the APIs we need. Rejected in favor of `hasattr`.
- *List as optional extra (`pip install pqwave[kicad]`)* — idiomatic but adds packaging complexity. The lazy-import-with-clear-error approach is simpler and sufficient for a tool aimed at technical users.
- *Bundle kicad-python* — version coupling nightmare. KiCad and kicad-python version locks would force pqwave releases to track KiCad releases.

### Decision 3: Connection lifecycle

**Choice:** Lazy connection on first API call, reused for the session lifetime. A single `kipy.KiCad` instance stored on `KiCadBridge`. Connection uses the `KICAD_API_SOCKET` environment variable (set by KiCad when launching plugins) or falls back to the default platform socket path.

```
  User opens KiCad schematic
       │
  pqwave calls export_netlist()
       │
  KiCadBridge._ensure_ipc()  ← first call: import kipy, connect
       │                     ← subsequent calls: reuse existing connection
  schematic.export_netlist(SNF_SPICE)
       │
  User saves schematic
       │
  pqwave calls export_netlist() again — same connection, no reconnect
```

**Rationale:** Persistent connection avoids the overhead of re-establishing the Unix socket + Protobuf handshake per operation. If the connection drops (KiCad closed), `_ensure_ipc()` reconnects automatically.

### Decision 4: Cross-probe via RunAction

**Choice:** Use `kicad.run_action("eeschema.InteractiveSelection.SelectItem")` and related actions for cross-probe, rather than the legacy TCP port 4243 protocol.

**Rationale:** The IPC API's `RunAction` mechanism is the officially supported way to trigger editor commands. The exact action names need discovery (KiCad's action registry is not documented as a stable API), but `run_action` is explicitly provided for this purpose and will be maintained.

**Alternatives considered:**
- *Use `AddToSelection` / `ClearSelection` IPC commands* — more structured than `run_action`, but `AddToSelection` takes KIIDs (UUIDs), not net names. We'd need to resolve net name → KIID first via `get_netlist()`.
- *Keep TCP 4243* — never worked, not a public API.

**Fallback plan:** If `run_action` proves unreliable, implement net-name → KIID resolution via `get_netlist()` and use `AddToSelection` + `ClearSelection` with the resolved KIIDs.

### Decision 5: Conditional StripSlashes

**Choice:** `StripSlashes` fix becomes conditional — applied only when the exported netlist actually contains leading slashes on net names. Rather than guessing based on KiCad version, we inspect the exported netlist: if no line matches the pattern `\s/[A-Za-z_]`, skip the fix. This is a **functional check**, not a version check.

**Rationale:** Applying a regex fix that's no longer needed risks corrupting net names that legitimately contain `/` characters (e.g., hierarchical net names like `/sheet1/net_a` which are intentionally multi-level).

## Risks / Trade-offs

- **[Risk] kicad-python missing required APIs** — the installed kicad-python may lack `get_schematic()` or `export_netlist()` (e.g., PyPI 0.7.1). → **Mitigation:** Functionality checks at import time (`hasattr`); clear error message with specific install command (`pip install git+https://gitlab.com/kicad/code/kicad-python.git`).
- **[Risk] run_action API instability** — action names are explicitly NOT a stable API per KiCad docs. → **Mitigation:** Fall back to `AddToSelection`/`ClearSelection` with KIID resolution if action names break.
- **[Risk] IPC API server must be enabled** — disabled by default in KiCad preferences. → **Mitigation:** Detection code checks if the socket exists; clear error message telling user how to enable it.
- **[Trade-off] Two code paths** — maintaining both IPC and kicad-cli paths adds complexity. → Accepted: the kicad-cli path is already written and tested; the IPC path is the future; the kicad-cli path eventually becomes dead code as KiCad 8/9 age out.
