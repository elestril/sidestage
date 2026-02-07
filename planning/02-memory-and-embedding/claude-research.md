# Research: Memory and Embedding System

## Part 1: Codebase Analysis

### Project Overview

**Sidestage** is an AI Co-Author for Roleplaying Games, built to help Game Masters maintain consistency and depth in their campaign worlds. It's a multi-agent assistant with a FastAPI backend, WebSocket support for real-time sync, and recently implemented FalkorDB graph database integration.

### Directory Layout
```
src/sidestage/
├── graph/               # FalkorDB integration (split 01)
│   ├── client.py        # GraphConfig, GraphClient, connect(), close()
│   ├── schema.py        # Schema versioning, indexes, constraints
│   ├── entities.py      # Entity CRUD, label mappings, serialization
│   ├── relationships.py # Link/unlink, get_related, valid rel types
│   ├── queries.py       # High-level graph queries
│   ├── errors.py        # GraphError hierarchy
│   └── __init__.py      # Public API re-exports
├── schemas.py           # Pydantic entity models
├── agent.py             # LiteLLMAgent (multi-provider LLM)
├── character.py         # AgentActor, CharacterLogic
├── bus.py               # SceneMessageBus (async event dispatch)
├── scene.py             # SceneLogic (scene lifecycle + event persistence)
├── campaign.py          # Campaign (config, LLM, entity management)
├── tools.py             # WorldTools (agent-callable tools)
├── storage.py           # Storage (SQLite, legacy)
├── orchestrator.py      # SidestageOrchestrator (FastAPI server)
└── sync.py              # SyncManager (WebSocket broadcast)
```

### Key Dependencies
- **falkordb** (>=1.4.0): Graph database client
- **litellm** (>=1.81.6): Multi-LLM provider abstraction
- **fastapi** (>=0.128.0): Web framework
- **sqlalchemy** (>=2.0.46): Database ORM (legacy)
- **pydantic**: Entity models (BaseModel throughout)
- **pytest** + **pytest-anyio**: Testing framework (async support)
- **uv**: Package manager

### Entity System (schemas.py)

```python
class Entity(BaseModel):
    name: str; body: str; id: str

class Character(Entity):
    unseen: bool = False; location_id: Optional[str] = None; inventory: List[str] = []

class Location(Entity):
    connected_locations: List[str] = []

class Event(Entity):
    scene_id: str; gametime: int; walltime: str

class ChatMessage(Event):
    character_id: str; actor_id: Optional[str] = None; message: str

class JoinEvent(Event): actor_id: str
class LeaveEvent(Event): actor_id: str
class FastForwardEvent(Event): duration_str: str

class Scene(Entity):
    current_gametime: Optional[int] = None; location_id: Optional[str] = None
```

### Graph Module Patterns (split 01)

**Function signature convention**: All functions take `GraphClient` as first param.
```python
async def create_entity(client: GraphClient, entity: Entity) -> Entity
async def link(client, source_id, rel_type, target_id, properties=None)
async def get_related(client, entity_id, rel_type, direction="outgoing") -> list[Entity]
```

**Label hierarchy**: `Entity → Character`, `Entity → Event → ChatMessage`

**Valid relationship types** (whitelist):
```python
VALID_REL_TYPES = frozenset({
    "LOCATED_IN", "CONNECTS_TO", "AT_LOCATION",
    "HAS_EVENT", "INVOLVES", "PARTICIPATES_IN",
})
```

**Schema versioning**: Version 1 with indexes on (Entity.id, Entity.name, Event.gametime, Scene.current_gametime) and constraints (Entity.id unique+mandatory, Entity.name mandatory).

**Error hierarchy**: `GraphError → ConnectionError | EntityNotFoundError | DuplicateEntityError | SchemaError | QueryError`

### Actor/Agent System

**LiteLLMAgent** (`agent.py`):
- Multi-provider support via LiteLLM (OpenAI, Gemini, local llama.cpp)
- Auto-generates tool schemas from function signatures
- Tool execution loop (max 5 turns) with async tool support

**AgentActor** (`character.py`):
- Creates LiteLLMAgent per character
- Prompt template selection based on `character.unseen` flag
- Templates: `data/prompts/default_npc.txt` (visible NPCs), `data/prompts/unseen_npc.txt` (narrators)
- Current prompt: character description only, no memory enrichment

**Prompt templates** inject `{character.body}` into a system prompt wrapper.

### Event Flow

1. User sends chat → `SceneLogic.chat()` publishes to `SceneMessageBus`
2. Bus `_on_publish_hook` persists event (Storage + Graph dual-write)
3. Graph persistence: `create_entity(event)` → `link(scene, HAS_EVENT, event)` → `link(event, INVOLVES, character)`
4. Bus dispatches to all listeners (AgentActors) in parallel
5. Each AgentActor generates response → publishes reply to bus (recursive)

### Campaign Configuration

```yaml
llms:
  default:
    provider: llama_cpp
    base_url: http://localhost:8080/v1
    model: default
graph:
  host: localhost
  port: 6379
```

**LLMConfig** supports named configs (e.g., "default", "embed") — infrastructure for multiple LLM purposes already exists.

### Testing Patterns

