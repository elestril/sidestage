Now I have a thorough understanding of all the files involved. Let me generate the section content.

# Section 06: Orchestrator, WebSocket, Campaign Agent, and API Changes

## Overview

This section refactors the Orchestrator layer to eliminate `SyncManager` and the broadcast callback pattern, routing all WebSocket communication through the `User` actor. It also integrates the Campaign Co-Author as an `NPCActor`, updates REST endpoints and schemas for the new `EventModel`, and updates the MCP bridge.

**Plan sections covered:** 8 (User & WebSocket Integration), 9 (Campaign Agent Integration), 12 (API Changes)

**Dependencies:** Sections 01-05 must be complete before implementing this section. Specifically:
- Section 01 provides `EventModel`, `EventType`, `Event` wrapper
- Section 02 provides `Actor`, `NPCActor`, `User`, `Character`, and `Campaign.get_character()` / `Campaign.user`
- Section 03 provides updated storage and graph persistence for `EventModel`
- Section 04 provides the refactored `Scene` with `scene.chat(actor_id, text, character_id)`, `Scene.process()`, and `Scene._dispatch()`
- Section 05 provides tracing integration

**Blocked by this section:** Section 07 (Frontend) and Section 08 (Integration Tests)

---

## Tests

Tests should be written first, before the implementation. The following test stubs cover the orchestrator, WebSocket, campaign agent, and API changes.

### Test File: `/home/harald/src/sidestage/tests/integration/test_websocket.py`

This file needs significant updates (or rewrite) from the existing `tests/integration/test_sync.py`. The old file tests `SyncManager`-based broadcasting; the new tests validate `User` actor-based communication.

```python
"""Tests for WebSocket integration with User actor (replaces SyncManager tests)."""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from sidestage.orchestrator import SidestageOrchestrator


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a TestClient with mocked Campaign dependencies."""
    # Patch Campaign to avoid LLM availability checks and agent creation.
    # The Campaign should now have a .user attribute (User actor) instead of
    # the orchestrator owning a SyncManager.
    ...


class TestWebSocketConnect:
    def test_websocket_connect_registers_with_user(self, client):
        """WebSocket connect calls campaign.user.connect(ws), NOT SyncManager."""
        ...

    def test_websocket_disconnect_removes_from_user(self, client):
        """WebSocket disconnect calls campaign.user.disconnect(ws)."""
        ...


class TestWebSocketMessages:
    def test_incoming_chat_message_routes_to_scene_chat(self, client):
        """Incoming chat_message routes to scene.chat() with raw parameters
        (actor_id, text, character_id) instead of creating ChatMessageModel."""
        ...

    def test_entity_content_sync_rebroadcast_via_user_send(self, client):
        """entity_content_sync rebroadcasts via user.send(message, exclude=sender)
        instead of sync_manager.broadcast()."""
        ...

    def test_event_dispatch_to_user_sends_json_over_websocket(self, client):
        """When Scene._dispatch() calls User.process(), the event JSON
        is sent over the WebSocket connection."""
        ...

    def test_actor_status_thinking_idle_messages(self, client):
        """actor_status thinking/idle messages are sent over WebSocket
        during NPC processing."""
        ...
```

### Test File: `/home/harald/src/sidestage/tests/unit/test_campaign.py`

Extend the existing test file with new tests for the Campaign agent integration changes.

```python
"""Additional tests for Campaign agent refactoring."""

# Test: Campaign creates User at startup
# Campaign.__init__ should create self.user = User(actor_id="user")
def test_campaign_creates_user_at_startup(tmp_path):
    """Campaign.__init__ creates a User actor accessible as campaign.user."""
    ...

# Test: Campaign no longer has Campaign.agent field (raw LiteLLMAgent)
def test_campaign_no_raw_agent_field(tmp_path):
    """Campaign should not have a .agent attribute holding a raw LiteLLMAgent.
    The Co-Author's agent is managed by its NPCActor."""
    ...

# Test: Co-Author character resolved as NPCActor with system_actor=True
def test_co_author_resolved_as_system_npc_actor(tmp_path):
    """Campaign.get_character() for Co-Author returns Character with
    NPCActor that has system_actor=True."""
    ...

# Test: Co-Author NPCActor gets world-building tools
def test_co_author_gets_world_building_tools(tmp_path):
    """NPCActor with system_actor=True is configured with world-building
    tools (create_character, list_characters, etc.)."""
    ...

# Test: Regular NPC NPCActor gets memory tools only
def test_regular_npc_gets_memory_tools_only(tmp_path):
    """NPCActor with system_actor=False gets memory tools, not world-building tools."""
    ...
```

