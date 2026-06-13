# KiCad Eeschema IPC Integration — Lessons Learned

> Reference for re-integrating when KiCad upstream implements Eeschema
> selection/annotation handlers.  Based on pqwave v0.3.2+ with KiCad 10.99
> (local build, June 2026).

## 1. Architecture Overview

```
┌──────────────┐     IPC/NNG      ┌──────────────────────────┐
│   pqwave     │ ◄──────────────► │  KiCad API Server        │
│  (Python)    │   /tmp/kicad/    │  (C++, per-process)      │
│              │   api.sock       │                          │
│  bridge.py   │                  │  KICAD_API_SERVER        │
│  cross_probe │                  │    ├─ API_HANDLER_PCB    │
│  main_window │                  │    └─ API_HANDLER_SCH    │
└──────────────┘                  └──────────────────────────┘
```

**Key insight:** The API server is per-process. The `kicad` project manager has one server; a standalone `eeschema` process has its own with a PID-suffixed socket (`api-<PID>.sock`). pqwave must connect to the correct socket.

## 2. C++ Handler Implementation (KiCad Side)

### 2.1 Handler Registration

Handlers are registered in the `API_HANDLER_SCH` constructor via template method
`registerHandler<RequestType, ResponseType>(&Handler::method)`.

```cpp
// eeschema/api/api_handler_sch.cpp — constructor
registerHandler<GetSelection, SelectionResponse>(
    &API_HANDLER_SCH::handleGetSelection);
registerHandler<ClearSelection, Empty>(
    &API_HANDLER_SCH::handleClearSelection);
registerHandler<AddToSelection, SelectionResponse>(
    &API_HANDLER_SCH::handleAddToSelection);
registerHandler<GetBoundingBox, GetBoundingBoxResponse>(
    &API_HANDLER_SCH::handleGetBoundingBox);
```

**Important:** The `API_HANDLER_SCH` constructor MUST finish completely. If any handler
registration between existing and new handlers throws (unlikely, but ensure
`wxASSERT_MSG` is a no-op in release builds), later handlers are silently absent.

### 2.2 Required Includes

```cpp
#include <sch_actions.h>
#include <tools/sch_selection_tool.h>
#include <tool/tool_manager.h>
```

### 2.3 Handler Pattern (matching Pcbnew)

Every handler must follow this pattern:

```cpp
HANDLER_RESULT<ResponseType> API_HANDLER_SCH::handleXxx(
    const HANDLER_CONTEXT<RequestType>& aCtx)
{
    // 1. Guard: is the editor busy?
    if (std::optional<ApiResponseStatus> busy = checkForBusy())
        return tl::unexpected(*busy);

    // 2. Guard: is the frame available?
    if (!m_frame) {
        ApiResponseStatus e;
        e.set_status(ApiStatusCode::AS_UNHANDLED);
        return tl::unexpected(e);
    }

    // 3. Validate document header
    auto validResult = validateItemHeaderDocument(aCtx.Request.header());

    // 4. Only return AS_UNHANDLED for wrong document type
    if (!validResult && validResult.error().status() == ApiStatusCode::AS_UNHANDLED) {
        ApiResponseStatus e;
        e.set_status(ApiStatusCode::AS_UNHANDLED);
        return tl::unexpected(e);
    }
    // 5. Propagate real validation errors (project mismatch, etc.)
    else if (!validResult) {
        return tl::unexpected(validResult.error());
    }

    // 6. Actual handler logic...
}
```

**Critical bug we hit:** Returning `AS_UNHANDLED` on ALL validation failures
(instead of just document-type mismatch) causes the API server to silently
route to the next handler. Since no other handler matches, the client gets
"no handler available" even when the handler EXISTS. This cost hours of debugging.

### 2.4 Registration Guard

The `SCH_EDIT_FRAME` constructor guards handler creation with `#ifdef KICAD_IPC_API`:

