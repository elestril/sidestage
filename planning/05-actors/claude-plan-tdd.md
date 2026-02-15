# TDD Plan: Actor Restructuring (05-actors)

Companion to `claude-plan.md`. Defines tests to write BEFORE implementing each section.

**Testing setup:** pytest, async tests, fixtures in `conftest.py`. Tests in `tests/unit/` and `tests/integration/`. Marker `@pytest.mark.llm` for LLM-dependent tests.

---

## 2. EventModel Restructuring

**Test file:** `tests/unit/test_models.py` (extend existing)

### 2.1 EventType Enum
```python
# Test: EventType enum has all expected values (CHAT_MESSAGE, JOIN, LEAVE, ADJUST_GAMETIME, ERROR)
# Test: EventType values are strings matching legacy entity_type names ("ChatMessage", "JoinEvent", etc.)
# Test: Visibility enum has PUBLIC, GM_ONLY, PRIVATE values
```

### 2.2 Flattened EventModel
```python
# Test: EventModel instantiation with each EventType
# Test: EventModel.entity_type ClassVar is "Event" (not an instance field)
# Test: EventModel.event_type is an instance field (per-event discriminator)
# Test: EventModel inherits from EntityModel (has id, name, body fields)
# Test: EventModel defaults — visibility=PUBLIC, body="", metadata={}
# Test: EventModel serialization via model_dump() includes event_type, excludes entity_type
# Test: EventModel with character_id and actor_id set correctly
# Test: EventModel walltime serializes to ISO string
# Test: EventModel name follows convention per event type (e.g., "Alice Message" for CHAT_MESSAGE)
```

### 2.3 Deleted Subclasses
```python
# Test: ChatMessageModel, JoinEventModel, LeaveEventModel, FastForwardEventModel no longer importable from models
```

### 2.4 SceneModel Changes
```python
# Test: SceneModel no longer has 'messages' field
# Test: SceneModel still has 'events' field (list of event IDs)
```

### 2.5 CharacterModel Changes
```python
# Test: CharacterModel has owner field, default "npc"
# Test: CharacterModel has system_actor field, default False
# Test: CharacterModel with owner="user-123" (player character)
# Test: CharacterModel with system_actor=True (Co-Author)
```

### 2.6 Schema Updates
```python
# Test: ChatResponse schema references EventModel (not ChatMessageModel)
```

---

## 3. Event Wrapper Class

**Test file:** `tests/unit/test_event.py` (new)

### 3.1-3.2 Event Wrapper
```python
# Test: Event wraps an EventModel instance
# Test: Event is not a Pydantic model (plain class / dataclass / attrs)
# Test: Event.span_context defaults to None
# Test: Event.scene defaults to None
# Test: Event.character returns None when scene is None
# Test: Event.character returns None when model.character_id is None
# Test: Event.character looks up character from scene.characters dict
```

### 3.3 Factory
```python
# Test: Event.from_model() creates Event from EventModel
# Test: Event.from_model() captures current span context when tracing is active
# Test: Event.from_model() sets span_context=None when no active span
# Test: Event.from_model() does NOT set scene reference (scene is None)
```

### 3.4 Queue Integration
```python
# Test: EventQueue accepts Event objects (not raw EventModel)
# Test: EventQueue handler receives Event objects
# Test: EventQueue start/stop lifecycle works with Event type
```

---

## 4. Actor Hierarchy

**Test file:** `tests/unit/test_actors.py` (new)

### 4.1 Base Actor
```python
# Test: Actor is abstract, cannot be instantiated directly
# Test: Actor requires actor_id
# Test: Actor.process() is abstract
```

### 4.2 NPCActor
```python
# Test: NPCActor is a concrete Actor subclass
# Test: NPCActor has system_actor flag, default False
# Test: NPCActor.process() with non-User-originated event returns without action
# Test: NPCActor.process() with non-CHAT_MESSAGE event returns without action
# Test: NPCActor.process() with User CHAT_MESSAGE calls LLM agent (@pytest.mark.llm)
# Test: NPCActor.process() enqueues response event via event.scene.process()
# Test: NPCActor.process() enqueues ERROR event on LLM failure
# Test: NPCActor with system_actor=True uses system_agent prompt template
# Test: NPCActor with system_actor=False uses default_npc/unseen_npc prompt template
```

