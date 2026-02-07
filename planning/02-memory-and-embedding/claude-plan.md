# Implementation Plan: Memory and Embedding System

## 1. Background and Goals

Sidestage is an AI Co-Author for tabletop RPGs. It uses FalkorDB as a graph database (split 01, complete), LiteLLM for multi-provider LLM abstraction, and an async actor system where NPC characters respond to scene events via a message bus. Currently, NPC agents only receive their static character description as context — they have no memory of past events or interactions.

This plan adds a **memory system** where:
1. Memories are **living text documents** stored as graph nodes, updated explicitly via LLM tool calls
2. A **visibility model** (`"common"` or `"private"`) controls which memories each character can access — designed for future expansion to rich ACLs
3. Scene memories exist in **layers**: common knowledge (what everyone heard), canonical truth (DM-only), and personal recollections (per-character)
4. **World facts** can be generally known or private to specific characters
5. During a scene, each character's context is assembled from: character description + applicable memories + recent verbatim chat history
6. Memories are embedded for future cross-memory vector search
7. A campaign health system monitors embedding availability and degrades gracefully

The system builds on the existing graph module, LLM configuration, agent tool system, and event bus.

---

## 2. Architecture Overview

### New Modules

```
src/sidestage/
├── memory/                   # New package
│   ├── __init__.py           # Public API re-exports
│   ├── embeddings.py         # Embedding generation via LiteLLM
│   ├── models.py             # Memory Pydantic models
│   ├── store.py              # Memory CRUD + vector search + relationship Cypher
│   ├── context.py            # Context assembly for agent prompts
│   └── tools.py              # Memory update tools for agent tool calls
├── health.py                 # New: Campaign health status system
```

### Modified Modules

- **`graph/schema.py`**: Add migration v2 with vector index and Memory range indexes
- **`graph/client.py`**: Add `vector_dimension` to `GraphConfig`
- **`campaign.py`**: Add `LLMConfig` fields for context budget, embed config validation, health status, memory system lifecycle
- **`agent.py`**: Add `context` parameter to `LiteLLMAgent.arun()`
- **`character.py`**: Modify `AgentActor` to assemble memory context in `on_event()`, add memory tools to agent
- **`scene.py`**: Pass memory dependencies to CharacterLogic during scene activation

**NOT modified:** `graph/relationships.py`, `graph/entities.py`, `schemas.py`

### Data Flow

```
Character LLM responding to a chat message:
  1. AgentActor.on_event() receives ChatMessage
  2. memory.context.assemble_context() builds context:
     - Fetches common memories for this scene (visibility == "common")
     - Fetches character's private scene memory (visibility == "private", owner == self)
     - Fetches character memories about present characters
     - Fetches generally known world facts (visibility == "common")
     - Gets recent chat history (% of context window)
  3. Context passed to LiteLLMAgent.arun() as system context
  4. LLM generates response, MAY include tool calls:
     - update_scene_memory(content) → upserts private scene memory
     - update_character_memory(about_character_id, content) → upserts character memory
  5. Tool calls persist to FalkorDB + generate embeddings asynchronously

DM / Co-Author managing world state:
  - update_common_memory(scene_id, content) → upserts common scene memory
  - update_canonical_memory(scene_id, content) → upserts canonical (DM-private) scene memory
  - add_world_fact(content, about_entity_id, visibility) → creates/updates a world fact
```

---

## 3. Memory Models

### Memory as a Separate Graph Type

Memory nodes use the `:Memory` label (not `:Entity`). They are separate from the Entity hierarchy because existing Entity operations are hardcoded to match on `:Entity` labels with constraints (unique id, mandatory name) that don't fit memories.

All Memory Cypher lives in `memory/store.py`. The existing `graph/relationships.py` and `graph/entities.py` are untouched.

### Memory Schema

