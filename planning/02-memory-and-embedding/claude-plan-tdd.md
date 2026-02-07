# TDD Plan: Memory and Embedding System

Mirrors the structure of `claude-plan.md`. For each section, defines what tests to write BEFORE implementing.

**Testing stack:** pytest + pytest-anyio, unittest.mock (AsyncMock, MagicMock), existing conftest.py patterns. Tests in `tests/unit/` and `tests/integration/`.

---

## 3. Memory Models

```python
# tests/unit/test_memory_models.py

# Test: Memory model validates all required fields
# Test: Memory model accepts None for optional fields (embedding, owner_id, gametime, last_accessed_at)
# Test: MemoryType enum has correct values (scene, character, world_fact)
# Test: Memory with visibility="common" and owner_id=None is valid
# Test: Memory with visibility="private" and owner_id set is valid
# Test: Memory serialization round-trip (model_dump / model construction)
# Test: ContextResult model has memory_text, chat_text, token_estimate fields
# Test: ContextMemories model groups memories correctly (common_scene, private_scene, character_memories, world_facts)
```

---

## 4. Embedding Generation

```python
# tests/unit/test_embeddings.py

# Test: embed_text calls litellm.aembedding with correct model string for llama_cpp provider
# Test: embed_text calls litellm.aembedding with correct model string for gemini provider
# Test: embed_text returns list of floats from successful response
# Test: embed_text raises EmbeddingError on litellm failure
# Test: embed_text raises EmbeddingError on timeout
# Test: embed_and_update updates memory node embedding on success (mock store)
# Test: embed_and_update transitions health to DEGRADED on failure
# Test: embed_and_update transitions health back to HEALTHY on success after prior failure
# Test: embed_and_update does not crash when health callback is None
```

---

## 5. Schema Migration (v2)

```python
# tests/unit/test_schema_v2.py

# Test: initialize_schema with vector_dimension creates vector index
# Test: initialize_schema without vector_dimension skips vector index
# Test: v2 migration creates range indexes on owner_id, target_id, memory_type, visibility
# Test: v2 migration stores dimension on SchemaVersion node
# Test: schema version bumps from 1 to 2
# Test: initialize_schema is no-op when already at version 2
# Test: CURRENT_VERSION is 2
```

---

## 6. Memory Store (CRUD + Search)

```python
# tests/unit/test_memory_store.py

# --- Upsert operations ---
# Test: upsert_memory creates new Memory node with correct labels (Memory:SceneMemory)
# Test: upsert_memory creates HAS_MEMORY and ABOUT relationships for private memory
# Test: upsert_memory for common memory creates ABOUT relationship without HAS_MEMORY (no owner)
# Test: upsert_memory updates content and updated_at when memory already exists
# Test: upsert_memory preserves id and created_at on update
# Test: upsert_scene_memory creates private scene memory with correct owner_id and target_id
# Test: upsert_common_scene_memory creates common scene memory with owner_id=None
# Test: upsert_character_memory creates private character memory
# Test: upsert_world_fact with visibility="common" creates common world fact
# Test: upsert_world_fact with visibility="private" creates private world fact with owner

# --- Read operations ---
# Test: get_scene_memory returns memory for matching owner_id + scene_id
# Test: get_scene_memory returns None when no memory exists
# Test: get_common_scene_memory returns common scene memory
# Test: get_character_memory returns memory for matching owner + about_character
# Test: get_character_memory returns None for non-existent pair
# Test: get_memories_for_context returns all applicable memories in a single call
# Test: get_memories_for_context returns common memories even with no private memories
# Test: get_memories_for_context returns world facts connected to entities in the scene
# Test: get_all_memories returns all memories for an owner
# Test: get_all_memories filters by memory_type when specified

# --- Delete / Touch ---
# Test: delete_memory removes node and all relationships
# Test: delete_memory is no-op for non-existent id
# Test: touch_memory increments access_count
# Test: touch_memory updates last_accessed_at

# --- Vector search ---
# Test: search_similar returns memories ordered by score
# Test: search_similar post-filters by owner_id when specified
# Test: search_similar post-filters by visibility when specified
# Test: search_similar returns empty list when no vector index exists

# --- Cypher safety ---
# Test: store validates relationship types against MEMORY_REL_TYPES
# Test: store uses parameterized queries (no string interpolation of user values)
```