```cpp
#ifdef KICAD_IPC_API
    m_apiHandler = std::make_unique<API_HANDLER_SCH>(this);
    Pgm().GetApiServer().RegisterHandler(m_apiHandler.get());
#endif
```

Ensure `KICAD_IPC_API=ON` in CMake (option defaults to ON).

### 2.5 Standalone vs. Shell

- **`kicad` shell:** `kicad.cpp` → `_eeschema.kiface` loaded via KIWAY
- **Standalone `eeschema`:** `common/single_top.cpp` → creates `KICAD_API_SERVER` directly, loads `_eeschema.kiface`
- Both paths call `SCH_EDIT_FRAME` constructor → handler registered

## 3. IPC Protocol Gotchas

### 3.1 DocumentSpecifier Validation

`validateItemHeaderDocument()` → `validateDocument()` → `validateDocumentInternal()`
checks that the request's `DocumentSpecifier.project` matches the open project:

```cpp
// eeschema/api/api_handler_sch.cpp
if (aDocument.project().name().compare(prj.GetProjectName().ToUTF8()) != 0)
    return error;  // "the requested document <name> is not open"
```

**Fix:** Always populate `DocumentSpecifier.project.name` and `.project.path`
from the schema's `GetOpenDocuments` response. kipy's `schematic.document`
already has this populated.

### 3.2 GetSelection Returns Serialized EDA_ITEMs, NOT KIIDs

`SelectionResponse.items` contains `google.protobuf.Any` objects wrapping
serialized `SCH_ITEM` protos (Junction, SchematicLine, Symbol, etc.).
To extract KIIDs, you must:

1. Parse `item.type_url` to determine the message type
2. Import the corresponding Python protobuf module
3. Unpack the `Any` into the correct type
4. Read the `id.value` field (every SCH_ITEM has an `id` field)

```python
# Proto package → Python module mapping
pkg_map = {
    'kiapi.common.commands': 'kipy.proto.common.commands.editor_commands_pb2',
    'kiapi.common.types': 'kipy.proto.common.types',
    'kiapi.schematic.types': 'kipy.proto.schematic.schematic_types_pb2',
    'kiapi.schematic.commands': 'kipy.proto.schematic.schematic_commands_pb2',
}
```

### 3.3 Proto Field Names Use Suffixes

All coordinate/distance fields use `_nm` suffix:

```
Vector2:  x_nm, y_nm          (NOT x, y)
Distance: value_nm             (NOT value)
Box2:     position (Vector2), size (Vector2)   (NOT top_left/bottom_right)
```

Schematic item `id` field access: `item.id.value` (string)

### 3.4 LockedState and Alignment Enums Are Integers

```python
attrs.horizontal_alignment = 1  # HA_LEFT
attrs.vertical_alignment = 2    # VA_CENTER
sch_text.locked = 2             # LS_UNLOCKED
```

Importing named enum constants from kipy would be cleaner but may not
be available depending on the protobuf generation settings.

### 3.5 Socket Path and Multiple Processes

- Main `kicad` process: `/tmp/kicad/api.sock`
- Standalone `eeschema` process: `/tmp/kicad/api-<PID>.sock` (falls back when `api.sock` is locked)

When both `kicad` and `eeschema` run as separate processes, the Eeschema
handlers are on `api-<PID>.sock`, NOT on `api.sock`. pqwave's default
connection to `/tmp/kicad/api.sock` will NOT find schematic handlers.

**Fix:** Detect the Eeschema-specific socket, or always run eeschema
standalone (which gets `api.sock` when no `kicad` PM is running).

## 4. Back-Annotation via CreateItems

### 4.1 Creating SchematicText Items