```python
class MemoryType(str, Enum):
    SCENE = "scene"           # Memory of a scene (common, canonical, or personal)
    CHARACTER = "character"   # Memory about another character
    WORLD_FACT = "world_fact" # Fact about the world or an entity

class Memory(BaseModel):
    id: str                         # UUID
    content: str                    # Human-readable text (the "living document")
    memory_type: MemoryType         # Discriminator
    visibility: str                 # "common" or "private" — extensible to rich ACLs later
    embedding: list[float] | None   # Vector, None if pending or failed
    owner_id: str | None            # Character/actor ID who owns this. None for common memories.
    target_id: str                  # Scene ID, Character ID, or Entity ID (what this memory is ABOUT)
    created_at: float               # Unix timestamp of creation
    updated_at: float               # Unix timestamp of last update
    gametime: int | None            # Game time when last updated
    access_count: int               # Incremented on retrieval (for future cleanup)
    last_accessed_at: float | None  # Timestamp of last retrieval
```

### Visibility Model

The `visibility` field is a plain `str` — simple today, extensible later:

| Value | Meaning | Who can read |
|---|---|---|
| `"common"` | Generally available | Any character in context assembly |
| `"private"` | Owner-only | Only the character/actor whose `owner_id` matches |

**Future extensibility:** The field can later hold richer values — role identifiers, JSON-encoded ACL lists, entity ID references — without schema migration. The context assembly query just needs to evolve its filter logic.

### Memory Instances by Use Case

| Use Case | memory_type | visibility | owner_id | target_id (ABOUT) |
|---|---|---|---|---|
| Common scene memory ("the bar fight everyone heard of") | `scene` | `"common"` | `None` | Scene ID |
| Canonical scene memory (DM truth) | `scene` | `"private"` | DM actor ID | Scene ID |
| Character's personal scene memory | `scene` | `"private"` | Character ID | Scene ID |
| Character memory about another character | `character` | `"private"` | Character ID | Other Character ID |
| Generally known world fact | `world_fact` | `"common"` | `None` | Entity ID |
| Secret world fact known to specific character | `world_fact` | `"private"` | Character ID | Entity ID |

### Graph Structure

```
# Private scene memory (character owns it)
(Character)-[:HAS_MEMORY]->(Memory:SceneMemory {visibility: "private"})-[:ABOUT]->(Scene)

# Common scene memory (no owner)
(Memory:SceneMemory {visibility: "common"})-[:ABOUT]->(Scene)

# Canonical scene memory (DM owns it)
(DM Actor)-[:HAS_MEMORY]->(Memory:SceneMemory {visibility: "private"})-[:ABOUT]->(Scene)

# Character memory
(Character)-[:HAS_MEMORY]->(Memory:CharacterMemory {visibility: "private"})-[:ABOUT]->(OtherCharacter)

# World facts
(Memory:WorldFact {visibility: "common"})-[:ABOUT]->(Entity)
(Character)-[:HAS_MEMORY]->(Memory:WorldFact {visibility: "private"})-[:ABOUT]->(Entity)
```

### Graph Labels

- `Memory:SceneMemory` — memory of a scene
- `Memory:CharacterMemory` — memory about a character
- `Memory:WorldFact` — fact about the world/entity

### Relationship Types (managed by memory/store.py)

| Relationship | Meaning | Example |
|---|---|---|
| `HAS_MEMORY` | Actor owns this memory | Character -[HAS_MEMORY]-> Memory |
| `ABOUT` | What the memory is about | Memory -[ABOUT]-> Scene, Character, or Entity |

### Upsert Semantics

Each (owner_id, memory_type, target_id) tuple is unique. The upsert functions enforce this:
- If a matching memory exists → update `content`, `updated_at`, `gametime`, re-embed
- If not → create new Memory node + relationships

For common memories (owner_id is None), the uniqueness key is (memory_type, visibility, target_id).

---

## 4. Embedding Generation

### Architecture

Embeddings are generated via LiteLLM's `aembedding()` function, using the campaign's `embed` LLM configuration. This is consistent with how chat models are configured — same `LLMConfig` structure, same provider abstraction.

