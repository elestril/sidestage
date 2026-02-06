# Spec: Memory and Embedding System

## Overview
Implement vector-based memory retrieval for Sidestage agents using embeddings. This split extends the FalkorDB foundation (split 01) with memory nodes, embedding generation, and similarity search capabilities to enable context-aware agent prompts.

## Context & Requirements

### From Project Requirements (planning/requirements.md)
- **Section 2.3:** FalkorDB for entities, relationships, and **memories**
- **Section 3.2:** Context-aware chat with tool-based access to world knowledge
- **Section 3.2:** Multi-agent interaction with NPCs reacting to events
- **Section 3.2:** Dynamic prompts generated from character descriptions
- Track 6 goal: "Transitioning primary storage to FalkorDB for relationship traversal and **vector-based memory retrieval**"

### Existing Architecture Context
- Chat history stored in SQLite (session memory)
- Events stored as Event entities: ChatMessage, JoinEvent, LeaveEvent
- Actor system uses character descriptions and templates for prompts
- Agents need scene-specific context + knowledge of world state
- Both local (llama.cpp) and cloud (Google Gemini) LLM backends supported
- Python 3.12+ async patterns throughout codebase

### Design Principles
- **Builds on split 01:** Assumes FalkorDB foundation is stable and functional
- **Agent-focused:** Designed to improve prompt quality by providing relevant context
- **Embedding agnostic:** Support multiple embedding models (local vs cloud)
- **Memory lifecycle:** Memories should have creation time, relevance scoring, optional expiration
- **Context assembly:** Retrieve and rank memories for inclusion in agent prompts

## Key Decisions to Explore in Deep-Plan

### 1. Embedding Model Strategy
- **Question:** Which embedding model(s) should we use?
  - Local option: Sentence-transformers (e.g., all-MiniLM-L6-v2) - no API calls, lightweight
  - Cloud option: Google Vertex AI embeddings - coordinated with Gemini LLM usage
  - Hybrid: Use local for campaign-specific memories, cloud for broader reasoning?
- **Question:** Vector dimensionality (384-1536 dims)?
- **Impact:** Cost (cloud vs local compute), latency, memory footprint, semantic quality
- **Design considerations:**
  - Must work with both local and cloud LLM backends
  - Campaign data is private (local storage preferred for PII-heavy character info)
  - Embedding consistency across sessions important

### 2. Memory Node Types & Properties
- **Question:** What types of memories should we store?
  - Event memories (historical occurrences from chat/events)?
  - Fact memories (extracted knowledge: "Character X has trait Y")?
  - Relationship memories (connections between entities)?
  - Interaction memories (conversations between characters)?
- **Question:** What properties on memory nodes?
  - Content (text), embedding vector, timestamp, relevance_score
  - Source entity (which character/scene does this pertain to)?
  - Memory type, tags, expiration_time?
- **Impact:** Query flexibility, memory management, storage efficiency

### 3. Memory Creation & Indexing Strategy
- **Question:** When/how are memories created?
  - Real-time: Every event/chat message becomes a memory?
  - Batch: Summarize events at scene boundaries?
  - Agent-initiated: Let agents extract important facts?
- **Question:** How do we index for vector search?
  - Full vector index on all memories (slower writes, fast searches)?
  - Incremental indexing with background jobs?
  - Partitioned by entity (memories per character/location)?
- **Impact:** Write performance, search latency, storage requirements

### 4. Similarity Search & Context Retrieval
- **Question:** How do we retrieve relevant memories for an agent prompt?
  - Query strategy: Search by entity context? By scene? By keywords?
  - Ranking: Pure similarity score? Decay by age? Boost by relevance?
  - Context window: Max tokens to include in prompt?
- **Question:** How do we avoid irrelevant or contradictory memories?
  - Manual memory curation/deletion?
  - Automatic expiration based on recency?
  - Conflict resolution when memories conflict?
- **Impact:** Prompt quality, agent coherence, token efficiency

### 5. Integration with Actor System Prompts
- **Question:** How does memory retrieval integrate with existing prompt generation?
  - Current system: Character descriptions + templates (default_npc.txt, unseen_npc.txt)
  - New system: Add "recent events" and "relevant relationships" sections?
- **Question:** How do we prevent prompt bloat?
  - Prioritize memories by relevance score
  - Limit total context to token budget
  - Summarization strategy for long memory lists
