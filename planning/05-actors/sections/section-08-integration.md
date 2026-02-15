I have all the context I need. Now I will generate the section content.

# Section 08: Integration Tests (End-to-End)

## Overview

This is the final section of the Actor Restructuring plan. It introduces end-to-end integration tests that verify the full event flow across all system layers: user input through WebSocket or REST, event creation, queue processing, persistence, dispatch to actors (both User and NPCActor), and NPC response generation. These tests exercise the real wiring between Orchestrator, Campaign, Scene, Actor, EventQueue, Storage, and Graph -- the complete refactored system.

**Plan section covered:** 13 (Testing Strategy -- Integration Tests)

**Dependencies:** All prior sections (01-07) must be complete before implementing this section. Specifically:
- Section 01: `EventModel`, `EventType`, `Visibility`, `Event` wrapper, `EventQueue` in `event.py`
- Section 02: `Actor`, `NPCActor`, `User`, `Character` classes in `actors.py` and `character.py`; `Campaign.get_character()`, `Campaign.user`
- Section 03: Updated graph `entity_to_labels()`, `node_to_entity()`, entity serialization with `event_type` in frontmatter
- Section 04: Refactored `Scene` with `scene.chat(actor_id, text, character_id)`, `Scene.process()`, `Scene._dispatch()`, `Scene.create_event()`, `EventQueue` consuming `Event` objects
- Section 05: Tracing integration -- `Event.from_model()` span context capture, span linking in `Scene._process_event()`
- Section 06: Orchestrator refactored to use `User` actor (no `SyncManager`), `ChatResponse` returning `EventModel`, MCP bridge updates, Co-Author as `NPCActor`
- Section 07: Frontend consuming new event format (not directly tested here but the WebSocket protocol it depends on is)

**Blocks:** Nothing. This is the final section.

---

## Background

### Pre-Refactor State

