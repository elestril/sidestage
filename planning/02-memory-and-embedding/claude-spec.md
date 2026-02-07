# Synthesized Spec: Memory and Embedding System

## Overview

Implement an LLM-driven memory system for Sidestage agents with layered visibility. Memories are living text documents stored as FalkorDB graph nodes — updated explicitly by LLM tool calls. A generic visibility model (`"common"` / `"private"`) controls access, designed for future expansion to rich ACLs.

## Architecture Context

Sidestage is an AI Co-Author for tabletop RPGs. It uses:
- **FalkorDB** as graph database (split 01 complete): entity CRUD, relationships, queries
- **LiteLLM** for multi-provider LLM abstraction (OpenAI, Gemini, llama.cpp)
- **AsyncIO** throughout, with `SceneMessageBus` for event dispatch
- **Pydantic** models for entities (Character, Location, Event, ChatMessage, etc.)
- **Campaign** as top-level organizer: config, LLM setup, entity management, graph lifecycle
- **LiteLLMAgent** with tool calling support (auto-schema, async tools, max 5 turns)

## Core Design

### Memory Types
1. **Scene memories** — with visibility layers:
   - `common`: what everyone generally knows ("there was a bar fight")
   - `private` + DM owner: canonical truth ("the assassin poisoned the drink")
   - `private` + character owner: personal recollection ("I observed from the second floor")
2. **Character memories** — one per character about each other character (always private)
3. **World facts** — facts about entities, either generally known (common) or restricted (private)

### Visibility Model
- Generic `visibility: str` field: `"common"` or `"private"` today
- Extensible to rich ACLs later without schema migration
- Context assembly rule: `visibility == "common" OR owner_id == this_character`

### LLM-Driven Updates
- Character LLMs call `update_scene_memory(content)` / `update_character_memory(about_character_id, content)` when they decide something is noteworthy
- DM/Co-Author calls `update_common_memory()` / `update_canonical_memory()` / `add_world_fact()`
- No automatic event-to-memory pipeline

### Character Context During a Scene
1. Character description (existing template + body)
2. Generally known world facts (common visibility)
3. Common scene memory
4. Personal scene memory
5. Character memories about present characters
6. Recent chat history — 20% of configured context window

### Embeddings
- LiteLLM `aembedding()` with "embed" config
- Async and non-blocking — text persists immediately, embedding in background
- Primary retrieval is graph-based; embeddings for future cross-memory search

## Key Decisions

- **Memory nodes** use `:Memory` label, separate from `:Entity` hierarchy
- **Own Cypher** in `memory/store.py`, not using `graph/entities.py` or `graph/relationships.py`
- **Upsert semantics**: one memory per (owner_id, memory_type, target_id) tuple
- **Context limit** validated at startup via `/status` endpoint
- **Health system**: HEALTHY → DEGRADED (embed fail) → UNHEALTHY (graph fail)
- **Graph relationships**: `HAS_MEMORY` (owner → memory), `ABOUT` (memory → target)

## Scope

### In Scope
- Memory Pydantic models with generic visibility field
- Three memory types: scene, character, world_fact
- Memory CRUD with upsert semantics in FalkorDB
- NPC memory tools (update_scene_memory, update_character_memory)
- DM memory tools (update_common_memory, update_canonical_memory, add_world_fact)
- Context assembly with visibility-based filtering
- Embedding generation via LiteLLM (async, non-blocking)
- FalkorDB vector indexing for future similarity search
- Agent integration (context parameter on arun(), memory tools)
- Campaign health status system
- Schema v2 migration
- Config validation (embed endpoint, context limits)
- Unit and integration tests

### Out of Scope
- Rich ACL implementation (visibility field is extensible, but only common/private for now)
- Memory migration from SQLite (split 03)
- Cross-memory vector search UX (index created, search available, not wired into context)
- Memory consolidation, summarization, or auto-expiration
- Memory visualization UI