### Test File: `/home/harald/src/sidestage/tests/integration/test_api.py`

New or extended test file for the REST API changes.

```python
"""Tests for REST API changes with EventModel."""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


# Test: POST /v1/chat returns ChatResponse with event field (EventModel)
def test_chat_endpoint_returns_event_model(client):
    """POST /v1/chat should return {"event": {...}} with EventModel fields,
    not {"user_message": {...}} with ChatMessageModel."""
    ...

# Test: GET /v1/scenes/{id}/messages returns List[EventModel]
def test_scene_messages_returns_event_models(client):
    """GET /v1/scenes/{id}/messages returns EventModel objects
    (with event_type field), not ChatMessageModel."""
    ...

# Test: WebSocket broadcast uses 'event' message type (not 'chat_message')
def test_websocket_broadcast_event_type(client):
    """WebSocket broadcasts use type='event' with EventModel payload,
    not type='chat_message'."""
    ...
```

### Test File: `/home/harald/src/sidestage/tests/unit/test_mcp_bridge.py`

Update the existing test file. The key changes are:
- `sync_manager` references become `campaign.user.send()` references
- `send_chat_message` calls `scene.chat()` with raw parameters
- Return format changes to `{"event": ...}`

```python
# Test: MCP bridge send_chat_message calls scene.chat() with raw parameters
@pytest.mark.anyio
async def test_send_chat_message_calls_scene_chat_raw(mcp, mock_orchestrator):
    """send_chat_message calls scene.chat(actor_id="user", text=message)
    instead of scene.create_message() + scene.chat(msg)."""
    ...

# Test: MCP bridge send_chat_message returns {"event": ...} format
@pytest.mark.anyio
async def test_send_chat_message_returns_event_format(mcp, mock_orchestrator):
    """send_chat_message returns {"event": event.model_dump()} not
    {"user_message": msg.model_dump()}."""
    ...

# Test: MCP bridge broadcast calls go through campaign.user.send()
@pytest.mark.anyio
async def test_mcp_broadcasts_via_user_send(mcp, mock_orchestrator):
    """All broadcast calls (entities_updated, scene_updated) go through
    campaign.user.send() instead of orchestrator.sync_manager.broadcast()."""
    ...
```

---

## Implementation Details

### 1. Delete `src/sidestage/sync.py`

Remove the entire `SyncManager` class and file. The `User` actor (from section 02) now owns WebSocket connections and provides `connect()`, `disconnect()`, `send()`, and `process()`.

### 2. Orchestrator Changes (`/home/harald/src/sidestage/src/sidestage/orchestrator.py`)

The orchestrator undergoes significant simplification.

**Remove:**
- `from sidestage.sync import SyncManager` import
- `self.sync_manager = SyncManager()` from `__init__`
- `_broadcast_chat_event()` method entirely
- `set_broadcast()` call in `get_active_scene()`

**Add/Change in `__init__`:**
- The orchestrator no longer creates a `SyncManager`. It accesses `self.campaign.user` for WebSocket communication.

**`get_active_scene()` simplification:**
- Remove `scene_logic.set_broadcast(self._broadcast_chat_event)` line. Scene dispatch to Users IS the broadcast now (User.process() sends events to WebSocket connections).
- The method becomes:

```python
async def get_active_scene(self, scene_id: str):
    """Retrieve or activate a scene by ID."""
    if scene_id in self.active_scenes:
        return self.active_scenes[scene_id]
    scene_logic = self.campaign.get_scene_object(scene_id)
    if scene_logic:
        await scene_logic.activate()
        self.active_scenes[scene_id] = scene_logic
        return scene_logic
    return None
```

**WebSocket endpoint refactored:**

```python
@self.fastapi_app.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    user = self.campaign.user
    await user.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await self._handle_ws_message(websocket, data)
    except WebSocketDisconnect:
        user.disconnect(websocket)
```

Key differences from the current implementation:
- `websocket.receive_json()` instead of `receive_text()` + json.loads in SyncManager
- `user.connect(ws)` / `user.disconnect(ws)` instead of `sync_manager.connect/disconnect`
- No more routing through `sync_manager.handle_message()` -- the orchestrator handles messages directly

**`_handle_ws_message()` refactored:**

