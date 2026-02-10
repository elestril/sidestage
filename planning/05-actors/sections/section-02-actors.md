Now I have all the context needed. Let me produce the section content.

# Section 02: Actor Hierarchy and Character System Refactor

## Overview

This section introduces the Actor abstraction layer and refactors the Character system. It covers:

- **Actor ABC** (`Actor`): base class for anything that controls Characters in a Scene
- **NPCActor**: replaces the current `AgentActor` with LLM-driven behavior and `system_actor` differentiation
- **User**: represents a human player, owns WebSocket connections, serves as the broadcast mechanism
- **Character refactor**: simplified runtime wrapper pairing `CharacterModel` with an `Actor`
- **Campaign-scoped character registry**: `Campaign.get_character()` with actor resolution logic
- **Lifecycle management**: `activate()` / `deactivate()` for Characters and their Actors

**Depends on:** section-01-event-model (EventModel, EventType, Event wrapper, EventQueue changes must be complete)

**Blocks:** section-04-scene-loop, section-06-orchestrator

---

## Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/sidestage/actors.py` | **Create** | Actor ABC, NPCActor, User classes |
| `src/sidestage/character.py` | **Major refactor** | Simplified Character wrapper (remove AgentActor) |
| `src/sidestage/campaign.py` | **Modify** | Add character registry, `get_character()`, `_resolve_actor()`, create User at startup |
| `data/prompts/system_agent.txt` | **Create** | System-level prompt template for the Co-Author NPCActor |
| `tests/unit/test_actors.py` | **Create** | Tests for Actor, NPCActor, User |
| `tests/unit/test_character.py` | **Create** | Tests for Character registry and actor resolution |

---

## Tests (Write First)

### Test File: `tests/unit/test_actors.py`

This is a new file. All tests use the `Event` wrapper and `EventModel` from section-01.

```python
"""Tests for the Actor hierarchy: Actor ABC, NPCActor, User."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sidestage.actors import Actor, NPCActor, User
from sidestage.event import Event
from sidestage.models import EventModel, EventType, Visibility


# --- 4.1 Base Actor ---

# Test: Actor is abstract, cannot be instantiated directly
# Attempting Actor(actor_id="test") should raise TypeError

# Test: Actor requires actor_id
# Concrete subclass must accept and store actor_id

# Test: Actor.process() is abstract
# Subclass that does not implement process() cannot be instantiated


# --- 4.2 NPCActor ---

# Test: NPCActor is a concrete Actor subclass
# NPCActor(actor_id="agent:char_1") should instantiate without error

# Test: NPCActor has system_actor flag, default False
# npc = NPCActor(actor_id="agent:char_1", ...)
# assert npc.system_actor is False

# Test: NPCActor.process() with non-User-originated event returns without action
# Create event where event.character.actor is an NPCActor (not a User)
# Calling npc.process(event) should return without calling the LLM

# Test: NPCActor.process() with non-CHAT_MESSAGE event returns without action
# Create event with event_type=EventType.JOIN
# Calling npc.process(event) should return without calling the LLM

# Test: NPCActor.process() with User CHAT_MESSAGE calls LLM agent
# @pytest.mark.llm — mock the LLM agent's arun() method
# Verify arun() was called with the message body

# Test: NPCActor.process() enqueues response event via event.scene.process()
# Mock agent.arun() to return content, verify event.scene.process() was awaited

# Test: NPCActor.process() enqueues ERROR event on LLM failure
# Mock agent.arun() to raise, verify event.scene.process() was called with an ERROR event

# Test: NPCActor with system_actor=True uses system_agent prompt template
# Verify _update_prompt loads data/prompts/system_agent.txt

# Test: NPCActor with system_actor=False uses default_npc/unseen_npc prompt template
# Verify _update_prompt loads data/prompts/default_npc.txt or unseen_npc.txt


# --- 4.3 User ---

# Test: User is a concrete Actor subclass
# User(actor_id="user") should instantiate without error

# Test: User.connections starts empty
# user = User(actor_id="user")
# assert user.connections == []

# Test: User.connect() accepts WebSocket and adds to connections
# Mock WebSocket, call user.connect(ws), verify ws in user.connections

# Test: User.disconnect() removes WebSocket from connections
# Add ws, call user.disconnect(ws), verify ws not in user.connections

# Test: User.process() sends event data to all connected WebSockets
# Connect two mock WebSockets, call user.process(event)
# Verify send_json was called on both with {"type": "event", "event": ..., "scene_id": ...}

# Test: User.send() broadcasts to all connections
# Connect two mock WebSockets, call user.send(message)
# Verify both received the message

# Test: User.send() with exclude skips the excluded WebSocket
# Connect two mock WebSockets, call user.send(message, exclude=ws1)
# Verify only ws2 received the message

# Test: User.send() removes WebSocket on send failure (broken connection)
# Connect a mock WebSocket that raises on send_json
# Call user.send(message), verify the broken ws was removed from connections
```

