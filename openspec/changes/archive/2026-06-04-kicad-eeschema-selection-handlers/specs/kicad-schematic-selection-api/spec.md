# kicad-schematic-selection-api Specification

## Purpose
Defines the four IPC handlers added to KiCad Eeschema for schematic selection and bounding box queries, plus the pqwave-side wiring that uses them for bidirectional cross-probe.

## ADDED Requirements

### Requirement: GetSelection handler in Eeschema

The system SHALL register a `GetSelection` IPC handler in `API_HANDLER_SCH` that returns the currently selected schematic items.

The handler SHALL:
- Validate the document header (must be `DOCTYPE_SCHEMATIC`)
- Get `SCH_SELECTION_TOOL` from the tool manager
- Iterate the current selection and serialize each item via `item->Serialize(google::protobuf::Any&)`
- Return a `SelectionResponse` containing the serialized items

If `m_frame` is null (headless constructor path), the handler SHALL return `AS_UNHANDLED`.

#### Scenario: Items selected in Eeschema
- **WHEN** the user selects a wire and a symbol in Eeschema, and pqwave calls `GetSelection`
- **THEN** the response SHALL contain two items (one wire, one symbol) serialized as protobuf

#### Scenario: Nothing selected
- **WHEN** no items are selected in Eeschema, and pqwave calls `GetSelection`
- **THEN** the response SHALL contain zero items

#### Scenario: Headless mode
- **WHEN** `GetSelection` is called in headless mode (no frame)
- **THEN** the handler SHALL return `AS_UNHANDLED`

---

### Requirement: AddToSelection handler in Eeschema

The system SHALL register an `AddToSelection` IPC handler in `API_HANDLER_SCH` that adds schematic items to the current selection by KIID.

The handler SHALL:
- Validate the document header
- Resolve each KIID to an `SCH_ITEM*` via `getItemById()`
- Add resolved items to the selection via `selectionTool->AddItemsToSel()`
- Refresh the canvas
- Return a `SelectionResponse` containing the updated selection

If `m_frame` is null, the handler SHALL return `AS_UNHANDLED`.

#### Scenario: Add net items to selection
- **WHEN** pqwave resolves net "r1" to KIIDs [uuid1, uuid2] via `get_netlist()`, then calls `AddToSelection([uuid1, uuid2])`
- **THEN** the items for net "r1" SHALL appear selected (highlighted) in Eeschema
- **THEN** the response SHALL contain the updated selection

#### Scenario: KIID not found
- **WHEN** a KIID in the request does not correspond to any existing schematic item
- **THEN** that KIID SHALL be silently skipped (no error)

---

### Requirement: ClearSelection handler in Eeschema

The system SHALL register a `ClearSelection` IPC handler in `API_HANDLER_SCH` that clears the current schematic selection.

The handler SHALL:
- Validate the document header
- Call `selectionTool->ClearSelection(false)`
- Return an empty response

If `m_frame` is null, the handler SHALL return `AS_UNHANDLED`.

#### Scenario: Clear before probing a new net
- **WHEN** the Xa cursor moves to a new trace, pqwave calls `ClearSelection` before `AddToSelection` for the new net
- **THEN** the previous net's highlight SHALL be removed
- **THEN** the new net SHALL be the only selected items

---

### Requirement: GetBoundingBox handler in Eeschema

The system SHALL register a `GetBoundingBox` IPC handler in `API_HANDLER_SCH` that returns bounding boxes for specified schematic items by KIID.

The handler SHALL:
- Validate the document header
- Resolve each KIID to an `SCH_ITEM*` via `getItemById()`
- Compute the bounding box via `item->GetBoundingBox()`
- Return a `GetBoundingBoxResponse` mapping KIIDs to boxes

If `m_frame` is null, the handler SHALL return `AS_UNHANDLED`.

#### Scenario: Get position of a net's items
- **WHEN** pqwave calls `GetBoundingBox([uuid1])` for a net item
- **THEN** the response SHALL contain the bounding box, enabling position computation for future text annotation placement

---

### Requirement: Net name to KIID resolution for cross-probe

The pqwave `IpcProbeClient` SHALL resolve net names to KIIDs by calling `schematic.get_netlist()` via the IPC API, then use `AddToSelection` to highlight the resolved items.

The client SHALL:
- Call `get_netlist()` and cache the result (refresh on each probe to handle schematic edits)
- Match net names case-insensitively
- Fall back to substring matching if exact match fails
- Call `ClearSelection` before `AddToSelection` to ensure only the target net is highlighted

#### Scenario: Probe net by name
- **WHEN** `probe_net("r1")` is called
- **THEN** the netlist SHALL be queried for net "r1"
- **THEN** `ClearSelection` SHALL be called
- **THEN** `AddToSelection` SHALL be called with the net's KIIDs
- **THEN** the net SHALL be highlighted in Eeschema

#### Scenario: Net not found
- **WHEN** `probe_net("nonexistent")` is called and no net matches
- **THEN** a warning SHALL be logged
- **THEN** no selection change SHALL occur

---

### Requirement: Selection polling from Eeschema

The pqwave `KiCadBridge` SHALL poll Eeschema's selection every 500ms when a KiCad bridge is active, to detect when the user selects a net in the schematic.

The polling SHALL:
- Call `GetSelection` via the IPC API
- If the selection changed from the previous poll, identify the net(s) of the selected items via `get_netlist()`
- Emit a signal or callback to pqwave's trace manager to highlight the corresponding trace(s)
- Stop polling when the bridge is unwatched

#### Scenario: User clicks a net in Eeschema
- **WHEN** the user selects a wire on net "R1" in Eeschema
- **THEN** the next poll cycle SHALL detect the selection change
- **THEN** the net name "R1" SHALL be resolved
- **THEN** pqwave SHALL highlight the trace matching "v(r1)" or "i(r1)"

---

## Future: Show Trace Numbers

The following is explicitly **out of scope** for this change and marked as future work:

- Placing `SchematicText` annotations with trace values on the schematic via `CreateItems`
- Cleaning up old annotations via `DeleteItems`
- Position computation for text placement near nets via `GetBoundingBox`
- Undo-stack management for programmatic text creation

These capabilities are possible with the existing IPC API (CreateItems/DeleteItems are already registered) but require additional design around position computation, performance with rapid cursor movement, and undo history pollution.
