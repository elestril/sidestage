# agent

Implements: [sidestage#actor](/specs/sidestage.md#actor)

## Overview {#overview}

The agent system provides LLM-powered chat within scene contexts, with access
to the entity database and memory system via tools. Agents are powered by
LiteLLM.

## Context-Aware Chat {#context-aware-chat}

### Scene-Specific Context {#scene-specific}

Chat history MUST be compartmentalized by scene. The agent MUST only see
messages from the current scene.

### Memory-Enriched Prompts {#memory-enriched}

Agent prompts MUST include assembled memory context — scene recollections,
character impressions, and world facts relevant to the current character and
scene. See [memory#context-assembly](/specs/implementation/memory.md#context-assembly) for
the full specification.

### World Knowledge Access {#world-knowledge}

The agent MUST have access to the entity database via tools during chat.

## Agent Tools {#agent-tools}

### Entity Tools {#entity-tools}

The agent MUST have access to the following entity tools:

- `list_entities` — List all entities in the campaign (filterable by type).
- `get_entity_markdown` — Get markdown representation of an entity.
- `list_scenes` — List all scenes.
- `get_scene_messages` — Get message history for a scene.
- `send_chat_message` — Send a chat message within a scene.
- `join_scene` — Add a character to a scene's cast.
- `leave_scene` — Remove a character from a scene's cast.

These tools are shared with the MCP endpoint (see
[api#mcp-tools](/specs/implementation/api.md#mcp-tools)).

> TODO(<a id="todo-unified-entity-tools"></a>todo-unified-entity-tools): Replace
> `list_characters`, `get_character`, and `list_locations` with unified
> `list_entities` and `get_entity_markdown` tools.

### Memory Tools {#memory-tools}

#### Character-Level Tools {#character-tools}

Agents operating as a character (see
[sidestage#character](/specs/sidestage.md#character)) MUST be able to:

<a id="tool-update-scene-memory"></a>
- Update private scene memories.

<a id="tool-update-character-impression"></a>
- Update character impressions.

#### Privileged Tools {#privileged-tools}

Agents operating as a privileged character (see
[sidestage#character](/specs/sidestage.md#character)) MUST be able to:

<a id="tool-update-common-scene"></a>
- Update common scene memories.

<a id="tool-update-canonical"></a>
- Update canonical truth (privileged-only).

<a id="tool-update-world-fact"></a>
- Update world facts.

## Interactive Responses {#interactive-responses}

### Widget Embedding {#widget-embedding}

<a id="widget-entity-card"></a>
The agent MAY return structured data alongside text in the `metadata.widget`
field. The structured data MUST render as an interactive element in the chat
UI.