- **Impact:** Agent behavior, consistency, prompt token usage

### 6. Memory Lifecycle & Cleanup
- **Question:** How long should memories persist?
  - Indefinite (never delete)?
  - Time-based expiration (e.g., memories older than campaign end)?
  - Activity-based (delete if not accessed after N searches)?
- **Question:** Memory consolidation/summarization?
  - Keep raw event memories or summarize into higher-level facts?
  - Archive old memories separately?
- **Impact:** Storage requirements, query performance, long-term campaign coherence

## Scope & Deliverables

### In Scope
- Memory node type definition and creation in FalkorDB (building on split 01)
- Embedding model integration (local and/or cloud)
- Vector indexing for similarity search
- Query API for memory retrieval by similarity and filters
- Memory ranking/scoring for context assembly
- Integration with Actor system for prompt enrichment
- Memory lifecycle management (creation, expiration, cleanup)
- Unit tests for embedding and search operations

### Out of Scope
- Memory migration from SQLite chat logs (deferred to split 03)
- Real-time memory synchronization between clients (deferred to split 03)
- Advanced memory consolidation or summarization algorithms
- Memory visualization/exploration UI
- Performance tuning beyond basic indexing
- Persistent embedding cache (compute on-demand initially)

## API Surface (Preliminary)

### Embedding Operations
```python
async def init_embedding_model(model_name: str) -> EmbeddingModel
async def embed_text(model: EmbeddingModel, text: str) -> list[float]
async def embed_batch(model: EmbeddingModel, texts: list[str]) -> list[list[float]]
```

### Memory CRUD
```python
async def create_memory(client, content: str, embedding: list[float],
                       source_entity_id: str, memory_type: str) -> Memory
async def get_memory(client, memory_id: str) -> Memory | None
async def update_memory(client, memory_id: str, updates: dict) -> Memory
async def delete_memory(client, memory_id: str) -> None
```

### Memory Search
```python
async def search_memories(client, embedding: list[float], limit: int = 10,
                         filters: dict | None = None) -> list[tuple[Memory, float]]  # (memory, similarity_score)
async def search_by_entity(client, entity_id: str, limit: int = 10) -> list[Memory]
async def search_by_type(client, memory_type: str, limit: int = 10) -> list[Memory]
```

### Context Assembly
```python
async def assemble_context(client, agent_entity_id: str, scene_id: str,
                          token_budget: int = 2000) -> str
    # Returns formatted text of relevant memories for agent prompt
```

### Memory Lifecycle
```python
async def expire_old_memories(client, before_timestamp: float) -> int  # returns count deleted
async def score_memory_relevance(memory: Memory, context: dict) -> float
```

## Integration Points

### Upstream Dependencies
- Split 01 (FalkorDB Foundation): Entity nodes, graph structure, transaction API

### Downstream Dependencies
- Split 03 (Migration & Sync): Needs memory API for creating memories from migrated events
- Actor system (Track 5): Reads memories to enrich agent prompts
- Event bus: Listens for ChatMessage, JoinEvent, LeaveEvent to create memories

### Event Integration
- Subscribe to ChatMessage events → create memory node with embedding
- Subscribe to JoinEvent/LeaveEvent → create relationship memory
- Propagate memory updates to clients via existing WebSocket sync

### Agent Integration
- Actor prompts call `assemble_context()` before LLM inference
- Character descriptions + memories = enriched system prompt
- Query memories by entity_id to get "things you know about X"

## Testing Strategy
- Unit tests for embedding model (mock embeddings)
- Unit tests for memory CRUD operations
- Unit tests for similarity search with synthetic vectors
- Integration tests with FalkorDB foundation
- Performance tests for large memory sets (1000+ memories)
- Context assembly tests (validate token counts, formatting)

## Success Criteria
1. Embedding model can be initialized (local or cloud)
2. Text can be embedded and stored as memory nodes
3. Vector similarity search returns relevant memories ordered by score
4. Memory filtering by entity, type, timestamp works
5. Context assembly produces properly formatted agent context
6. Memory lifecycle (creation, expiration) is functional
7. Agent prompts improved with enriched context (subjective, but measurable via agent behavior)
8. Tests provide >80% code coverage
9. No performance degradation when searching large memory sets
10. Graceful fallback if embedding service unavailable