```python
async def _handle_ws_message(self, websocket: WebSocket, message: dict) -> None:
    """Handle incoming WebSocket messages from clients."""
    msg_type = message.get("type")
    scene_id = message.get("scene_id")

    if msg_type == "chat_message" and scene_id:
        scene = await self.get_active_scene(scene_id)
        if scene:
            text = message.get("text", "")
            character_id = message.get("character_id")
            await scene.chat(actor_id="user", text=text, character_id=character_id)

    elif msg_type == "entity_content_sync":
        # Relay keystroke sync to all other clients via the User actor
        await self.campaign.user.send(message, exclude=websocket)
```

Key changes:
- No longer imports `ChatMessageModel`
- Calls `scene.chat(actor_id="user", text=text, character_id=character_id)` with raw parameters
- `entity_content_sync` uses `user.send(message, exclude=websocket)` instead of `sync_manager.broadcast(message, exclude=websocket)`

**All `sync_manager.broadcast()` calls become `campaign.user.send()`:**

Every place in the orchestrator that previously called `self.sync_manager.broadcast(...)` now calls `self.campaign.user.send(...)`. These are all the non-event system notifications (entities_updated, scene_updated, etc.). They are NOT events in the EventModel sense -- they are ephemeral WebSocket messages for UI state sync. The call sites:

- `import_entities()`: `await self.campaign.user.send({"type": "entities_updated"})`
- `update_entity_markdown()`: same
- `update_entity()`: same
- `reload_defaults()`: same
- `create_scene()`: `await self.campaign.user.send({"type": "scene_updated"})`
- `import_campaign_route()`: passed as parameter to importer (see below)
- `backup_campaign_route()`: `await self.campaign.user.send({"type": "entities_updated"})`

**Chat endpoint updated:**

```python
@self.fastapi_app.post("/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    scene = await self.get_active_scene(request.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    await scene.chat(actor_id="user", text=request.message)
    # The event is created inside scene.chat(); the response comes async via WebSocket
    return ChatResponse(event=...)  # See schema changes below
```

Note: The exact return value of `scene.chat()` changes. In the new design, `scene.chat()` returns `None` (fire-and-forget); events are dispatched asynchronously. The REST endpoint either needs to:
- Return immediately with a minimal acknowledgment, OR
- Have `scene.chat()` return the created `Event` so the REST response can include it

The plan specifies `ChatResponse(event=EventModel)` -- so `scene.chat()` should return the created `Event` object to allow this. Check the section 04 implementation for the return type.

**Scene messages endpoint:**

```python
@self.fastapi_app.get("/v1/scenes/{scene_id}/messages")
async def get_scene_messages(scene_id: str):
    """Get event history for a scene."""
    events = self.campaign.get_scene_events(scene_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return [e.model_dump() for e in events]
```

The `Campaign.get_scene_messages()` method name may change to `get_scene_events()` to reflect the new model. The implementation queries events by `scene_id` from storage or graph, filtered to relevant event types.

### 3. Campaign Agent Changes (`/home/harald/src/sidestage/src/sidestage/campaign.py`)

**Remove:**
- `from sidestage.agent import LiteLLMAgent` import (no longer needed at Campaign level)
- `self.agent = self.create_agent()` from `__init__`
- `create_agent()` method entirely
- The Co-Author's agent is now managed by its NPCActor, created via `Campaign.get_character()`

**Add to `__init__`:**
- `self.user = User(actor_id="user")` -- create the User actor (imported from `sidestage.actors`)
- `self.characters: Dict[str, Character] = {}` -- campaign-scoped character registry (from section 02)

**`get_scene_messages()` becomes `get_scene_events()`:**
- Returns `List[EventModel]` instead of `List[ChatMessageModel]`
- Queries events by scene_id from storage/graph
- Since `SceneModel.messages` is removed (section 01), events are stored independently

**`get_scene_object()` updated:**
- Remove `self.agent` parameter from `Scene(...)` constructor
- Pass `campaign=self` so Scene can access `campaign.get_character()` and `campaign.user`

**Co-Author data file update:**

Update `/home/harald/src/sidestage/data/campaign_defaults/markdown/characters/co-author.md` frontmatter to add:

```yaml
---
id: "char_co_author"
name: "Co-Author"
unseen: true
owner: npc
system_actor: true
---
```

The `owner: npc` and `system_actor: true` fields cause `Campaign._resolve_actor()` (from section 02) to create an `NPCActor` with `system_actor=True` when `get_character()` is called for this character. The NPCActor then configures itself with world-building tools and the `system_agent.txt` prompt template.

**Create prompt file:**

Create `/home/harald/src/sidestage/data/prompts/system_agent.txt` containing the system-level prompt template for the Co-Author. This should be derived from the existing instructions in `Campaign.create_agent()`:

```
You are the Sidestage Co-Author, a world-building assistant.
STRICT PERSONA: NEVER identify as a 'large language model'. You are strictly the Sidestage Co-Author.
DATABASE-ONLY KNOWLEDGE: You know NOTHING about Characters, locations, or items except what is in your database.
TOOL-FIRST: If asked about characters, world details, or 'which characters do you know?', you MUST call `list_characters` immediately.
NEVER list famous characters from other games (like Fallout or Elder Scrolls) unless they were created in THIS campaign.
TONE: Helpful and collaborative.
```

### 4. Schema Changes (`/home/harald/src/sidestage/src/sidestage/schemas.py`)

**`ChatResponse` updated:**

```python
from sidestage.models import EventModel

class ChatResponse(BaseModel):
    event: EventModel  # The created user event
```

This replaces the old `ChatResponse(user_message: ChatMessageModel, agent_message: Optional[ChatMessageModel])`. The agent response arrives asynchronously via WebSocket dispatch, not in the REST response.

**`ChatRequest` stays the same:**

```python
class ChatRequest(BaseModel):
    message: str
    scene_id: str = "campaign_planning"
```

**`WebSocketMessage` updated for the flattened event structure:**

```python
class WebSocketMessage(BaseModel):
    type: str
    event: Optional[Dict[str, Any]] = None  # For 'event' type messages
    scene_id: Optional[str] = None
    entity_id: Optional[str] = None
    body: Optional[str] = None
    character_id: Optional[str] = None  # For actor_status messages
    status: Optional[str] = None  # For actor_status messages ('thinking'/'idle')
```

**Remove** the `ChatMessageModel` import from schemas.py.

### 5. MCP Bridge Changes (`/home/harald/src/sidestage/src/sidestage/mcp_bridge.py`)

All `orchestrator.sync_manager.broadcast(...)` calls change to `orchestrator.campaign.user.send(...)`. There are approximately 6 such call sites in the existing code.

**`send_chat_message` tool updated:**

```python
@mcp.tool()
async def send_chat_message(message: str, scene_id: str) -> dict[str, Any]:
    """Send a message to the AI co-author in a scene."""
    scene = await orchestrator.get_active_scene(scene_id)
    if not scene:
        raise ValueError(f"Scene '{scene_id}' not found")
    await scene.chat(actor_id="user", text=message)
    return {"status": "sent", "scene_id": scene_id}
```

Key changes:
- Calls `scene.chat(actor_id="user", text=message)` with raw parameters
- No longer calls `scene.create_message()` to build a `ChatMessageModel`
- Return value changes -- the event is now created inside `scene.chat()` and dispatched asynchronously
- If `scene.chat()` returns the created `Event`, the return value can be `{"event": event.model.model_dump()}`

**`get_scene_messages` tool updated:**

```python
@mcp.tool()
async def get_scene_messages(scene_id: str) -> list[dict[str, Any]]:
    """Get the event history for a scene."""
    events = orchestrator.campaign.get_scene_events(scene_id)
    if events is None:
        raise ValueError(f"Scene '{scene_id}' not found")
    return [e.model_dump() for e in events]
```

**`import_campaign` tool updated:**

```python
result = await do_import(
    campaign=campaign,
    parse_result=parse_result,
    user=orchestrator.campaign.user,  # Pass User instead of SyncManager
    active_scenes=orchestrator.active_scenes,
)
```

### 6. Migration Importer Changes (`/home/harald/src/sidestage/src/sidestage/migration/importer.py`)

**`import_campaign()` signature updated:**

```python
async def import_campaign(
    campaign: Campaign,
    parse_result: ParseResult,
    user: User | None = None,  # Was: sync_manager: SyncManager | None = None
    active_scenes: dict[str, Any] | None = None,
) -> MigrationImportResult:
```

**Post-import broadcast updated:**

```python
if user is not None:
    await user.send({"type": "entities_updated"})
```

This replaces `sync_manager.broadcast({"type": "entities_updated"})`.

**`_parse_chatlog_lines()` updated:**
- Constructs `EventModel` with `event_type=EventType.CHAT_MESSAGE` instead of `ChatMessageModel`
- Uses `evt_` prefix for IDs instead of `msg_` or `{scene_id}_msg_`
- Uses `body` for message content (no separate `message` field)

**`_restore_chatlogs()` updated:**
- No longer sets `existing.messages = messages` (field removed from SceneModel)
- Instead, persists each event individually to storage and/or graph