- **Framework**: pytest + pytest-anyio for async
- **Mocking**: `unittest.mock.AsyncMock` and `MagicMock`
- **GraphClient mock pattern**:
```python
client = MagicMock()
client.graph = MagicMock()
client.graph.query = AsyncMock()
```
- **Node mock helper**: `_make_node_mock(labels, properties)` creates FalkorDB result mocks
- **Test markers**: `@pytest.mark.llm` for live LLM tests (skipped if localhost:8080 unavailable)
- **Test command**: `uv run pytest`
- **Coverage areas**: Entity CRUD, relationships, queries, schema, error conditions, integration routing

### Key Findings for Memory Implementation

1. **No existing vector/embedding code** — clean slate
2. **Graph module is clean and extensible** — well-isolated with public API
3. **Dual persistence pattern** exists (graph_client None → Storage fallback)
4. **Named LLM configs** already support "embed" config naming
5. **All graph operations are async** — consistent async patterns
6. **Prompt templates** currently have no memory section — needs extension
7. **SceneLogic._on_publish_hook** is the natural event interception point for memory creation

---

## Part 2: Web Research

### FalkorDB Vector Search Capabilities

**Vector index creation:**
```cypher
CREATE VECTOR INDEX FOR (n:Memory) ON n.embedding
OPTIONS {dimension: 384, similarityFunction: 'cosine'}
```

**Required parameters:**
- `dimension`: Must match embedding model output (384 for MiniLM)
- `similarityFunction`: `euclidean` or `cosine`

**Optional HNSW tuning:**
- `M` (default 16): Max connections per node, 16-32 for balanced recall
- `efConstruction` (default 200): Build-time quality, 100-400 range
- `efRuntime` (default 10): Query-time candidates, adjustable per query

**Vector queries:**
```cypher
CALL db.idx.vector.queryNodes('Memory', 'embedding', 10, vecf32($query_vector))
YIELD node, score
```

**Vector creation:**
```cypher
CREATE (m:Memory {content: $content, embedding: vecf32($embedding)})
```

**Performance notes:**
- 1M vectors at 384-dim ≈ 1.5 GB memory
- Formula: `vectors × dimensions × 4 bytes + ~20% overhead`
- Cosine similarity recommended for normalized text embeddings
- Cannot combine vector search with property filters in same query (requires post-filtering)

### Sentence-Transformers: all-MiniLM-L6-v2

**Model specs:**
- 384 dimensions, 22.7M params (22MB)
- 256 word piece input limit
- Apache 2.0 license
- Trained on 1.17B sentence pairs

**Usage:**
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
embeddings = model.encode(["text1", "text2"])  # Returns numpy arrays
```

**Async pattern** — sentence-transformers is synchronous, wrap with:
```python
embedding = await asyncio.to_thread(model.encode, text)
```

**Batch processing:**
```python
embeddings = model.encode(sentences, batch_size=32)  # CPU: 16-32, GPU: 32-128
```

**Comparison with alternatives:**

| Model | Dims | Params | Speed | STS-B Score |
|-------|------|--------|-------|-------------|
| all-MiniLM-L6-v2 | 384 | 22M | 5x faster | 84-85% |
| all-mpnet-base-v2 | 768 | 110M | Baseline | 87-88% |

**Recommendation:** Start with all-MiniLM-L6-v2 (384-dim) — excellent speed/quality tradeoff, small footprint, local-only.

### AI Agent Memory Retrieval Patterns

**Memory types for agents:**
1. **Episodic**: Specific past events tied to time (chat messages, scene events)
2. **Semantic**: Extracted factual knowledge ("Character X has trait Y")
3. **Procedural**: Learned behaviors/skills (less relevant for our use case)

**Composite relevance scoring:**
```
activation = α × semantic_similarity + β × recency + γ × frequency + δ × importance
```

Recommended weights: α=0.5, β=0.3, γ=0.15, δ=0.05

**Time-decay (exponential):**
```python
recency_score = math.exp(-decay_rate * hours_elapsed)  # decay_rate ≈ 0.995
```

**Context window management:**
- Budget tokens dynamically per section (system prompt, memories, history)
- Summarize old memories rather than including verbatim
- Use hierarchical retrieval: summaries first, drill down if needed
- Typical budget: 500-2000 tokens for memory context in agent prompts

**Memory consolidation:**
- Periodic: End of session, daily, or when episodic memory exceeds threshold
- Process: Aggregate similar memories → Summarize into semantic facts → Reconcile conflicts
- Keep source provenance (link consolidated memories to originals)

**Key pattern from MemGPT:** LLMs managing their own memory via function calls:
- `archival_memory_insert(content)` — store long-term
- `archival_memory_search(query)` — semantic retrieval

### Sources

- [FalkorDB Vector Index Docs](https://docs.falkordb.com/cypher/indexing/vector-index)
- [FalkorDB 4.0 Vector Search Blog](https://www.falkordb.com/blog/released-falkordb-4-0-a1-vector-search-index-bolt-protocol/)
- [sentence-transformers/all-MiniLM-L6-v2 on HuggingFace](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [IBM: What Is AI Agent Memory?](https://www.ibm.com/think/topics/ai-agent-memory)
- [Graphlit: Survey of AI Agent Memory Frameworks](https://www.graphlit.com/blog/survey-of-ai-agent-memory-frameworks)
- [MemGPT Research](https://research.memgpt.ai/)
