## Context

KiCad's IPC API uses a handler registry pattern. Each protobuf message type is mapped to a C++ method. The Pcbnew editor registers 20+ handlers including `GetSelection`, `AddToSelection`, `ClearSelection`, `GetBoundingBox`, and `RunAction`. The Eeschema editor registers 14 handlers covering data access and export — but none of the interactive selection handlers.

The four handlers we need already exist in Pcbnew (`pcbnew/api/api_handler_pcb.cpp`). They follow a simple pattern: validate the request, get the selection tool, iterate items, serialize to protobuf. The Eeschema equivalents use the same base classes (`SELECTION_TOOL`, `EDA_ITEM`) and the same protobuf messages — only the type names differ (`SCH_` instead of `PCB_`).

## Goals / Non-Goals

**Goals:**
- Port `GetSelection`, `AddToSelection`, `ClearSelection`, `GetBoundingBox` from Pcbnew to Eeschema IPC API
- Wire pqwave's existing `IpcProbeClient` to use these handlers for bidirectional cross-probe
- Maintain the existing kicad-python + PYTHONPATH setup for development

**Non-Goals:**
- `RunAction` handler — not needed; `AddToSelection` + `ClearSelection` is sufficient
- Show-trace-numbers (text annotations) — deferred to future work
- `RemoveFromSelection` — not needed for current use cases
- Upstreaming to KiCad mainline — local development fork only

## Decisions

### Decision 1: Direct port from Pcbnew, not redesign

**Choice:** Copy the Pcbnew implementations verbatim, changing only type names (`PCB_SELECTION_TOOL` → `SCH_SELECTION_TOOL`, `BOARD_ITEM` → `SCH_ITEM`, `checkForHeadless` → skip for GUI-only).

**Rationale:** The Pcbnew handlers are battle-tested. Eeschema's tool classes mirror Pcbnew's. No reason to redesign. The risk of introducing bugs by being creative is higher than the risk of not being idiomatic enough.

**Alternatives considered:**
- *Refactor into shared base class* — Cleaner but requires touching Pcbnew code and base class signatures. Increases scope and risk.
- *Write from scratch* — Unnecessary; the PCB implementations are 15-25 lines each.

### Decision 2: Selection-based cross-probe, not RunAction

**Choice:** Use `AddToSelection`/`ClearSelection` for cross-probe. Resolve net names to KIIDs via `get_netlist()`.

**Rationale:** `RunAction("eeschema.EditorControl.highlightNet")` highlights the net under the cursor position — not by net name. We'd need to programmatically move the cursor, which the IPC API can't do. `AddToSelection` accepts KIIDs directly and produces a clear visual highlight. The selection-based approach is simpler and more reliable.

### Decision 3: Poll GetSelection, don't subscribe to events

**Choice:** pqwave polls `GetSelection` every 500ms via QTimer to detect when the user clicks a net in Eeschema. No push-based event subscription.

**Rationale:** The IPC API has no push mechanism. Polling is the only option. 500ms is fast enough for user perception and light enough to avoid burdening the IPC socket.

### Decision 4: No headless check

**Choice:** Skip `checkForHeadless()` in the SCH handlers. Register unconditionally.

**Rationale:** The PCB handlers use `checkForHeadless()` to reject interactive commands in headless mode. The SCH handler doesn't have this method. For our local build, we only use GUI mode. If the handlers are upstreamed, the KiCad team can add the headless guard.

## Risks / Trade-offs

- **[Risk] `GetSelection` polling overhead** — 500ms polling adds constant IPC traffic. → **Mitigation:** Only poll when a KiCad bridge is active (file being watched). Stop polling on unwatch.
- **[Risk] `AddToSelection` changes KiCad undo state** — every selection change via API is an undoable action. → **Mitigation:** Acceptable for now. Users can undo normally. Future: investigate `BeginCommit`/`EndCommit` to batch changes.
- **[Risk] SCH handler registered but frame is null** — the headless constructor path (`API_HANDLER_SCH(context, nullptr)`) sets `m_frame = nullptr`. Selection methods dereference it. → **Mitigation:** Guard with `if(!m_frame) return error;` in each handler.
- **[Risk] `GetBoundingBox` may not be needed** — if text annotations are deferred, this handler has no consumer yet. → **Mitigation:** Include it anyway; it's 15 lines and we'll need it for show-trace-numbers.