### Test File: `tests/unit/test_character.py`

This is a new file testing the refactored Character class and Campaign character registry.

```python
"""Tests for Character runtime wrapper and Campaign character registry."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sidestage.character import Character
from sidestage.actors import NPCActor, User, Actor
from sidestage.models import CharacterModel


# --- 5.1 Character Registry ---

# Test: Campaign.characters dict starts empty
# campaign = Campaign(...)  (with mocked dependencies)
# assert campaign.characters == {}

# Test: Campaign.get_character() creates Character from CharacterModel
# model = CharacterModel(id="char_1", name="Alice", body="A warrior", owner="npc")
# char = campaign.get_character(model)
# assert isinstance(char, Character)
# assert char.data is model

# Test: Campaign.get_character() caches -- same model ID returns same Character instance
# char1 = campaign.get_character(model)
# char2 = campaign.get_character(model)
# assert char1 is char2

# Test: Character wraps CharacterModel as .data and Actor as .actor
# char = Character(model=model, actor=some_actor)
# assert char.data is model
# assert char.actor is some_actor


# --- 5.2 Actor Resolution ---

# Test: Campaign._resolve_actor() returns NPCActor for model with owner="npc"
# model = CharacterModel(id="char_1", name="Alice", body="...", owner="npc")
# actor = campaign._resolve_actor(model)
# assert isinstance(actor, NPCActor)

# Test: Campaign._resolve_actor() returns campaign.user for model with owner != "npc"
# model = CharacterModel(id="char_2", name="Bob", body="...", owner="user-123")
# actor = campaign._resolve_actor(model)
# assert actor is campaign.user

# Test: Campaign._resolve_actor() sets system_actor=True on NPCActor when model.system_actor=True
# model = CharacterModel(id="char_co_author", name="Co-Author", body="...", owner="npc", system_actor=True)
# actor = campaign._resolve_actor(model)
# assert isinstance(actor, NPCActor)
# assert actor.system_actor is True


# --- 5.3 Lifecycle ---

# Test: Character.activate() initializes actor's LLM agent (for NPCActor)
# Verify that after activate(), the NPCActor has a configured agent

# Test: Character.deactivate() cleans up actor state
# Verify that after deactivate(), cleanup has occurred
```

---

## Implementation Details

### New File: `src/sidestage/actors.py`

This file contains the entire Actor hierarchy. It is new and separate from `character.py` because the responsibility is fundamentally different: actors define behavior, while Character is a runtime wrapper pairing data with an actor.

#### Actor ABC

```python
from abc import ABC, abstractmethod

class Actor(ABC):
    """Base class for anything that controls Characters in a Scene."""

    def __init__(self, actor_id: str):
        self.actor_id = actor_id

    @abstractmethod
    async def process(self, event: "Event") -> None:
        """Handle an event. May enqueue response events via event.scene.process()."""
```

Key points:
- `actor_id` is a string identifier unique per actor instance
- `process()` returns `None` -- actors enqueue responses by calling `event.scene.process(new_event)` rather than returning events
- Actors receive ALL events from the scene dispatch; they decide internally which to react to

#### NPCActor

Replaces the current `AgentActor` class (which will be deleted from `character.py`). One NPCActor per NPC Character (1:1 mapping).