### 4.3 User
```python
# Test: User is a concrete Actor subclass
# Test: User.connections starts empty
# Test: User.connect() accepts WebSocket and adds to connections
# Test: User.disconnect() removes WebSocket from connections
# Test: User.process() sends event data to all connected WebSockets
# Test: User.send() broadcasts to all connections
# Test: User.send() with exclude skips the excluded WebSocket
# Test: User.send() removes WebSocket on send failure (broken connection)
```

---

## 5. Character System Refactor

**Test file:** `tests/unit/test_character.py` (extend existing)

### 5.1 Character Registry
```python
# Test: Campaign.characters dict starts empty
# Test: Campaign.get_character() creates Character from CharacterModel
# Test: Campaign.get_character() caches — same model ID returns same Character instance
# Test: Character wraps CharacterModel as .data and Actor as .actor
```

### 5.2 Actor Resolution
```python
# Test: Campaign._resolve_actor() returns NPCActor for model with owner="npc"
# Test: Campaign._resolve_actor() returns campaign.user for model with owner != "npc"
# Test: Campaign._resolve_actor() sets system_actor=True on NPCActor when model.system_actor=True
```

### 5.3 Lifecycle
```python
# Test: Character.activate() initializes actor's LLM agent (for NPCActor)
# Test: Character.deactivate() cleans up actor state
```

---

## 6. Scene Event Loop Refactor

**Test file:** `tests/unit/test_scene.py` (extend existing)

### 6.4 Scene.process()
```python
# Test: Scene.process() sets event.scene = self before enqueueing
# Test: Scene.process() puts event on the queue
```

### 6.5 Scene._process_event()
```python
# Test: _process_event() persists EventModel to storage
# Test: _process_event() creates graph node for the event
# Test: _process_event() calls _dispatch() for all event types
# Test: _process_event() updates current_gametime for ADJUST_GAMETIME events
# Test: _process_event() does NOT update gametime for other event types
```

### 6.6 Scene._dispatch()
```python
# Test: _dispatch() calls process() on every present actor
# Test: _dispatch() deduplicates by actor_id (same User controlling 2 characters dispatched once)
# Test: _dispatch() sends thinking status to Users before calling NPCActor.process()
# Test: _dispatch() sends idle status to Users after NPCActor.process() completes
# Test: _dispatch() sends idle status even when NPCActor.process() raises
# Test: _dispatch() does NOT send thinking status for User actors
```

### 6.7 Scene.create_event()
```python
# Test: create_event() returns Event wrapping EventModel
# Test: create_event() generates ID with evt_ prefix
# Test: create_event() sets scene_id, gametime, walltime, event_type
```

### 6.8 Scene.chat()
```python
# Test: chat() creates CHAT_MESSAGE event with given text and character_id
# Test: chat() enqueues event via self.process()
# Test: chat() accepts raw parameters (actor_id, text, character_id)
```

---

## 7. Tracing Integration

**Test file:** `tests/unit/test_tracing.py` (extend existing)

```python
# Test: Event.from_model() captures span context from active tracer
# Test: Scene._process_event() creates new root span with link to event.span_context
# Test: Scene._process_event() sets sidestage.scene.id and sidestage.event.type span attributes
# Test: NPCActor.process() creates child span under scene's processing span
```

---

## 8. User & WebSocket Integration

**Test file:** `tests/integration/test_websocket.py` (extend existing)

```python
# Test: WebSocket connect registers with campaign.user (not SyncManager)
# Test: WebSocket disconnect removes from campaign.user
# Test: Incoming chat_message routes to scene.chat() with raw parameters
# Test: entity_content_sync rebroadcast via user.send(exclude=sender)
# Test: Event dispatch to User sends event JSON over WebSocket
# Test: actor_status thinking/idle messages sent over WebSocket during NPC processing
```

