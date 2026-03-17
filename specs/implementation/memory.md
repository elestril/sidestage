# memory

Implements: [sidestage#character](/specs/sidestage.md#character),
[sidestage#principle-living-memory](/specs/sidestage.md#principle-living-memory)

## Overview {#overview}

Memories are living documents updated explicitly through agent tool calls.
They are NOT auto-generated summaries.

## Memory Model {#memory-model}

Each memory MUST have the following fields:

| Field              | Type     | Description                            |
|--------------------|----------|----------------------------------------|
| `id`               | string   | UUID (prefixed, e.g., `mem_abc123`)    |
| `content`          | string   | The living document text               |
| `memory_type`      | string   | `scene`, `character`, or `world_fact`  |
| `visibility`       | string   | `common` or `private`                  |
| `embedding`        | float[]? | Vector embedding for similarity search |
| `owner_id`         | string?  | Character who owns this memory         |
| `target_id`        | string   | Entity this memory is about            |
| `created_at`       | float    | Unix timestamp                         |
| `updated_at`       | float    | Unix timestamp                         |
| `gametime`         | int?     | In-game time of the memory             |
| `access_count`     | int      | Number of times accessed               |
| `last_accessed_at` | float?   | Unix timestamp of last access          |

## Memory Types {#memory-types}

### Scene Memory {#type-scene}

Scene memories (`memory_type: "scene"`) record what happened in a scene. They
MUST support three layers:

<a id="visibility-common"></a>
- **Common** (`visibility: "common"`) — Shared knowledge visible to all
  characters.

<a id="visibility-canonical"></a>
- **Canonical** (`visibility: "private"`, owned by privileged character — see
  [sidestage#character](/specs/sidestage.md#character)) — The authoritative
  ground truth.

<a id="visibility-personal"></a>
- **Personal** (`visibility: "private"`, owned by character) — Individual
  recollection from a specific character's perspective.

### Character Memory {#type-character}

Character memories (`memory_type: "character"`) represent one character's
impression of another. Character memories MUST always be private
(`visibility: "private"`).

### World Fact {#type-world-fact}

World facts (`memory_type: "world_fact"`) represent general world knowledge.
World facts MAY be commonly known (`visibility: "common"`) or restricted to a
specific character (`visibility: "private"`).

## Visibility Model {#visibility}

Each memory MUST have a `visibility` field set to either `"common"` or
`"private"`.

<a id="visibility-rule"></a>
**Context assembly rule:** A character MUST see memories where
`visibility == "common"` OR `owner_id == self`.

The visibility model is designed for future extension to rich ACLs without
schema migration.

## Graph Structure {#graph-structure}

Memories MUST be stored as `:Memory` nodes, separate from the `:Entity`
hierarchy.

### Edges {#memory-edges}

<a id="edge-has-memory"></a>
- `HAS_MEMORY` — Links an owner to a memory.

<a id="edge-about"></a>
- `ABOUT` — Links a memory to its target entity.

The pattern MUST be:
`(Character)-[:HAS_MEMORY]->(Memory)-[:ABOUT]->(Scene|Character|Entity)`

## Embeddings and Vector Search {#embeddings}

### Embedding Generation {#embedding-generation}

Text embeddings MUST be generated via LiteLLM `aembedding()`, supporting both
local (sentence-transformers) and cloud (Vertex AI) models.

### Vector Index {#vector-index}

FalkorDB MUST maintain a vector index on memory embeddings for similarity
search.

### Background Processing {#embedding-background}

Embeddings MUST be generated asynchronously after memory creation or update.

## Context Assembly {#context-assembly}

Before each agent turn, a context block MUST be assembled from the character's
accessible memories and injected as a system message.

### Component Order {#context-order}

The context MUST include the following components, in this order:

1. **World facts** — Generally known facts about entities relevant to the
   scene.
2. **Common scene memory** — What everyone knows about this scene.
3. **Personal scene memory** — The character's private recollection.
4. **Character memories** — Impressions of other characters present in the
   scene.
5. **Recent chat history** — The most recent verbatim messages.

### Token Budgeting {#token-budget}

<a id="chat-history-budget"></a>
Token budgeting MUST split the context window between memory sections and chat
history. Chat history MUST be allocated 20% of the context window by default.
Sections with no content MUST be omitted.

## Memory File Format {#memory-file-format}

Memory files MUST follow this format:

```markdown
---
id: "mem_abc123"
memory_type: "scene"
visibility: "common"
owner_id: "char_1"
target_id: "scene_1"
gametime: 3600
created_at: 1706000000.0
updated_at: 1706000000.0
access_count: 0
last_accessed_at: null
---

Memory content text.
```

<a id="embedding-excluded-from-disk"></a>
The `embedding` field MUST be excluded from disk. Embeddings MUST be
regenerated on import.
