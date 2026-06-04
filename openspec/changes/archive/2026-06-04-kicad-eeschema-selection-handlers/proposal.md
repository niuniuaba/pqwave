## Why

The KiCad IPC API for Eeschema (KiCad 10.99.0) supports data access and export but lacks the interactive selection handlers that Pcbnew already has. This blocks all cross-probe between pqwave and KiCad Eeschema — selecting a net in Eeschema to find it in pqwave, probing a trace in pqwave to highlight it in Eeschema, and cursor-driven back-annotation. These same handlers already exist in Pcbnew (`pcbnew/api/api_handler_pcb.cpp`); porting them to Eeschema is ~80 lines of C++ following the exact same patterns.

## What Changes

- **Add `GetSelection` handler** to Eeschema IPC API — returns the currently selected schematic items as protobuf. Enables: click net in Eeschema → pqwave identifies the net and plots it.
- **Add `AddToSelection` handler** to Eeschema IPC API — adds items by KIID to the schematic selection. Enables: pqwave probe → KiCad highlights the net.
- **Add `ClearSelection` handler** to Eeschema IPC API — clears the schematic selection. Enables: clearing previous probe highlights before selecting a new net.
- **Add `GetBoundingBox` handler** to Eeschema IPC API — returns bounding boxes for schematic items. Needed for future text annotation placement.
- **Wire pqwave's IpcProbeClient** to use these handlers (net name → KIID resolution via `get_netlist()` → `AddToSelection`).
- **Add polling for Eeschema selection** in pqwave (500ms QTimer → `GetSelection` → resolve net name → plot matching trace).
- **Mark show-trace-numbers as future work** — placing text annotations with trace values via `CreateItems`/`DeleteItems` (handlers already exist, needs position computation and undo-stack management).

## Capabilities

### New Capabilities

- `kicad-schematic-selection-api`: Four new IPC handlers in KiCad Eeschema (`GetSelection`, `AddToSelection`, `ClearSelection`, `GetBoundingBox`), plus pqwave-side wiring to use them for bidirectional cross-probe.

### Modified Capabilities

*None — this is a new capability. Existing pqwave bridge code (IpcProbeClient, context menus, cursor back-annotation) was already written and waiting for these handlers.*

## Impact

- **KiCad source** (`eeschema/api/api_handler_sch.h`, `eeschema/api/api_handler_sch.cpp`): ~80 lines of C++ added. All four handlers follow existing patterns from `pcbnew/api/api_handler_pcb.cpp`.
- **pqwave bridge** (`pqwave/bridge/kicad/cross_probe.py`): Update `IpcProbeClient` to resolve net names to KIIDs via `get_netlist()` and use `AddToSelection`/`ClearSelection`. Add selection polling.
- **Build**: KiCad must be rebuilt after handler changes. Incremental build ~30s for the changed file.
- **Future**: Show-trace-numbers via `CreateItems`/`DeleteItems` for text annotations is explicitly deferred. Handlers already exist in KiCad; the pqwave-side position computation and undo management needs separate design.