```python
from kipy.proto.schematic.schematic_types_pb2 import SchematicText
from kipy.proto.common.types import Text, TextAttributes

# Build text attributes
attrs = TextAttributes()
attrs.horizontal_alignment = 1       # HA_LEFT
attrs.vertical_alignment = 2         # VA_CENTER
attrs.size.x_nm = 1_270_000          # 50 mil
attrs.size.y_nm = 1_270_000
attrs.stroke_width.value_nm = 127_000  # 5 mil

# Build text body
txt = Text()
txt.position.x_nm = x_position
txt.position.y_nm = y_position
txt.text = "r1=95.94"
txt.attributes.CopyFrom(attrs)

# Build SchematicText wrapper
sch_text = SchematicText()
sch_text.text.CopyFrom(txt)
sch_text.locked = 2                  # LS_UNLOCKED
sch_text.exclude_from_sim = True     # Don't include in simulation
```

### 4.2 Batching (Performance)

**Always batch multiple text items into a single `CreateItems` request.**
Each IPC call has ~5-30ms latency; with 10+ traces that's significant.

```python
req = CreateItems()
req.header.CopyFrom(hdr)
for sch_text in text_items:
    any_item = Any()
    any_item.Pack(sch_text)
    req.items.append(any_item)
resp = client.send(req, CreateItemsResponse)
```

### 4.3 Annotation Lifecycle

1. Track created KIIDs in `_annotation_ids`
2. Before creating new annotations, delete old ones via `DeleteItems`
3. On delete failure, preserve `_annotation_ids` for retry (otherwise orphans accumulate)

### 4.4 Positioning

Use `GetBoundingBox` to find net wire positions, then place text near the
bounding box center. The `net_kiids[:20]` limit prevents oversized requests
for nets with many wire segments.

## 5. Thread Safety for Selection Polling

### 5.1 Architecture

Selection polling MUST run on a background thread to avoid blocking the Qt
event loop. Even 30ms IPC latency every 500ms causes visible UI jank.

```python
class KiCadPollWorker(QObject):
    nets_found = pyqtSignal(list)

    def __init__(self, bridge, interval_ms=500):
        super().__init__()
        self._bridge = bridge
        # Timer created in start() — AFTER moveToThread()
        self._timer = None

    def start(self):
        if self._timer is None:
            self._timer = QTimer()
            self._timer.timeout.connect(self._poll)
        self._timer.start()

# Usage:
worker = KiCadPollWorker(bridge)
thread = QThread()
worker.moveToThread(thread)
worker.nets_found.connect(handler)      # queued connection
thread.started.connect(worker.start)
thread.start()
```

### 5.2 Lock Discipline

Shared bridge state (`_ipc_probe`, `_suppress_ipc_poll`) needs a `threading.Lock`:

- **Writers** (main thread): `probe_net()`, `probe_part()` hold lock when setting `_suppress_ipc_poll`
- **Readers** (poll thread): `_poll()` holds lock when reading `_suppress_ipc_poll`
- **Invalidation** (main thread): `_invalidate_ipc_probe()` holds lock
- **Connection creation**: `_get_ipc_probe()` uses double-checked locking

**Critical:** The poll worker must NEVER call `_invalidate_ipc_probe()`.
If the poll worker invalidates while the main thread is mid-probe,
`self._kicad` becomes `None` and the probe crashes with `AttributeError`.

### 5.3 Feedback Loop Guard

`probe_net()`/`probe_part()` set `_suppress_ipc_poll = True` before
modifying Eeschema selection, preventing the poll worker from detecting
the programmatic selection change as a user click.

## 6. kicad-python (kipy) Integration

### 6.1 Installation

kipy must be installed as a **user prerequisite**, NOT a pqwave dependency:

```bash
# From Git main branch (PyPI 0.7.1 is too old — no schematic support)
cd ~/Apps/kicad-python.git
# Ensure kicad submodule points to the correct KiCad source
pip install -e .
```

pqwave loads kipy via `PYTHONPATH`:
```bash
export PYTHONPATH=/home/wing/Apps/kicad-python.git:$PYTHONPATH
```

