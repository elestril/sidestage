# Features

Sidestage is designed as a modular, AI-enhanced campaign manager.

## Core Platform

### Campaign Management
- **Multi-Campaign Support:** The orchestrator manages multiple distinct campaigns.
- **File-Based Storage:** Campaign data lives in `~/.sidestage/<campaign_name>`. SQLite stores chat logs; FalkorDB stores entities and relationships; `config.yml` holds LLM and graph settings.
- **Graph Database:** Entity data and relationships are stored in FalkorDB for fast graph traversal and vector search.
- **Campaign Health:** Runtime health tracking (HEALTHY / DEGRADED / UNHEALTHY) gates destructive operations and embedding availability.

### Real-Time Synchronization
- **WebSocket Architecture:** All clients (browser windows) stay in sync instantly.
- **Collaborative Editing:** Multiple users can edit entity descriptions simultaneously without conflicts.
- **Live Updates:** Changes made by the AI or other users appear immediately.

## World Building (Entity Management)

### Entity Database
- **Universal Entity Model:** All game objects (Characters, Locations, Items, Scenes, Events) share a common structure.
- **Graph Storage:** Entities are stored as multi-label nodes in FalkorDB (e.g., `:Entity:Character`). Properties, relationships, and indexes are managed via a versioned schema.
- **Markdown-First:** Entities can be edited and exchanged as Markdown files with YAML frontmatter.
- **Relationship Graph:** Entity connections are stored as typed, directed edges:
    - `LOCATED_IN` — Character at a Location.
    - `CONNECTS_TO` — Location adjacency (semantically bidirectional).
    - `AT_LOCATION` — Scene set at a Location.
    - `HAS_EVENT` — Scene contains an Event.
    - `INVOLVES` — Event references a Character.
    - `PARTICIPATES_IN` — Character present in a Scene.
- **Graph Queries:** Domain-specific queries over the graph — characters at a location, connected locations, scene events, N-hop subgraph extraction.

### Specialized Types
- **Characters:** Track location and inventory.
- **Locations:** Track connections (navigation graph).
- **Scenes:** Track active gametime and events.
- **Items:** Track properties.
- **Events:** Track historical occurrences with walltime and gametime timestamps.

### Campaign Import & Backup
- **Two-Phase Import:** Validate a `markdown/` directory tree, review warnings/errors, then execute the import into FalkorDB. Import is destructive — the graph is dropped and recreated.
- **Atomic Backup:** Export the full graph (entities, relationships, memories) to a `markdown/` directory tree with atomic swap to prevent partial writes. A `status.json` tracks backup metadata.
- **Roundtrip Fidelity:** The markdown format preserves all entity data, relationships, memories, and chat logs, enabling full backup/restore cycles.

## Memory System

### Memory as Living Documents
- **Explicit Updates:** Memories are not auto-generated summaries. They are living documents that characters and the DM update explicitly through agent tool calls.
- **Memory Types:**
    - `SCENE` — What happened in a scene, with three layers:
        - **Common** (`visibility: "common"`) — what everyone generally knows ("there was a bar fight").
        - **Canonical** (`visibility: "private"`, owned by DM) — the ground truth ("the assassin poisoned the drink").
        - **Personal** (`visibility: "private"`, owned by character) — individual recollection ("I observed from the second floor").
    - `CHARACTER` — One character's impression of another (always private).
    - `WORLD_FACT` — General world knowledge, either commonly known or restricted to a specific character.
- **Visibility Model:** Each memory has a `visibility` field (`"common"` or `"private"`), controlling who can access it. Context assembly rule: a character sees memories where `visibility == "common"` OR `owner_id == self`. Designed for future extension to rich ACLs without schema migration.

### Graph Structure
- Memories are stored as `:Memory` nodes (separate from the `:Entity` hierarchy).
- Linked via `HAS_MEMORY` (owner) and `ABOUT` (target) edges.
- Pattern: `(Character)-[:HAS_MEMORY]->(Memory)-[:ABOUT]->(Scene|Character|Entity)`

### Embeddings & Vector Search
- **Embedding Generation:** Text embeddings via LiteLLM `aembedding()`, supporting both local (sentence-transformers) and cloud (Vertex AI) models.
- **Vector Index:** FalkorDB vector index on memory embeddings for similarity search.
- **Background Processing:** Embeddings are generated asynchronously after memory creation/update.

### Context Assembly
Before each agent turn, a context block is assembled from the character's accessible memories and injected as a system message. The components, in order:
1. **World facts** — generally known facts about entities relevant to the scene.
2. **Common scene memory** — what everyone knows about this scene.
3. **Personal scene memory** — the character's private recollection.
4. **Character memories** — impressions of other characters present in the scene.
5. **Recent chat history** — the most recent verbatim messages, allocated 20% of the context window by default.

Token budgeting splits the context window between memory sections and chat history. Sections with no content are omitted.

## AI Co-Author

### Context-Aware Chat
- **Scene-Specific:** Chat history is compartmentalized by Scene.
- **World Knowledge:** The agent has access to the Entity Database via tools.
- **Memory-Enriched:** Agent prompts include assembled memory context — scene recollections, character impressions, and world facts relevant to the current character and scene.
- **Tool Use:** The agent can actively query the database (`list_characters`, `get_character`, `list_locations`) and update memories.

### Agent Memory Tools
- **Character Tools:** Update private scene memories and character impressions.
- **DM Tools:** Update common scene memories, canonical truth (DM-only), and world facts.

### Interactive Responses
- **Widget Embedding:** The agent can return structured data (e.g., an Entity Card) alongside text, which renders as an interactive element in the chat.

## Session Tools

### Scene Management
- **Multiple Scenes:** Organize the campaign into distinct scenes (e.g., "Tavern", "Dungeon", "Flashback").
- **Prose View:** A dedicated area for the static description of the current scene.

### Gametime Tracking
- **Granular Time:** Time is tracked in seconds and displayed as `Day D, HH:MM:SS`.
- **Per-Scene Clocks:** Different scenes can exist at different times (enabling split parties or flashbacks).
