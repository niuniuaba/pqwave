## 1. KiCad C++ Handlers

- [ ] 1.1 Add handler declarations to `eeschema/api/api_handler_sch.h` — declare `handleGetSelection`, `handleClearSelection`, `handleAddToSelection`, `handleGetBoundingBox`
- [ ] 1.2 Register handlers in `eeschema/api/api_handler_sch.cpp` constructor — four `registerHandler<>()` calls
- [ ] 1.3 Implement `handleGetSelection` — validate doc, get `SCH_SELECTION_TOOL`, iterate selection, serialize items, return `SelectionResponse`
- [ ] 1.4 Implement `handleClearSelection` — validate doc, call `selectionTool->ClearSelection(false)`, return `Empty`
- [ ] 1.5 Implement `handleAddToSelection` — validate doc, resolve KIIDs via `getItemById()`, call `AddItemsToSel()`, refresh canvas, return `SelectionResponse`
- [ ] 1.6 Implement `handleGetBoundingBox` — validate doc, resolve KIIDs, compute bounding boxes, return `GetBoundingBoxResponse`
- [ ] 1.7 Add null-frame guards — return `AS_UNHANDLED` when `m_frame` is nullptr in all four handlers
- [ ] 1.8 Rebuild KiCad — `cd ~/Apps/kicad.git/build && make -j$(nproc)` (or appropriate build dir)
- [ ] 1.9 Verify handlers with kicad-python smoke test — connect, call each handler, confirm responses

## 2. pqwave IpcProbeClient Wiring

- [ ] 2.1 Update `IpcProbeClient.probe_net()` — resolve net name → KIIDs via `get_netlist()`, call `ClearSelection` + `AddToSelection`
- [ ] 2.2 Update `IpcProbeClient.probe_part()` — resolve refdes → KIID via `get_symbols()`, call `ClearSelection` + `AddToSelection`
- [ ] 2.3 Update `IpcProbeClient.clear()` — call `ClearSelection`
- [ ] 2.4 Handle net-not-found gracefully — log warning, don't crash

## 3. Selection Polling (KiCad → pqwave)

- [ ] 3.1 Add `_poll_selection()` method to `KiCadBridge` — call `GetSelection`, compare with last poll, identify changed nets
- [ ] 3.2 Add 500ms QTimer to MainWindow for KiCad selection polling — start on watch, stop on unwatch
- [ ] 3.3 Wire selection change to trace highlighting — when net "R1" is selected in Eeschema, highlight matching trace(s) in pqwave

## 4. Integration Testing

- [ ] 4.1 Manual test: probe pqwave → KiCad — click trace, right-click Probe in KiCad, verify net highlights
- [ ] 4.2 Manual test: probe KiCad → pqwave — click wire in Eeschema, verify matching trace highlights in pqwave
- [ ] 4.3 Manual test: cursor back-annotation — move Xa cursor, verify net highlight follows in Eeschema
- [ ] 4.4 Manual test: bridge not active — verify Probe in KiCad shows friendly message when no bridge

## 5. Future: Show Trace Numbers

- [ ] 5.1 *(Future)* Design position computation for text annotation placement
- [ ] 5.2 *(Future)* Implement text creation/cleanup via CreateItems/DeleteItems
- [ ] 5.3 *(Future)* Handle undo-stack pollution from programmatic text