Tests use `pytest.importorskip("kipy")` to gracefully skip when absent.

### 6.2 Connection

```python
import kipy
kicad = kipy.KiCad(socket_path="ipc:///tmp/kicad/api.sock", timeout_ms=3000)
sch = kicad.get_schematic()
# sch.document has project info populated
```

### 6.3 Exception Handling

kipy raises its own exception types (`kipy.errors.ConnectionError`,
`kipy.errors.ApiError`), NOT Python builtins. Catching `ConnectionError`
(builtins) will miss kipy failures.

```python
# WRONG — doesn't catch kipy errors
except (OSError, ConnectionError, TimeoutError):

# CORRECT
except Exception:
```

## 7. kicad-cli Netlist Export

For simulation (separate from IPC cross-probe):

```python
result = subprocess.run(
    [kicad_cli, "sch", "export", "netlist", "--format", "spice",
     "-o", tmp_path, sch_path],
    capture_output=True, text=True, timeout=30,
)
```

Netlist fixes for KiCad-specific quirks (apply in order):
1. `StripSlashes` — removes `/` from hierarchical net names
2. `FixDiodePins` — corrects diode pin ordering
3. `FixBJTPins` — corrects BJT pin ordering
4. `MoveControlBlock` — repositions `.control` blocks

## 8. Common Pitfalls Checklist

- [ ] `DocumentSpecifier.project.name` and `.path` populated (not empty)
- [ ] Proto field names use `_nm` suffix: `x_nm`, `y_nm`, `value_nm`
- [ ] `Box2` uses `position` + `size` (not `top_left`/`bottom_right`)
- [ ] `GetSelection` returns `Any` items, not KIIDs — must unpack
- [ ] Handler returns `AS_UNHANDLED` ONLY for document-type mismatch
- [ ] `checkForBusy()` called before handler logic
- [ ] Poll worker on background thread, NOT main-thread QTimer
- [ ] Poll worker NEVER calls `_invalidate_ipc_probe()`
- [ ] `_suppress_ipc_poll` protected by lock on BOTH read and write paths
- [ ] Annotation IDs preserved on `DeleteItems` failure (retry, not orphan)
- [ ] `CreateItems` batched — single request for all annotation texts
- [ ] kipy exceptions are custom types, not Python builtins
- [ ] Socket path: check for PID-suffixed socket when eeschema is standalone
- [ ] `_eeschema.kiface` must be relinked (not just recompiled) after handler changes

## 9. Test Strategy

```python
# Module-level skip if kipy not installed
pytest.importorskip("kipy", reason="kicad-python is required")

# Mock setup must provide valid DocumentSpecifier with ProjectSpecifier
def _make_mock_schematic():
    doc = DocumentSpecifier()
    doc.type = DocumentType.DOCTYPE_SCHEMATIC
    proj = ProjectSpecifier()
    proj.name = "test"
    proj.path = "/tmp/test"
    doc.project.CopyFrom(proj)
    mock_sch = MagicMock()
    mock_sch.document = doc
    return mock_sch

# set_kicad() now calls get_schematic() internally
mock_kicad.get_schematic.return_value = mock_sch
```

## 10. KiCad Build Notes

```bash
# Configure
cmake -B build -DCMAKE_BUILD_TYPE=Release -DKICAD_IPC_API=ON

# Build (limit parallelism to avoid OOM)
cmake --build build --target eeschema_kiface -j 8

# Install
cmake --install build --prefix ~/Apps/kicad

# Incremental rebuild after handler changes
touch eeschema/api/api_handler_sch.cpp
cmake --build build --target eeschema_kiface -j 8
cp build/eeschema/_eeschema.kiface ~/Apps/kicad/bin/
```

The `_eeschema.kiface` shared library contains the API handler code. Changes
to `api_handler_sch.cpp` require BOTH recompilation AND relinking of the kiface.