---

## 9. Campaign Agent Integration

**Test file:** `tests/unit/test_campaign.py` (extend existing)

```python
# Test: Campaign creates User at startup
# Test: Campaign no longer has Campaign.agent field (raw LiteLLMAgent)
# Test: Co-Author character resolved as NPCActor with system_actor=True
# Test: Co-Author NPCActor gets world-building tools (create_character, list_characters, etc.)
# Test: Regular NPC NPCActor gets memory tools only
```

---

## 10. Storage and Persistence

**Test file:** `tests/unit/test_storage.py` (extend existing), `tests/unit/test_graph_entities.py` (extend/new)

### 10.1-10.2 Storage and Graph
```python
# Test: entity_to_labels() for EventModel with CHAT_MESSAGE returns ["Entity", "Event", "ChatMessage"]
# Test: entity_to_labels() for EventModel with JOIN returns ["Entity", "Event", "JoinEvent"]
# Test: entity_to_labels() for each EventType produces correct 3-label list
# Test: node_to_entity() deserializes Event node back to EventModel with correct event_type
# Test: EventModel round-trips through graph (write node, read node, compare)
# Test: LABEL_TO_MODEL maps each EventType value string to EventModel class
```

### 10.3 Entity Serialization
```python
# Test: entity_to_markdown() for EventModel includes event_type in frontmatter
# Test: markdown_to_entity() for Event type reconstructs EventModel with correct event_type
# Test: TYPE_MAP maps EventType value strings to EventModel
# Test: TYPE_TO_SUBDIR maps event types to "events"
# Test: frontmatter_dict_to_entity() handles type="Event" with event_type field
```

### 10.4 Graph Property Handling
```python
# Test: metadata dict serialized as JSON string in graph properties
# Test: metadata JSON string deserialized back to dict from graph
# Test: walltime datetime serialized to ISO string in graph properties
# Test: visibility and event_type stored as string values in graph
```

### 10.5 Clean Break
```python
# Test: EventModel with model_config extra='ignore' gracefully handles unknown fields
```

---

## 11. Frontend Changes

**Test approach:** Manual verification and TypeScript compilation. No automated frontend tests specified in current project.

```
# Verify: types.ts compiles with EventModel interface and EventType type
# Verify: ChatWidget renders event.body for chat messages
# Verify: ChatWidget renders thinking indicator for actors in thinkingActors set
# Verify: ChatWidget renders ERROR events with distinct styling
# Verify: WebSocket handler processes 'event' type messages
# Verify: WebSocket handler processes 'actor_status' messages
# Verify: AppContext messages state uses EventModel[] type
```

---

## 12. API Changes

**Test file:** `tests/integration/test_api.py` (extend existing)

```python
# Test: POST /v1/chat returns ChatResponse with event field (EventModel)
# Test: GET /v1/scenes/{id}/messages returns List[EventModel]
# Test: MCP bridge send_chat_message calls scene.chat() with raw parameters
# Test: MCP bridge send_chat_message returns {"event": ...} format
# Test: WebSocket broadcast uses 'event' message type (not 'chat_message')
```

---

## 13. Integration Tests (End-to-End)

**Test file:** `tests/integration/test_chat_flow.py` (new)

```python
# Test: Full chat flow — user sends message -> event created -> persisted -> dispatched to User (WebSocket) and NPCActor
# Test: NPCActor response -> new event created -> persisted -> dispatched to User (WebSocket) (@pytest.mark.llm)
# Test: LLM failure -> ERROR event created -> dispatched to User
# Test: Multiple characters same User -> dispatch deduplicates by actor_id
# Test: Co-Author NPCActor participates in scene like regular NPC (@pytest.mark.llm)
# Test: ADJUST_GAMETIME event updates scene gametime
# Test: Event tracing — span links connect user request trace to scene processing trace
```