Embedding generation is **asynchronous and non-blocking**. When a memory is created or updated via tool call, the text is persisted immediately. Embedding generation is then fired off as a background task. If it fails, the memory remains usable for graph-based retrieval — only vector search is affected.

### LLMConfig Extension

Add optional fields to `LLMConfig`:

```python
class LLMConfig(BaseModel):
    provider: str = "llama_cpp"
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "sk-no-key-required"
    model: str = "default"
    context_limit: int | None = None        # Max context tokens (validated at startup via /status)
    memory_token_budget: int | None = None   # Tokens allocated for memory context (optional override)
```

### GraphConfig Extension

```python
@dataclass
class GraphConfig:
    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    max_connections: int = 16
    graph_name: str | None = None
    vector_dimension: int | None = None     # Set at startup from test embedding call
```

### Embed Config Validation

At campaign startup (in `start_graph()` after graph connection), if an `embed` LLM config exists:

1. Build the LiteLLM model string from provider + model (same pattern as `create_agent`)
2. For local providers: hit the `/v1/models` endpoint to verify the embedding model is available
3. For cloud providers: skip validation (same pattern as existing Gemini handling)
4. **Make a test embedding call** with a short probe text to determine the actual vector dimension
5. Store the dimension in `GraphConfig.vector_dimension`
6. Pass it to `initialize_schema()` so the v2 migration creates the vector index with correct dimensions

If embed validation fails: log warning, set health to DEGRADED, campaign starts without embedding (memories still work via graph retrieval).

### Embedding Functions

```python
class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

async def embed_text(config: LLMConfig, text: str) -> list[float]:
    """Generate embedding for a single text using LiteLLM aembedding().

    Builds model string from config, calls litellm.aembedding(),
    returns the embedding vector.

    Raises EmbeddingError on failure.
    """

async def embed_and_update(
    client: GraphClient,
    config: LLMConfig,
    memory_id: str,
    text: str,
    health: CampaignHealth,
) -> None:
    """Generate embedding and update the memory node. Fire-and-forget.

    On success: updates memory node's embedding field. If health was DEGRADED, transitions to HEALTHY.
    On failure: logs warning, transitions health to DEGRADED. Memory remains without embedding.
    """
```

---

## 5. Schema Migration (v2)

### `initialize_schema()` Extension

Add an optional `vector_dimension` parameter:

```python
async def initialize_schema(client: GraphClient, vector_dimension: int | None = None) -> None:
```

### v2 Migration

1. **Vector index** on `Memory.embedding` (only if `vector_dimension` is provided):
   ```cypher
   CREATE VECTOR INDEX FOR (n:Memory) ON n.embedding
   OPTIONS {dimension: $dim, similarityFunction: 'cosine'}
   ```

2. **Range indexes** on `Memory.owner_id`, `Memory.target_id`, `Memory.memory_type`, `Memory.visibility` for fast lookups.

3. **Stores dimension** as a property on the SchemaVersion node.

### Version Bump

`CURRENT_VERSION` becomes 2. The v2 migration runs automatically on connect (existing pattern). If the embed config doesn't exist, the vector index is skipped.

### Caller Changes

`Campaign.start_graph()` calls `connect()` as today, then:
1. If `embed` config exists, makes a test embedding call to get dimension
2. Sets `config.graph.vector_dimension`
3. Schema migration picks up the dimension for vector index creation

---

## 6. Memory Store (CRUD + Search)

### Own Cypher, Not Entity Functions

`memory/store.py` contains all Cypher for Memory operations. It does NOT use `graph/entities.py` or `graph/relationships.py`. Memory nodes use `:Memory` labels, not `:Entity`.

The store validates its own relationship types via an internal constant:
```python
MEMORY_REL_TYPES = frozenset({"HAS_MEMORY", "ABOUT"})
```

### Core Upsert Operations