```python
class NPCActor(Actor):
    """LLM-driven actor controlling an NPC character."""

    def __init__(self, actor_id: str, system_actor: bool = False, ...):
        super().__init__(actor_id)
        self.system_actor = system_actor
        self.agent: LiteLLMAgent | None = None
        # ... other fields for LLM config, context, etc.

    async def process(self, event: Event) -> None:
        """React to events from User actors by generating LLM responses."""
```

**process() logic (pseudocode):**

1. Guard: Check if the originating character's actor is a `User` instance AND the event type is `CHAT_MESSAGE`. If either condition fails, return immediately. This is how NPCs skip their own messages and non-chat events.
   ```python
   if not (event.model.event_type == EventType.CHAT_MESSAGE
           and event.character
           and isinstance(event.character.actor, User)):
       return
   ```

2. Assemble memory context using `memory.context.assemble_context()`, passing `self.recent_events` (a reference to Scene's event list) for chat history.

3. Call `self.agent.arun(event.model.body, context=context_text)`.

4. On success with content: create an `EventModel` with `event_type=EventType.CHAT_MESSAGE`, wrap in `Event.from_model()`, enqueue via `await event.scene.process(response_event)`.

5. On LLM failure: create an `EventModel` with `event_type=EventType.ERROR`, the error details in `body`, wrap in `Event.from_model()`, enqueue via `await event.scene.process(error_event)`.

**Context access:** NPCActor receives a reference to the Scene's runtime `events: list[EventModel]` list during initialization. This is the same pattern used by the current `AgentActor` which receives `scene_logic` and reads `scene_logic.messages`. The reference is read-only and used by `assemble_context()` for chat history.

**Prompt and tool differentiation based on `system_actor`:**

- `system_actor=True` (Co-Author character):
  - Loads prompt template from `data/prompts/system_agent.txt`
  - Gets Campaign-level world-building tools: `create_character`, `list_characters`, `create_location`, etc.

- `system_actor=False` (regular NPCs):
  - Loads prompt template from `data/prompts/default_npc.txt` or `data/prompts/unseen_npc.txt` based on `character.unseen`
  - Gets memory tools only: `update_scene_memory`, `update_character_memory`

**`_update_prompt()` method:** Preserves the existing pattern from `AgentActor._update_prompt()`. Reads the template file, formats with character attributes, instantiates `LiteLLMAgent` with the appropriate tools. The key difference is the branching on `self.system_actor` to select the template and tool set.

The existing `AgentActor._update_prompt()` code (in `/home/harald/src/sidestage/src/sidestage/character.py` lines 53-103) provides the blueprint. The new version adds a branch at the top:

```python
def _update_prompt(self) -> None:
    project_root = Path(__file__).parent.parent.parent
    prompt_dir = project_root / "data" / "prompts"

    if self.system_actor:
        template_name = "system_agent.txt"
    elif self.character.unseen:
        template_name = "unseen_npc.txt"
    else:
        template_name = "default_npc.txt"

    # ... rest follows existing pattern: load template, format, configure tools ...
```

For the tools, the branching is:
```python
if self.system_actor:
    # World-building tools from WorldTools
    tools = [world_tools.create_character, world_tools.list_characters, ...]
else:
    # Memory tools from MemoryTools
    tools = [memory_tools.update_scene_memory, memory_tools.update_character_memory]
```

#### User

```python
class User(Actor):
    """Represents a human player. Owns WebSocket connections."""

    def __init__(self, actor_id: str = "user"):
        super().__init__(actor_id)
        self.connections: list[WebSocket] = []

    async def process(self, event: Event) -> None:
        """Send event to all WebSocket connections."""

    async def send(self, message: dict, exclude: WebSocket | None = None) -> None:
        """Send to all connections, optionally excluding sender."""

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a WebSocket connection."""

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection."""
```

Key points:
- One User per Campaign, created at Campaign startup
- `process()` sends the event as JSON to all WebSocket connections -- this IS the broadcast mechanism (replaces `SyncManager.broadcast()` and `Scene._broadcast_fn`)
- `send()` is a general-purpose method for sending arbitrary messages (used for `entity_content_sync`, `actor_status`, etc.)
- `connect()` calls `ws.accept()` and appends; `disconnect()` removes
- On send failure, the broken WebSocket is silently removed from `connections`

The `process()` method sends this shape:
```python
{"type": "event", "event": event.model.model_dump(), "scene_id": event.model.scene_id}
```

### Refactored File: `src/sidestage/character.py`

The file is significantly simplified. `AgentActor` is deleted entirely (its logic moves to `NPCActor` in `actors.py`). The `Character` class becomes a thin wrapper:

```python
class Character:
    """Runtime wrapper for a CharacterModel with an associated Actor."""

    def __init__(self, model: CharacterModel, actor: Actor):
        self.data = model
        self.actor = actor

    async def activate(self) -> None:
        """Initialize the actor's LLM agent (for NPCActor)."""

    async def deactivate(self) -> None:
        """Clean up actor state."""
```

Key changes from the current `Character`:
- Constructor takes `(model, actor)` instead of `(character, scene_logic, graph_client, ...)`. All the runtime configuration dependencies move to NPCActor's constructor.
- No more `AgentActor` creation inside `activate()` -- the Actor is injected at construction time by `Campaign.get_character()`.
- `activate()` tells the Actor to initialize its LLM agent (for NPCActors). For User actors, this is a no-op.
- `deactivate()` cleans up the Actor's agent state.

### Modified File: `src/sidestage/campaign.py`

Campaign gains a character registry and User instance. Key additions:

```python
class Campaign:
    def __init__(self, name: str, base_dir: Path):
        # ... existing init ...
        self.characters: Dict[str, Character] = {}
        self.user = User(actor_id="user")
        # ... rest of init ...

    def get_character(self, model: CharacterModel) -> Character:
        """Get or create a Character instance for the given model."""
        if model.id in self.characters:
            return self.characters[model.id]
        actor = self._resolve_actor(model)
        char = Character(model=model, actor=actor)
        self.characters[model.id] = char
        return char

    def _resolve_actor(self, model: CharacterModel) -> Actor:
        """Determine which Actor controls this character."""
        if model.owner == "npc":
            return NPCActor(
                actor_id=f"agent:{model.id}",
                system_actor=model.system_actor,
                # ... LLM config, tools, etc.
            )
        else:
            return self.user
```

**Important:** `get_character()` caches by `model.id`. Calling it with the same character ID returns the same `Character` instance. This ensures that a Character's Actor is shared and consistent across scenes.

**`_resolve_actor()` logic:**
- `model.owner == "npc"` (default): creates a new NPCActor. The `system_actor` flag is read from the model to configure the prompt template and tool set.
- `model.owner` is any other string (a user ID): returns `self.user`, the Campaign's single User instance. All player characters share this User actor -- dispatch deduplication in Scene._dispatch() prevents sending the same event to the same User twice.

The `Campaign.agent` field (raw `LiteLLMAgent` for the Co-Author) is **not removed in this section** -- that happens in section-06-orchestrator when the full integration is wired up. This section focuses on building the Actor infrastructure.

**Campaign shutdown:** Add `self.characters = {}` to `Campaign.shutdown()` to clean up the registry.

### New File: `data/prompts/system_agent.txt`

This prompt template is used by the Co-Author NPCActor (`system_actor=True`). It contains world-building instructions, distinct from the NPC character prompts:

```
You are the Sidestage Co-Author, a world-building assistant for this tabletop RPG campaign. You help the game master create and manage the game world.

You have access to tools for creating and managing characters, locations, and items. Use these tools to help build the campaign world.

STRICT PERSONA: NEVER identify as a 'large language model'. You are strictly the Sidestage Co-Author.
DATABASE-ONLY KNOWLEDGE: You know NOTHING about Characters, locations, or items except what is in your database.
TOOL-FIRST: If asked about characters, world details, or 'which characters do you know?', you MUST call `list_characters` immediately.
NEVER list famous characters from other games unless they were created in THIS campaign.
TONE: Helpful and collaborative.

---
{character.body}
```

This moves the Co-Author's instructions (currently hardcoded in `Campaign.create_agent()` at `/home/harald/src/sidestage/src/sidestage/campaign.py` lines 130-151) into a template file, consistent with how other NPC prompts work.

---

## Background Context

### Current State (What Exists)

The current codebase has:

- **`AgentActor`** in `character.py`: tightly coupled to `Scene` via `scene_logic` parameter. Receives `EventModel`, checks `isinstance(event, ChatMessageModel)`, calls `scene_logic.create_message()` and `scene_logic.queue.put()` to enqueue responses.
- **`Character`** in `character.py`: runtime wrapper that creates its own `AgentActor` during `activate()`. Takes many constructor parameters (`scene_logic`, `graph_client`, `embed_config`, `health`, etc.).
- **`SyncManager`** in `sync.py`: manages WebSocket connections, provides `broadcast()` method. The Orchestrator owns a `SyncManager` and wires it to Scene via `set_broadcast()` callback.
- **`Campaign`**: creates a raw `LiteLLMAgent` as `self.agent` for the Co-Author. No character registry -- Scene creates Character instances directly during `activate()`.

### What This Section Changes

- `AgentActor` is **deleted** from `character.py` and replaced by `NPCActor` in the new `actors.py`
- `Character` is **simplified** to a thin `(model, actor)` wrapper
- `User` actor is **created** to replace `SyncManager` for WebSocket broadcast
- `Campaign` gains a **character registry** (`self.characters` dict) and **actor resolution** logic
- `Campaign` creates a **User** at startup (`self.user = User(actor_id="user")`)

### CharacterModel Changes (from section-01)

Section-01 adds two fields to `CharacterModel`:
- `owner: str = "npc"` -- `"npc"` for NPC characters, a user_id string for player characters
- `system_actor: bool = False` -- `True` for the Campaign Co-Author character

These fields drive actor resolution in `Campaign._resolve_actor()`.

### Event/EventModel (from section-01)

Section-01 establishes:
- Flattened `EventModel` with `event_type: EventType` instance field
- `Event` runtime wrapper class with `.scene` reference and `.character` property
- `EventType` enum: `CHAT_MESSAGE`, `JOIN`, `LEAVE`, `ADJUST_GAMETIME`, `ERROR`

NPCActor's `process()` method uses `event.model.event_type` and `event.character.actor` (via the `Event` wrapper) to determine whether to react.

### Import Dependencies

`actors.py` needs:
- `Event` from `sidestage.event` (section-01)
- `EventModel`, `EventType`, `Visibility` from `sidestage.models` (section-01)
- `LiteLLMAgent` from `sidestage.agent`
- `CharacterModel` from `sidestage.models`
- `WebSocket` from `fastapi`

`character.py` needs:
- `Actor` from `sidestage.actors`
- `CharacterModel` from `sidestage.models`

`campaign.py` additions need:
- `Character` from `sidestage.character`
- `NPCActor`, `User` from `sidestage.actors`

### Circular Import Prevention

`actors.py` references `Event` which has a `.character` property returning a `Character`. This creates a potential circular import (`actors` -> `event` -> `character` -> `actors`). Use `TYPE_CHECKING` guards:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sidestage.event import Event
    from sidestage.character import Character
```

The `Event.character` property in `event.py` similarly uses `TYPE_CHECKING` for the `Character` type hint.

---

## Implementation Notes

**NPCActor runtime dependencies:** `_resolve_actor()` creates NPCActor with only `actor_id` and `system_actor`. Full runtime dependencies (character, scene_logic, graph_client, etc.) are wired during scene activation in later sections (section-04/06). The `_update_prompt()` method gracefully returns without creating an agent when `scene_logic` is None.

**User.connect() calls ws.accept():** Added per plan requirement (code review auto-fix).

**Event IDs use uuid4:** Changed from `f"evt_{char_id}_{gametime}"` to `f"evt_{uuid.uuid4().hex[:8]}"` per code review to avoid duplicates.

**Campaign.get_scene_messages() renamed to get_scene_events():** Returns event IDs (list[str]) instead of ChatMessageModel list, since messages field was removed from SceneModel in section-01.

**29 tests total:** 15 in test_actors.py (6 sync + 9 async), 4 in test_character.py (2 sync + 2 async). Campaign registry and LLM integration tests deferred to later sections.