Before this plan, the system used:
- `ChatMessageModel` (subclass of `EventModel`) for chat messages, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel` as other event subclasses
- `SyncManager` for WebSocket connection management and broadcasting
- `AgentActor` embedded inside `Character`, tightly coupled to Scene via `scene_logic` back-reference
- `Scene.create_message()` returning `ChatMessageModel`, `Scene.chat()` accepting a `ChatMessageModel`
- `ChatResponse` schema with `user_message` and `agent_message` fields
- `Campaign.agent` as a raw `LiteLLMAgent` for the Co-Author

### Post-Refactor State (What These Tests Validate)

After all sections are implemented:
- Single `EventModel` with `event_type: EventType` discriminator replaces all subclasses
- `Event` wrapper carries `EventModel` + `SpanContext` through the queue
- `Actor` hierarchy: `User` (holds WebSocket connections, `process()` sends events), `NPCActor` (LLM-driven, `process()` generates responses)
- `Campaign.user` is a `User` actor; `Campaign.get_character()` resolves actors from `CharacterModel.owner` field
- `Scene.chat(actor_id, text, character_id)` creates events and enqueues via `Scene.process()`
- `Scene._dispatch()` calls `actor.process()` on all present actors, deduplicating by `actor_id`
- `Scene._dispatch()` sends `actor_status` thinking/idle signals to `User` actors around `NPCActor.process()` calls
- `ChatResponse` has a single `event: EventModel` field
- Orchestrator WebSocket endpoint uses `campaign.user.connect()` / `.disconnect()` instead of `SyncManager`
- Co-Author is an `NPCActor` with `system_actor=True`, participating in scenes like any NPC

---

## Tests

All integration tests for this section go in a single new file. These tests validate cross-layer behavior that unit tests in earlier sections cannot cover.

### Test File: `/home/harald/src/sidestage/tests/integration/test_chat_flow.py`

```python
"""End-to-end integration tests for the Actor-based chat flow.

These tests validate the full event lifecycle: user input -> event creation ->
queue processing -> persistence -> dispatch to actors -> NPC response generation.

Depends on all sections (01-07) being implemented.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from sidestage.orchestrator import SidestageOrchestrator
from sidestage.models import EventModel, EventType, CharacterModel, SceneModel
from sidestage.event import Event
from sidestage.actors import NPCActor, User
from sidestage.agent import AgentResponse


@pytest.fixture
def mock_agent():
    """Create a mock LiteLLMAgent that returns a canned response."""
    agent = MagicMock()
    agent.arun = AsyncMock(return_value=AgentResponse(content="NPC response text."))
    agent.model = "test-model"
    agent.api_base = "http://localhost:8080"
    agent.api_key = "sk-test"
    agent.tools = []
    agent.debug_mode = False
    return agent


@pytest.fixture
def client(tmp_path: Path, mock_agent) -> TestClient:
    """Create a TestClient with mocked LLM dependencies.

    Patches Campaign to avoid real LLM availability checks and agent creation.
    The Campaign.user attribute (User actor) is available for WebSocket testing.
    """
    ...


class TestFullChatFlow:
    """Test: Full chat flow -- user sends message -> event created ->
    persisted -> dispatched to User (WebSocket) and NPCActor.

    Verifies that a POST /v1/chat request creates an EventModel,
    enqueues it, persists it to storage, and dispatches it to all
    present actors (User receives it over WebSocket, NPCActor receives
    it for LLM processing).
    """

    def test_user_message_creates_event(self, client):
        """POST /v1/chat returns a ChatResponse with an EventModel.

        The response should contain an 'event' field (not 'user_message' /
        'agent_message' as before). The event should have event_type=CHAT_MESSAGE,
        an evt_ prefixed ID, and the user's text in the body field.
        """
        ...

    def test_user_message_persisted(self, client):
        """After sending a chat message, the event appears in the scene
        messages endpoint (GET /v1/scenes/{id}/messages).

        The returned list should contain EventModel dicts with event_type,
        body, character_id, and actor_id fields.
        """
        ...

    def test_user_message_broadcast_via_websocket(self, client):
        """A WebSocket client receives the user's event as a broadcast.

        The WebSocket message should have type='event' (not 'chat_message')
        and contain an EventModel payload with event_type='ChatMessage'.
        """
        ...


class TestNPCResponse:
    """Test: NPCActor response -> new event created -> persisted ->
    dispatched to User (WebSocket).

    Requires @pytest.mark.llm or a mocked LLM agent.
    """

    def test_npc_responds_to_user_message(self, client, mock_agent):
        """After a user sends a CHAT_MESSAGE, the NPCActor generates a
        response event that is broadcast over WebSocket.

        The test sends a chat message via REST, then polls the WebSocket
        for the NPC's response event. The response event should have
        event_type=CHAT_MESSAGE, the NPC's character_id, and an actor_id
        starting with 'agent:'.
        """
        ...

    def test_npc_response_persisted(self, client, mock_agent):
        """The NPC's response event is persisted and appears in the
        scene messages endpoint alongside the user's original event.
        """
        ...


class TestLLMFailure:
    """Test: LLM failure -> ERROR event created -> dispatched to User."""

    def test_llm_error_produces_error_event(self, client):
        """When the LLM agent raises an exception during NPCActor.process(),
        an ERROR event is created and dispatched to the User via WebSocket.

        The ERROR event should have event_type=ERROR and contain error
        details in the body field.
        """
        ...

    def test_error_event_persisted(self, client):
        """The ERROR event generated from an LLM failure is persisted
        to storage and appears in scene messages.
        """
        ...


class TestMultiCharacterDeduplication:
    """Test: Multiple characters same User -> dispatch deduplicates by actor_id.

    When a User controls two characters in the same scene, Scene._dispatch()
    should only call User.process() once per event (not once per character).
    """

    def test_user_receives_event_once(self, client):
        """Set up a scene with two player characters (both owned by the
        same User). Send a message. The User's WebSocket should receive
        exactly one broadcast of the event, not two.
        """
        ...


class TestCoAuthorParticipation:
    """Test: Co-Author NPCActor participates in scene like regular NPC.

    The Co-Author character has system_actor=True and owner='npc'. It should
    be resolved as an NPCActor and participate in scenes.
    """

    def test_co_author_responds(self, client, mock_agent):
        """The Co-Author character, configured with system_actor=True,
        receives dispatched events and generates responses like any NPC.
        """
        ...


class TestAdjustGametime:
    """Test: ADJUST_GAMETIME event updates scene gametime."""

    def test_gametime_updated(self, client):
        """When an ADJUST_GAMETIME event is processed, the scene's
        current_gametime is updated to the event's gametime value.
        """
        ...


class TestEventTracing:
    """Test: Event tracing -- span links connect user request trace
    to scene processing trace.
    """

    def test_span_link_created(self, client):
        """When an event is created with an active trace context and
        then processed by the scene, the processing span should contain
        a link to the original creation span context.

        Uses OpenTelemetry's InMemorySpanExporter to capture spans
        and inspect their links.
        """
        ...


class TestThinkingIndicators:
    """Test: actor_status thinking/idle messages bracket NPC processing."""

    def test_thinking_status_sent(self, client, mock_agent):
        """When an NPCActor starts processing, a 'thinking' actor_status
        message is sent to WebSocket clients. When processing completes,
        an 'idle' actor_status message is sent.

        The test connects a WebSocket, sends a chat message, and verifies
        that the received messages include actor_status messages with
        status='thinking' and status='idle' bracketing the NPC's response.
        """
        ...

    def test_idle_sent_on_llm_failure(self, client):
        """Even when the LLM agent raises an exception, the 'idle'
        actor_status message is still sent (not just on success).
        """
        ...


class TestWebSocketProtocol:
    """Test: WebSocket protocol changes from old SyncManager to User actor."""

    def test_entity_content_sync_relay(self, client):
        """entity_content_sync messages are relayed via user.send(exclude=sender).

        Connect two WebSocket clients. Client 1 sends entity_content_sync.
        Client 2 should receive it. Client 1 should NOT receive its own message.
        """
        ...

    def test_event_broadcast_format(self, client):
        """Events broadcast over WebSocket use the new format:
        {type: 'event', event: EventModel, scene_id: str}

        Not the old format: {type: 'chat_message', message: ...}
        """
        ...
```

### Test File: `/home/harald/src/sidestage/tests/integration/test_api_compliance.py` (Updates)

The existing `test_api_compliance.py` references `ChatMessageModel`, `ChatResponse.user_message`, and `SceneModel.messages`. These must be updated to use the new types. The existing tests should be migrated rather than duplicated.

Key changes needed in the existing file:

- Replace `from sidestage.models import ChatMessageModel` with `from sidestage.models import EventModel, EventType`
- `test_chat_endpoint_schema`: Assert response has `event` field (an `EventModel` dict with `event_type='ChatMessage'`), not `user_message` / `agent_message`
- `test_get_scene_messages`: Construct `EventModel` with `event_type=EventType.CHAT_MESSAGE` instead of `ChatMessageModel`. Assert response contains `body` field (not `message`). Scene no longer has embedded `messages` list -- events are persisted individually.
- Remove references to `SceneModel(messages=[...])` -- `SceneModel` no longer has a `messages` field

```python
# In test_chat_endpoint_schema:
# OLD:
#   assert "user_message" in data
#   assert "agent_message" in data
# NEW:
#   assert "event" in data
#   assert data["event"]["event_type"] == "ChatMessage"
#   assert data["event"]["id"].startswith("evt_")

# In test_get_scene_messages:
# OLD:
#   msg = ChatMessageModel(id="msg_1", ..., message="Hello")
#   self.orchestrator.campaign.storage.add_scene(SceneModel(id="scene_msg", ..., messages=[msg]))
# NEW:
#   evt = EventModel(id="evt_1", event_type=EventType.CHAT_MESSAGE, ..., body="Hello")
#   # Persist event individually to storage (not embedded in SceneModel)
#   # Then query via GET /v1/scenes/scene_msg/messages
```

### Test File: `/home/harald/src/sidestage/tests/integration/test_sync.py` (Deprecation)

The existing `test_sync.py` tests `SyncManager`-based broadcasting, which is eliminated in this refactoring. This file should either be:
1. **Deleted** -- its test scenarios are covered by the new `test_chat_flow.py` (specifically `TestWebSocketProtocol` and `TestFullChatFlow`)
2. **Or migrated** -- update the tests to use `campaign.user` instead of `sync_manager`

The recommended approach is to delete `test_sync.py` and rely on `test_chat_flow.py` for WebSocket integration coverage, since the entire broadcast mechanism has changed from `SyncManager` to `User.process()`.

### Test File: `/home/harald/src/sidestage/tests/integration/test_integration.py` (Updates)

The existing `test_integration.py` references old patterns:
- `scene.create_message(actor_id="user", text=...)` becomes `scene.chat(actor_id="user", text=...)`
- Polling for `m["message"]` field becomes `m["body"]`
- Polling for `m["character_id"] == "char_co_author"` still works (character IDs unchanged)
- `ChatResponse.agent_message` is gone; NPC responses arrive asynchronously via the event queue

```python
# In test_consecutive_messages:
# OLD:
#   if any(m["character_id"] == "char_co_author" and "helpful assistant" in m["message"] for m in messages):
# NEW:
#   if any(m["character_id"] == "char_co_author" and "helpful assistant" in m["body"] for m in messages):
```

---

## Implementation Details

### 1. Test Fixture Architecture

The integration test fixtures must set up a realistic system stack while mocking the LLM layer. The standard pattern is:

1. Create a `SidestageOrchestrator` with a temporary directory
2. Patch `Campaign._ensure_llm_availability` to avoid network checks
3. Patch `LiteLLMAgent` constructor in `actors.py` (not `character.py` as before, since `AgentActor` is replaced by `NPCActor`) to return a mock agent
4. The `Campaign` constructor creates `Campaign.user` (a `User` actor) automatically
5. `Campaign.get_character()` resolves actors based on `CharacterModel.owner`

The `client` fixture wraps the orchestrator's `FastAPI` app in a `TestClient`. WebSocket tests use `client.websocket_connect("/v1/ws")`.

### 2. Event Flow Verification Pattern

Because the event queue processes events asynchronously in a background task, integration tests that check for NPC responses or persistence need a polling or waiting strategy.

The recommended pattern (consistent with existing `test_integration.py`):

```python
import time

# Send a message
client.post("/v1/chat", json={"message": "Hello", "scene_id": "campaign_planning"})

# Poll for the result
max_retries = 10
for _ in range(max_retries):
    resp = client.get("/v1/scenes/campaign_planning/messages")
    messages = resp.json()
    if any(m["event_type"] == "ChatMessage" and m["actor_id"].startswith("agent:") for m in messages):
        break
    time.sleep(0.5)
```

For WebSocket tests, messages arrive in order since `TestClient` WebSocket is synchronous:

```python
with client.websocket_connect("/v1/ws") as ws:
    client.post("/v1/chat", json={"message": "Hello", "scene_id": "campaign_planning"})
    msg = ws.receive_json()
    assert msg["type"] == "event"
```

### 3. Thinking Indicator Verification

When an NPCActor processes an event, the Scene sends `actor_status` messages via `User.send()` before and after `actor.process()`. In WebSocket tests, these appear as additional messages interleaved with event broadcasts.

Expected message sequence for a user chat message with one NPC:
1. `{type: 'event', event: {event_type: 'ChatMessage', actor_id: 'user', ...}}` -- user's message broadcast
2. `{type: 'actor_status', character_id: '<npc_id>', scene_id: '...', status: 'thinking'}` -- NPC starts processing
3. `{type: 'event', event: {event_type: 'ChatMessage', actor_id: 'agent:<npc_id>', ...}}` -- NPC's response broadcast
4. `{type: 'actor_status', character_id: '<npc_id>', scene_id: '...', status: 'idle'}` -- NPC done processing

Note: The exact ordering of messages 3 and 4 depends on whether the response event dispatch completes before the idle signal. The idle signal is sent after `actor.process()` returns, and the response event is enqueued from within `process()` (which means it may be dispatched by the queue worker later). Tests should account for this by collecting all WebSocket messages and verifying the set contains the expected types rather than relying on strict ordering.

### 4. Tracing Verification

The tracing test uses OpenTelemetry's `InMemorySpanExporter` to capture spans without requiring Jaeger or any external collector.

Setup pattern:
```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

After sending a chat message and waiting for processing, inspect `exporter.get_finished_spans()` for:
- A span named `scene.process_event` with attributes `sidestage.scene.id` and `sidestage.event.type`
- The span should have a `Link` pointing to the span context captured at event creation time
- An `npc_actor.process` child span under the scene processing span

### 5. Multi-Character Deduplication Verification

To test that `Scene._dispatch()` deduplicates by `actor_id`:
1. Create two `CharacterModel` instances with `owner="user"` (both owned by the `User` actor)
2. Add both characters to the scene
3. Send a message
4. Verify the User receives exactly one broadcast (not two)

This can be verified by counting WebSocket messages or by patching `User.process()` to count invocations.

### 6. LLM Failure Verification

To test error event generation:
1. Patch the mock agent's `arun` to raise an exception
2. Send a chat message
3. Verify an event with `event_type='Error'` is broadcast over WebSocket and persisted to storage

```python
mock_agent.arun = AsyncMock(side_effect=Exception("LLM unavailable"))
```

### 7. ADJUST_GAMETIME Verification

To test gametime updates:
1. Activate a scene with a known `current_gametime`
2. Create and process an `ADJUST_GAMETIME` event with a new `gametime` value
3. Verify `scene.data.current_gametime` is updated

This test may need to bypass the REST API and work directly with the `Scene` object, since there is no REST endpoint for creating `ADJUST_GAMETIME` events (they are typically created programmatically by the Co-Author agent via tools).

### 8. Existing Test Migration Checklist

The following existing test files reference `ChatMessageModel` or old patterns and need updating. This section does NOT duplicate section-specific test changes but lists the files that need migration as part of the integration sweep:

| File | Change Needed |
|---|---|
| `/home/harald/src/sidestage/tests/integration/test_api_compliance.py` | Replace `ChatMessageModel` with `EventModel`, update `ChatResponse` assertions, remove `SceneModel.messages` usage |
| `/home/harald/src/sidestage/tests/integration/test_integration.py` | Update `m["message"]` to `m["body"]`, update polling assertions |
| `/home/harald/src/sidestage/tests/integration/test_sync.py` | Delete (replaced by `test_chat_flow.py`) or migrate to use `campaign.user` |
| `/home/harald/src/sidestage/tests/integration/test_frontend_integration.py` | Check for `ChatMessageModel` references; update if present |
| `/home/harald/src/sidestage/tests/unit/test_models.py` | Already handled in Section 01 |
| `/home/harald/src/sidestage/tests/unit/test_mcp_bridge.py` | Update `send_chat_message` assertions to use new `scene.chat()` signature and `{"event": ...}` response format |

### 9. Files Created

| File | Purpose |
|---|---|
| `/home/harald/src/sidestage/tests/integration/test_chat_flow.py` | New end-to-end integration tests for Actor-based chat flow |

### 10. Files Modified

| File | Purpose |
|---|---|
| `/home/harald/src/sidestage/tests/integration/test_api_compliance.py` | Migrate from `ChatMessageModel` to `EventModel`, update `ChatResponse` schema assertions |
| `/home/harald/src/sidestage/tests/integration/test_integration.py` | Update field references (`message` -> `body`), response format expectations |
| `/home/harald/src/sidestage/tests/integration/test_sync.py` | Delete (functionality covered by `test_chat_flow.py`) |

### 11. Files NOT Modified (Owned by Other Sections)

These files were modified in earlier sections and should not be touched here:
- `src/sidestage/models.py` (Section 01)
- `src/sidestage/event.py` (Section 01)
- `src/sidestage/actors.py` (Section 02)
- `src/sidestage/character.py` (Section 02)
- `src/sidestage/scene.py` (Section 04)
- `src/sidestage/orchestrator.py` (Section 06)
- `src/sidestage/schemas.py` (Section 06)
- `src/sidestage/mcp_bridge.py` (Section 06)
- `tests/unit/test_models.py` (Section 01)
- `tests/unit/test_event.py` (Section 01)
- `tests/unit/test_actors.py` (Section 02)
- `tests/unit/test_scene.py` (Section 04)