```python
async def upsert_memory(
    client: GraphClient,
    memory_type: MemoryType,
    visibility: str,
    owner_id: str | None,
    target_id: str,
    content: str,
    gametime: int | None = None,
) -> Memory:
    """Create or update a memory.

    Uniqueness key: (owner_id, memory_type, target_id) for private memories,
    or (memory_type, visibility, target_id) for common memories (owner_id is None).

    MERGE pattern in Cypher. Creates HAS_MEMORY and ABOUT relationships
    if this is a new memory.
    Returns the Memory object.
    """
```

This single function handles all memory types. Convenience wrappers call it:

```python
async def upsert_scene_memory(client, owner_id, scene_id, content, gametime=None) -> Memory:
    """Upsert a character's private scene memory."""

async def upsert_common_scene_memory(client, scene_id, content, gametime=None) -> Memory:
    """Upsert the common scene memory (visibility=common, no owner)."""

async def upsert_character_memory(client, owner_id, about_character_id, content, gametime=None) -> Memory:
    """Upsert a character's memory about another character."""

async def upsert_world_fact(client, about_entity_id, content, visibility="common", owner_id=None) -> Memory:
    """Upsert a world fact. Common by default, or private to a specific character."""
```

### Read Operations

```python
async def get_scene_memory(client, owner_id, scene_id) -> Memory | None:
    """Get a character's private scene memory."""

async def get_common_scene_memory(client, scene_id) -> Memory | None:
    """Get the common scene memory."""

async def get_character_memory(client, owner_id, about_character_id) -> Memory | None:
    """Get a character's memory about another character."""

async def get_memories_for_context(
    client: GraphClient,
    character_id: str,
    scene_id: str,
    present_character_ids: list[str],
) -> ContextMemories:
    """Fetch all memories needed for a character's context assembly.

    Returns a ContextMemories object containing:
    - common_scene_memory: The common scene memory (if any)
    - private_scene_memory: This character's private scene memory (if any)
    - character_memories: dict of character_id → Memory for present characters
    - world_facts: list of common world facts relevant to entities in the scene

    Single function to minimize round-trips. Uses a batch Cypher query
    or parallel queries internally.
    """

async def get_all_memories(client, owner_id, memory_type=None) -> list[Memory]:
    """Get all memories owned by a character, optionally filtered by type."""

async def delete_memory(client, memory_id) -> None:
    """Delete a memory and its relationships."""

async def touch_memory(client, memory_id) -> None:
    """Increment access_count and update last_accessed_at.

    Called during context assembly. Separate from get to avoid
    inflating counts during debugging/admin.
    """
```

### Vector Search (for future cross-memory queries)

```python
async def search_similar(
    client: GraphClient,
    query_embedding: list[float],
    owner_id: str | None = None,
    visibility: str | None = None,
    limit: int = 10,
) -> list[tuple[Memory, float]]:
    """Find memories similar to query embedding.

    Uses FalkorDB vector index. Post-filters by owner_id and/or visibility.
    Returns (memory, similarity_score) pairs ordered by score descending.
    """
```

Note: The primary retrieval path is graph-based (`get_memories_for_context`). Vector search is available for future cross-memory queries but is not used in the core context assembly flow.

---

## 7. Memory Tools (Agent-Callable)

### NPC Character Tools

Given to each character's LLM agent. The LLM decides when something noteworthy happens and explicitly calls these tools.

