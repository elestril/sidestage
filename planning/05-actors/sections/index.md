<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-event-model
section-02-actors
section-03-storage
section-04-scene-loop
section-05-tracing
section-06-orchestrator
section-07-frontend
section-08-integration
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-event-model | - | all | Yes (foundation) |
| section-02-actors | 01 | 04, 06 | Yes (after 01) |
| section-03-storage | 01 | 06 | Yes (after 01, parallel with 02) |
| section-04-scene-loop | 01, 02 | 05, 06 | No |
| section-05-tracing | 01, 04 | 06 | No |
| section-06-orchestrator | 01-05 | 07, 08 | No |
| section-07-frontend | 06 | 08 | No |
| section-08-integration | all | - | No (final) |

## Execution Order

1. section-01-event-model (no dependencies — foundational types)
2. section-02-actors, section-03-storage (parallel after 01)
3. section-04-scene-loop (after 01 + 02)
4. section-05-tracing (after 04)
5. section-06-orchestrator (after all backend sections)
6. section-07-frontend (after API changes in 06)
7. section-08-integration (final — end-to-end tests)

## Section Summaries

### section-01-event-model
**Plan sections:** 2 (EventModel Restructuring) + 3 (Event Wrapper Class)

EventType enum, Visibility enum, flattened EventModel replacing 4 subclasses. Event runtime wrapper with OpenTelemetry span context. EventQueue update from EventModel to Event type. Delete ChatMessageModel, JoinEventModel, LeaveEventModel, FastForwardEventModel. Add owner/system_actor fields to CharacterModel. Update schemas.

### section-02-actors
**Plan sections:** 4 (Actor Hierarchy) + 5 (Character System Refactor)

Actor ABC with process() method. NPCActor (replaces AgentActor) with LLM integration and system_actor differentiation. User actor owning WebSocket connections. Character runtime wrapper refactored to pair CharacterModel with Actor. Campaign-scoped character registry with actor resolution (NPC vs player). Lifecycle management (activate/deactivate).

### section-03-storage
**Plan section:** 10 (Storage and Persistence)

Graph entity label system updated for flattened EventModel (entity_to_labels with event_type-specific labels). Entity serialization (markdown export/import) with event_type in frontmatter. Migration serialization TYPE_MAP/TYPE_TO_SUBDIR updates. Graph property handling for metadata (JSON string), walltime (ISO string), enums. Importer/exporter updates. SQLite storage changes. ConfigDict extra='ignore' safety net.

### section-04-scene-loop
**Plan section:** 6 (Scene Event Loop Refactor)

EventQueue consolidation (move from bus.py to event.py, delete bus.py). Scene.__init__ simplification. Scene.activate() with Campaign.get_character(). Scene.process() as public entry point. Scene._process_event() queue handler with persistence and dispatch. Scene._dispatch() to all present actors with actor_id deduplication. Thinking indicator lifecycle (thinking/idle status to Users). Scene.create_event() factory with evt_ prefix. Scene.chat() accepting raw parameters.

### section-05-tracing
**Plan section:** 7 (Tracing Integration)

Event span lifecycle: capture at creation, carry through queue, link at processing. Span linking pattern (new root span linked to incoming span context). NPCActor child spans under scene processing span. LLM call data in trace events. Error event tracing with span context links.

### section-06-orchestrator
**Plan sections:** 8 (User & WebSocket) + 9 (Campaign Agent) + 12 (API Changes)

Orchestrator WebSocket endpoint refactored to use User actor for connect/disconnect. Remove SyncManager and broadcast callback pattern. _handle_ws_message() routing to scene.chat() and user.send(). Campaign Co-Author as NPCActor with system_actor=True. Campaign.agent field removal. REST endpoint updates (ChatResponse, scene events endpoint). MCP bridge updates for EventModel. Schema updates.

### section-07-frontend
**Plan section:** 11 (Frontend Changes)

TypeScript EventModel interface and EventType type. WebSocket message types (EventBroadcast, ActorStatusMessage). AppContext state changes (messages as EventModel[], thinkingActors set). ChatWidget rendering event.body, thinking indicators with animated ellipsis, ERROR event styling. Visibility filtering. Scene messages endpoint consumption.

### section-08-integration
**Plan section:** 13 (Testing Strategy — Integration Tests)

End-to-end chat flow test (user message -> event -> persist -> dispatch -> NPC response). LLM failure -> ERROR event flow. Multi-character deduplication test. Co-Author participation test. ADJUST_GAMETIME test. Event tracing span link verification. Existing test migration from ChatMessageModel to EventModel.