### 7. Migration Exporter (`/home/harald/src/sidestage/src/sidestage/migration/exporter.py`)

The exporter needs to query events from storage/graph by scene_id rather than reading from `SceneModel.messages`. This is covered by section 03 (storage), but the exporter call sites in the orchestrator change:

```python
result = await export_campaign(campaign)
if result.phase == "complete":
    await self.campaign.user.send({"type": "entities_updated"})
```

### 8. Existing Test Updates

**`/home/harald/src/sidestage/tests/integration/test_sync.py`:**
This file should be renamed or heavily refactored into `test_websocket.py`. All references to `SyncManager` are replaced with `User` actor operations. Key changes:

- `client` fixture no longer relies on `orchestrator.sync_manager`
- `test_websocket_broadcast_on_entity_update`: Broadcast comes via `user.send()`, message type may change
- `test_collaborative_editing_relay`: Uses `user.send(message, exclude=websocket)` instead of `sync_manager.broadcast(message, exclude=websocket)`
- `test_chat_broadcast`: Message type changes from `"chat_message"` to `"event"`, payload shape changes from `{"message": ...}` to `{"event": ...}` with EventModel fields

**`/home/harald/src/sidestage/tests/unit/test_mcp_bridge.py`:**
- `mock_orchestrator` fixture: Remove `orch.sync_manager = MagicMock()` setup. Instead, mock `campaign.user.send` as `AsyncMock`.
- All assertions on `sync_manager.broadcast` change to assertions on `campaign.user.send`.
- `test_send_chat_message` must verify `scene.chat()` is called with raw parameters.
- Tool registration test remains the same (tool names do not change).

**`/home/herald/src/sidestage/tests/unit/test_campaign.py`:**
- `test_campaign_create_agent_*` tests are removed or replaced -- Campaign no longer has a `create_agent()` method or `.agent` field.
- `test_agent_tools_configuration` is removed -- tools are now configured per-NPCActor based on `system_actor` flag, tested at the Actor level (section 02 tests).
- New tests added for `campaign.user` creation and Co-Author resolution.

**`/home/harald/src/sidestage/tests/unit/test_migration_importer.py`:**
- Update references from `sync_manager` parameter to `user` parameter in `import_campaign()` calls.
- Update `_parse_chatlog_lines()` tests to expect `EventModel` with `event_type=EventType.CHAT_MESSAGE` instead of `ChatMessageModel`.

---

## Files Modified

| File | Action |
|------|--------|
| `src/sidestage/orchestrator.py` | Major refactor: remove SyncManager, use User actor, update endpoints |
| `src/sidestage/campaign.py` | Remove `create_agent()`, add `self.user`, update `get_scene_object()` |
| `src/sidestage/schemas.py` | Update `ChatResponse` to use `EventModel`, remove `ChatMessageModel` import |
| `src/sidestage/mcp_bridge.py` | Replace `sync_manager.broadcast` with `user.send`, update `send_chat_message` |
| `src/sidestage/sync.py` | **DELETE** this file entirely |
| `src/sidestage/migration/importer.py` | Replace `sync_manager` param with `user`, update chatlog parsing |
| `data/campaign_defaults/markdown/characters/co-author.md` | Add `owner: npc` and `system_actor: true` to frontmatter |
| `data/prompts/system_agent.txt` | **NEW** file: system prompt template for Co-Author |
| `tests/integration/test_sync.py` | Rename/rewrite as `test_websocket.py` with User actor tests |
| `tests/unit/test_mcp_bridge.py` | Update to remove SyncManager mocks, add User.send assertions |
| `tests/unit/test_campaign.py` | Remove agent tests, add User and Co-Author resolution tests |
| `tests/unit/test_migration_importer.py` | Update for `user` param and `EventModel` chatlog parsing |
| `tests/integration/test_api.py` | **NEW** or extended: REST endpoint tests for EventModel responses |

---

## Implementation Order Within This Section

1. Write all tests first (stubs above)
2. Delete `src/sidestage/sync.py`
3. Update `src/sidestage/schemas.py` (ChatResponse)
4. Update `data/campaign_defaults/markdown/characters/co-author.md` (frontmatter)
5. Create `data/prompts/system_agent.txt`
6. Update `src/sidestage/campaign.py` (remove agent, add user)
7. Update `src/sidestage/migration/importer.py` (user param, EventModel chatlogs)
8. Update `src/sidestage/mcp_bridge.py` (user.send, raw chat params)
9. Update `src/sidestage/orchestrator.py` (main refactor)
10. Update all affected test files
11. Run `uv run pytest tests/` to verify