```python
class MemoryTools:
    """Memory update tools for character agents.

    Each instance is bound to a specific character (owner_id) and scene.
    All memories created are private (visibility="private").
    """

    def __init__(
        self,
        client: GraphClient,
        embed_config: LLMConfig | None,
        health: CampaignHealth,
        owner_id: str,
        scene_id: str,
    ): ...

    async def update_scene_memory(self, content: str) -> str:
        """Update your memory of the current scene.

        Call this when something noteworthy happens that you want to remember
        about this scene. Your scene memory is a living document — include
        everything important, as this replaces your previous scene memory.

        Args:
            content: Your updated memory of this scene. Include key events,
                     decisions, and anything you want to remember.

        Returns:
            JSON confirmation with memory ID.
        """

    async def update_character_memory(self, about_character_id: str, content: str) -> str:
        """Update your memory about another character.

        Call this when you learn something new about a character or want to
        update your impression of them. This replaces your previous memory
        about this character.

        Args:
            about_character_id: The ID of the character this memory is about.
            content: Your updated memory about this character. Include what you
                     know about them, your relationship, and impressions.

        Returns:
            JSON confirmation with memory ID.
        """
```

### DM / Co-Author Tools

Added to the existing `WorldTools` class (or a new `DmMemoryTools` class) for the Co-Author agent. These manage the "world state" layer of memories.

```python
async def update_common_memory(self, scene_id: str, content: str) -> str:
    """Update the common scene memory — what everyone generally knows about this scene.

    Args:
        scene_id: The scene this memory is about.
        content: The generally known version of events.
    """

async def update_canonical_memory(self, scene_id: str, content: str) -> str:
    """Update the canonical (DM truth) scene memory.

    This is the ground truth of what actually happened. Only visible to the DM.

    Args:
        scene_id: The scene this memory is about.
        content: The true, complete account of what happened.
    """

async def add_world_fact(self, about_entity_id: str, content: str, visibility: str = "common") -> str:
    """Add or update a world fact.

    Args:
        about_entity_id: The entity this fact is about (character, location, etc.)
        content: The fact content.
        visibility: "common" for generally known, "private" for restricted.
    """
```

### Tool Call Flow

Each tool call:
1. Calls the corresponding `upsert_*` function in `memory/store.py`
2. Fires off `embed_and_update()` as a background `asyncio.Task` (non-blocking)
3. Returns JSON confirmation to the LLM

---

## 8. Context Assembly

### Purpose

Build the system context for a character agent before each LLM call. The context provides the NPC with everything it "knows" for the current interaction.

### Context Components

The character's LLM context during a scene consists of (in order):

1. **Character description** (existing: from prompt template + `{character.body}`)
2. **World facts** — generally known facts (visibility=common) about entities relevant to the scene
3. **Common scene memory** — what everyone knows about this scene (visibility=common)
4. **Personal scene memory** — this character's private scene memory (visibility=private, owner=self)
5. **Character memories** — this character's private memories about other characters present in the scene
6. **Recent chat history** — the most recent N words of verbatim chat, where N is a function of the configured context window

### Visibility Filter Rule

The context assembly query fetches memories where:
```
visibility == "common" OR owner_id == this_character_id
```

This single rule handles all current cases and will naturally extend when richer ACLs are added.

### Context Window Budget

The chat history window is calculated as a percentage of the LLM's context limit:

```
chat_history_words = context_limit_tokens × chat_history_ratio / avg_tokens_per_word
```

- `context_limit` comes from the `default` LLM config (validated at startup via `/status` endpoint or config)
- `chat_history_ratio` is 0.20 (20% of context window) by default
- `avg_tokens_per_word` ≈ 1.3 (reasonable approximation for English text)
- `memory_token_budget` in LLMConfig can override the automatic calculation

### Assembly Function

```python
async def assemble_context(
    client: GraphClient,
    owner_id: str,
    scene_id: str,
    present_character_ids: list[str],
    recent_messages: list[ChatMessage],
    context_limit: int,
    chat_history_ratio: float = 0.20,
) -> ContextResult:
    """Assemble memory context for an agent prompt.

    1. Call get_memories_for_context() to fetch all applicable memories
    2. Format memories into sections
    3. Trim chat history to budget
    4. Return combined context

    Returns:
        ContextResult with memory_text, chat_text, token_estimate
    """
```

### ContextResult

```python
class ContextResult(BaseModel):
    memory_text: str     # World facts + scene memories + character memories
    chat_text: str       # Recent verbatim chat history, trimmed to budget
    token_estimate: int  # Rough token estimate of total context
```

