# `sidestage.memory.tools`

Agent-callable memory tools for NPC characters and the DM/Co-Author.

## Classes

### `DmMemoryTools`

Memory tools for the DM / Co-Author agent.

Manages world-state memories: common scene memories, canonical
(DM-truth) scene memories, and world facts.

#### `__init__(client: GraphClient, embed_config: LLMConfig | None, health: CampaignHealth, dm_actor_id: str)`

#### `add_world_fact(about_entity_id: str, content: str, visibility: str = 'common') -> str` *async*

Add or update a world fact about an entity.

World facts are persistent knowledge about locations, items, or
other entities. Common facts are visible to all; private facts
are hidden knowledge.

Args:
    about_entity_id: The entity this fact is about.
    content: The fact content.
    visibility: "common" (default) or "private".

Returns:
    JSON confirmation with memory ID.

#### `update_canonical_memory(scene_id: str, content: str, gametime: int | None = None) -> str` *async*

Update the canonical (DM truth) scene memory.

This is the authoritative account of what happened -- only the DM
can see this. Use it to record the true events behind the scenes.

Args:
    scene_id: The scene this memory is about.
    content: The canonical account of events.
    gametime: In-game time as an integer (seconds since game epoch),
              or omit to leave unchanged.

Returns:
    JSON confirmation with memory ID.

#### `update_common_memory(scene_id: str, content: str, gametime: int | None = None) -> str` *async*

Update the common scene memory -- what everyone generally knows.

This is shared knowledge about what happened in a scene. All
characters can access common scene memories.

Args:
    scene_id: The scene this memory is about.
    content: The common understanding of events in this scene.
    gametime: In-game time as an integer (seconds since game epoch),
              or omit to leave unchanged.

Returns:
    JSON confirmation with memory ID.

### `MemoryTools`

Memory update tools for character agents.

Each instance is bound to a specific character (owner_id) and scene.
All memories created are private (visibility="private").

#### `__init__(client: GraphClient, embed_config: LLMConfig | None, health: CampaignHealth, owner_id: str, scene_id: str)`

#### `update_character_memory(about_character_id: str, content: str, gametime: int | None = None) -> str` *async*

Update your memory about another character.

Call this when you learn something new about a character you're
interacting with. This replaces your previous memory about them.

Args:
    about_character_id: The ID of the character this memory is about.
    content: Your updated impression/knowledge of this character.
    gametime: In-game time as an integer (seconds since game epoch),
              or omit to leave unchanged.

Returns:
    JSON confirmation with memory ID.

#### `update_scene_memory(content: str, gametime: int | None = None) -> str` *async*

Update your memory of the current scene.

Call this when something noteworthy happens that you want to remember
about this scene. Your scene memory is a living document -- include
everything important, as this replaces your previous scene memory.

Args:
    content: Your updated memory of this scene. Include key events,
             decisions, and anything you want to remember.
    gametime: In-game time as an integer (seconds since game epoch),
              or omit to leave unchanged.

Returns:
    JSON confirmation with memory ID.
