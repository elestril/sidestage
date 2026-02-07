<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-models-and-health
section-02-schema-migration
section-03-memory-store
section-04-embeddings
section-05-memory-tools
section-06-context-assembly
section-07-agent-integration
section-08-scene-integration
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-models-and-health | - | all | Yes |
| section-02-schema-migration | 01 | 03 | No |
| section-03-memory-store | 01, 02 | 05, 06 | No |
| section-04-embeddings | 01 | 05 | Yes (parallel with 02, 03) |
| section-05-memory-tools | 03, 04 | 07 | No |
| section-06-context-assembly | 03 | 07, 08 | Yes (parallel with 05) |
| section-07-agent-integration | 05, 06 | 08 | No |
| section-08-scene-integration | 07 | - | No |

## Execution Order

1. section-01-models-and-health (no dependencies)
2. section-02-schema-migration, section-04-embeddings (parallel after 01)
3. section-03-memory-store (after 02)
4. section-05-memory-tools, section-06-context-assembly (parallel after 03 + 04)
5. section-07-agent-integration (after 05 AND 06)
6. section-08-scene-integration (final)

## Section Summaries

### section-01-models-and-health
Pydantic models (Memory, MemoryType, ContextResult, ContextMemories), the CampaignHealth class with health status transitions, and LLMConfig/GraphConfig field extensions. Foundation that everything else depends on.

**Plan sections:** 3 (Memory Models), 9 (Campaign Health Status), config fields from 4
**TDD sections:** Memory Models, Campaign Health Status, Campaign Configuration

### section-02-schema-migration
FalkorDB schema v2 migration: vector index creation (conditional on vector_dimension), range indexes on Memory properties (owner_id, target_id, memory_type, visibility), version bump from 1 to 2. Extends initialize_schema() with vector_dimension parameter.

**Plan sections:** 5 (Schema Migration)
**TDD sections:** Schema Migration (v2)

### section-03-memory-store
Memory CRUD operations in FalkorDB using own Cypher (not Entity functions). Upsert functions (scene, common scene, character, world fact), read functions (get_scene_memory, get_common_scene_memory, get_character_memory, get_memories_for_context), delete, touch, and vector search. Internal relationship type validation.

**Plan sections:** 6 (Memory Store)
**TDD sections:** Memory Store (CRUD + Search)

### section-04-embeddings
Embedding generation via LiteLLM aembedding(). embed_text() for single text, embed_and_update() as fire-and-forget that updates memory nodes and manages health transitions. EmbeddingError exception. Embed config validation logic (model verification, test embedding call for dimension detection).

**Plan sections:** 4 (Embedding Generation)
**TDD sections:** Embedding Generation

### section-05-memory-tools
Agent-callable memory tools: MemoryTools class for NPC characters (update_scene_memory, update_character_memory) and DM tools (update_common_memory, update_canonical_memory, add_world_fact). Tools call store upsert functions and fire background embedding tasks.

**Plan sections:** 7 (Memory Tools)
**TDD sections:** Memory Tools (Agent-Callable)

### section-06-context-assembly
Context assembly function that fetches applicable memories (visibility filter: common OR owner=self), formats them into sections, and trims chat history to context window budget (20% of context_limit). ContextResult construction.

**Plan sections:** 8 (Context Assembly)
**TDD sections:** Context Assembly

### section-07-agent-integration
Add context parameter to LiteLLMAgent.arun() — inserts system message between system prompt and user message. Modify AgentActor to call assemble_context() in on_event() and pass result to arun(). Add MemoryTools to agent tool list. Campaign embed validation and health wiring.

**Plan sections:** 8 (Integration with AgentActor), 10 (CharacterLogic/AgentActor Changes), agent.py changes
**TDD sections:** Agent Integration (arun context parameter), parts of Scene Integration

### section-08-scene-integration
Wire everything together in SceneLogic: pass graph_client/embed_config/health/context_limit to CharacterLogic during scene activation. Ensure AgentActor receives MemoryTools. End-to-end integration test that a character can receive context and call memory tools.

**Plan sections:** 10 (Scene Integration), 11 (Configuration)
**TDD sections:** Scene Integration