### Output Format

```
## World Knowledge
- [Fact about entity relevant to this scene]
- [Another generally known fact]

## Scene Memory (General)
[Common scene memory content — what everyone knows]

## My Scene Memory
[Character's private scene memory, or omitted if none]

## People I Know
### [Character Name]
[Memory about this character]

### [Character Name]
[Memory about this character]

## Recent Events
[Verbatim recent chat messages, trimmed to budget]
[Character A]: message text
[Character B]: message text
```

Sections with no content are omitted.

### Integration with AgentActor

Add a `context` parameter to `LiteLLMAgent.arun()`:

```python
async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse:
    """Run agent with message. Optional context inserted as system message."""
```

When `context` is provided, it is inserted as a system message between the main system prompt (character description) and the user message. This keeps memory context clearly separated from user input.

In `AgentActor.on_event()`:
1. Call `assemble_context()` with current scene state
2. Pass result as `context` to `self.agent.arun(event.message, context=...)`
3. If `assemble_context()` fails, call `arun()` without context (graceful degradation)

---

## 9. Campaign Health Status

### Health Enum

```python
class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"     # Non-critical issues (e.g., embedding service down)
    UNHEALTHY = "unhealthy"   # Critical failure (e.g., graph database down)
```

### CampaignHealth

```python
class CampaignHealth:
    """Manages campaign health status with transition logic."""

    def __init__(self, on_change: Callable[[HealthStatus, str], Awaitable[None]] | None = None): ...

    async def set_status(self, status: HealthStatus, reason: str) -> None:
        """Transition to new status. Fires on_change callback if status changed."""

    @property
    def is_accepting_chat(self) -> bool:
        """True if HEALTHY or DEGRADED. Only UNHEALTHY blocks chat."""

    @property
    def is_embedding_available(self) -> bool:
        """True only if HEALTHY. When DEGRADED, embedding is skipped."""
```

### Health State Transitions

| From | To | Trigger |
|---|---|---|
| HEALTHY | DEGRADED | Embedding failure, embed config missing |
| DEGRADED | HEALTHY | Embedding succeeds after prior failure |
| HEALTHY/DEGRADED | UNHEALTHY | Graph database connection lost |
| UNHEALTHY | HEALTHY | Graph database reconnected |

Embedding failure → DEGRADED (chat works, memories persist without vectors). Graph failure → UNHEALTHY (nothing works).

### Integration

- `Campaign.__init__` creates `CampaignHealth` instance
- `Campaign.start_graph()` wires `on_change` to WebSocket broadcast
- `SceneLogic.chat()` checks `health.is_accepting_chat`
- `embed_and_update()` checks `health.is_embedding_available` and transitions on failure/recovery

### WebSocket Notification

```json
{"type": "campaign_health", "status": "degraded", "reason": "Embedding service unavailable"}
```

---

## 10. Scene Integration

### SceneLogic Modifications

When a scene activates:

1. If graph_client exists, pass it to `CharacterLogic` during activation
2. `CharacterLogic.activate()` creates `MemoryTools` bound to the character + scene
3. Memory tools are added to the agent's tool list alongside existing WorldTools
4. On deactivation: no special cleanup needed (memories are already persisted)

### CharacterLogic / AgentActor Changes

`AgentActor.__init__` receives new dependencies:
- `graph_client: GraphClient | None` — for memory store operations
- `embed_config: LLMConfig | None` — for embedding generation
- `health: CampaignHealth` — for health status
- `scene_id: str` — current scene ID
- `present_character_ids: list[str]` — characters in the scene (for context assembly)
- `context_limit: int` — from default LLM config

`AgentActor.on_event()` modification:
1. Before calling `self.agent.arun()`, assemble context via `memory.context.assemble_context()`
2. Pass assembled context as `context` parameter to `arun()`
3. LLM response may include memory tool calls, which are executed via existing tool loop