---

## 7. Memory Tools (Agent-Callable)

```python
# tests/unit/test_memory_tools.py

# --- NPC Tools ---
# Test: update_scene_memory calls upsert_scene_memory with correct owner_id and scene_id
# Test: update_scene_memory fires embed_and_update as background task
# Test: update_scene_memory returns JSON with memory ID
# Test: update_scene_memory returns error JSON when graph fails
# Test: update_character_memory calls upsert_character_memory with correct parameters
# Test: update_character_memory returns JSON with memory ID
# Test: MemoryTools binds to specific owner_id and scene_id at construction

# --- DM Tools ---
# Test: update_common_memory calls upsert_common_scene_memory
# Test: update_canonical_memory calls upsert_memory with visibility="private" and DM owner_id
# Test: add_world_fact with visibility="common" creates common world fact
# Test: add_world_fact with visibility="private" creates private world fact
# Test: DM tools fire embed_and_update as background task
```

---

## 8. Context Assembly

```python
# tests/unit/test_context.py

# --- Assembly ---
# Test: assemble_context returns ContextResult with all sections populated
# Test: assemble_context includes common scene memory in output
# Test: assemble_context includes private scene memory for the owner
# Test: assemble_context excludes other characters' private scene memories
# Test: assemble_context includes character memories about present characters only
# Test: assemble_context includes common world facts
# Test: assemble_context excludes private world facts owned by other characters
# Test: assemble_context returns empty memory_text when no memories exist
# Test: assemble_context omits sections with no content

# --- Chat history trimming ---
# Test: chat history trimmed to 20% of context_limit by default
# Test: chat history ratio is configurable
# Test: chat history preserves most recent messages (trims oldest)
# Test: chat history formats messages as "[CharacterName]: message text"
# Test: empty message list produces empty chat_text

# --- Token estimation ---
# Test: token_estimate is roughly chars / 4
# Test: token_estimate accounts for both memory_text and chat_text

# --- Visibility filter ---
# Test: visibility filter includes visibility="common" memories
# Test: visibility filter includes visibility="private" where owner_id matches
# Test: visibility filter excludes visibility="private" where owner_id doesn't match
```

---

## 9. Campaign Health Status

```python
# tests/unit/test_health.py

# Test: CampaignHealth initializes with HEALTHY status
# Test: set_status transitions status and stores reason
# Test: set_status fires on_change callback when status changes
# Test: set_status does not fire on_change when status unchanged
# Test: set_status works when on_change is None
# Test: is_accepting_chat returns True for HEALTHY
# Test: is_accepting_chat returns True for DEGRADED
# Test: is_accepting_chat returns False for UNHEALTHY
# Test: is_embedding_available returns True for HEALTHY
# Test: is_embedding_available returns False for DEGRADED
# Test: is_embedding_available returns False for UNHEALTHY
```

---

## 10. Scene Integration

```python
# tests/integration/test_memory_integration.py

# Test: SceneLogic passes graph_client to CharacterLogic when available
# Test: AgentActor receives MemoryTools when graph_client exists
# Test: AgentActor tool list includes update_scene_memory and update_character_memory
# Test: AgentActor.on_event calls assemble_context before arun
# Test: AgentActor.on_event passes context to arun
# Test: AgentActor.on_event gracefully degrades when assemble_context fails
# Test: AgentActor works without memory system (graph_client=None, no memory tools)
```

---

## Agent Integration (arun context parameter)

```python
# tests/unit/test_agent_context.py

# Test: arun without context parameter works as before (backwards compatible)
# Test: arun with context inserts system message between system prompt and user message
# Test: arun with empty string context is equivalent to no context
# Test: arun with context preserves tool calling behavior
```

---

## Campaign Configuration

```python
# tests/unit/test_campaign_config.py

# Test: LLMConfig accepts context_limit field
# Test: LLMConfig accepts memory_token_budget field
# Test: LLMConfig defaults context_limit and memory_token_budget to None
# Test: GraphConfig accepts vector_dimension field
# Test: GraphConfig defaults vector_dimension to None
# Test: SidestageConfig serialization includes new fields
# Test: Existing config files without new fields load without error (backwards compat)
```