### Recent Chat History

`AgentActor` needs access to recent scene messages for context assembly. `SceneLogic` passes its messages list reference to `AgentActor`, which reads the last N entries during context assembly.

---

## 11. Configuration

### Campaign Config Example

```yaml
llms:
  default:
    provider: llama_cpp
    base_url: http://localhost:8080/v1
    model: default
    context_limit: 16384
  embed:
    provider: llama_cpp
    base_url: http://localhost:8080/v1
    model: embed
    api_key: sk-no-key-required

graph:
  host: localhost
  port: 6379
```

### Context Limit Validation

At startup, for local providers with `context_limit` configured:
- Query the endpoint's `/status` or `/v1/models` to verify the context limit is supported
- If not configured, attempt to detect from the endpoint
- Fall back to a conservative default (e.g., 4096) if detection fails

The chat history budget is derived automatically: `context_limit × 0.20`.

---

## 12. Error Handling Strategy

### Embedding Failures

1. `embed_text()` raises `EmbeddingError` on failure
2. `embed_and_update()` catches it, transitions health to DEGRADED, logs warning
3. Memory persists without embedding — still accessible via graph traversal
4. When embedding succeeds after failure, transitions back to HEALTHY
5. Memories with `embedding=None` are not vector-searchable but are fully functional for primary retrieval

### Graph Failures

Follow existing patterns from split 01: wrap in `QueryError`, log, propagate. Memory tool call failures return error messages to the LLM (existing tool error pattern in `LiteLLMAgent`).

### Graceful Degradation

- No `embed` config → memories persist without embeddings, no vector search
- No `graph_client` → memory system doesn't activate, agents use static prompts (current behavior)
- Embedding failure → DEGRADED, memories persist without vectors, chat continues

---

## 13. File-by-File Summary

| File | Action | What Changes |
|---|---|---|
| `src/sidestage/memory/__init__.py` | **New** | Public API exports |
| `src/sidestage/memory/models.py` | **New** | Memory, MemoryType, ContextResult, ContextMemories |
| `src/sidestage/memory/embeddings.py` | **New** | embed_text(), embed_and_update() via LiteLLM |
| `src/sidestage/memory/store.py` | **New** | upsert_*, get_*, get_memories_for_context, search_similar, touch, delete |
| `src/sidestage/memory/context.py` | **New** | assemble_context() — visibility-filtered retrieval + chat history trimming |
| `src/sidestage/memory/tools.py` | **New** | MemoryTools (NPC tools), DM memory tools |
| `src/sidestage/health.py` | **New** | HealthStatus, CampaignHealth |
| `src/sidestage/graph/schema.py` | **Modify** | v2 migration (vector index, Memory range indexes incl. visibility), accept vector_dimension |
| `src/sidestage/graph/client.py` | **Modify** | Add vector_dimension to GraphConfig |
| `src/sidestage/campaign.py` | **Modify** | LLMConfig fields, embed validation, health, context_limit validation, DM memory tools |
| `src/sidestage/agent.py` | **Modify** | Add context parameter to arun() |
| `src/sidestage/character.py` | **Modify** | AgentActor gets memory deps, assembles context in on_event(), memory tools in tool list |
| `src/sidestage/scene.py` | **Modify** | Pass graph_client/embed_config/health to CharacterLogic during activation |

**NOT modified:** `graph/relationships.py`, `graph/entities.py`, `schemas.py`

---

## 14. Dependencies

### New Python Dependencies

- **`litellm`** (already present): Used for `aembedding()` — no new dependency needed
- No `sentence-transformers` dependency — all embedding goes through LiteLLM

### FalkorDB Version

FalkorDB 4.0+ server is required for vector index support. The implementer should verify:
- The FalkorDB server version supports `CREATE VECTOR INDEX` and `db.idx.vector.queryNodes`
- The `falkordb` Python client supports `vecf32()` vector serialization
- Whether parameterized vectors work in the target version
