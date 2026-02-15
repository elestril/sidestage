# Opus Review (Iteration 2)

**Model:** claude-opus-4
**Generated:** 2026-02-08

---

## Critical Issues (Must Fix)

### 1. entity_to_markdown / markdown_to_entity not addressed
Events will lose their `event_type` discriminator on export — `entity_to_markdown()` writes `entity.entity_type` (ClassVar="Event") to frontmatter, so all events export as generic "Event" with no way to distinguish ChatMessage from JoinEvent on reimport. `migration/serialization.py` has the same issue.

### 2. Migration pipeline not addressed
- `migration/serialization.py` TYPE_MAP has entries for deleted subclasses (ChatMessageModel, etc.)
- `migration/importer.py` _parse_chatlog_lines() constructs ChatMessageModel directly
- `migration/importer.py` _restore_chatlogs() writes to SceneModel.messages (removed)
- `migration/exporter.py` serializes SceneModel.messages into chatlog files
- None of these files are listed in downstream impact

### 3. NPCActor has no way to access recent messages for context assembly
AgentActor.on_event() currently accesses `self.scene_logic.messages` for assemble_context(). The plan's decoupled Actor design (no Scene reference) drops this. NPCActor.process() needs recent events for context assembly but has no way to get them.

### 4. entity_content_sync rebroadcast loses exclude-sender pattern
SyncManager.broadcast() has `exclude` parameter for keystroke sync — rebroadcasts to all clients EXCEPT the sender. Campaign.broadcast() as described has no exclude parameter. Entity content sync will echo back to the sender.

### 5. Graph storage of metadata dict
`entity_to_properties()` dumps model fields to flat key-value FalkorDB properties. A nested `Dict[str, Any]` can't be stored as a flat property. Needs JSON serialization or exclusion.

### 6. scene.chat() ownership conflict
Section 8.3: Campaign creates EventModel and calls `scene.chat(event)`. Section 6.7: Scene.chat() "creates a CHAT_MESSAGE event via create_event()". Who creates the event?

### 7. actor_status messages need scene_id
Frontend filters by scene_id. Without it, thinking indicators from other scenes would appear. ActorStatusMessage needs scene_id.

## Significant Issues

### 8. MCP bridge references to sync_manager
mcp_bridge.py calls `orchestrator.sync_manager.broadcast()` in ~6 places. Section 12.3 only mentions send_chat_message. All MCP tools need updating.

### 9. import_campaign() takes sync_manager parameter
migration/importer.py import_campaign() takes SyncManager. Needs Campaign or broadcast callback.

### 10. Orchestrator still owns active_scenes
Orchestrator has `self.active_scenes` dict and `get_active_scene()`. Plan moves Scene creation to Campaign but doesn't move scene ownership.

### 11. visibility should be an enum
`visibility: str = "public"` is stringly-typed. Should be `class Visibility(str, Enum)` like EventType.

### 12. metadata needs Field(default_factory=dict)
Codebase uses `Field(default_factory=list)` for mutable defaults. Follow same pattern.

### 13. walltime as datetime needs graph property handling
FalkorDB may not handle datetime natively. entity_to_properties() will yield datetime instead of string.

## Minor Issues

### 14. system_agent.txt doesn't exist
Plan references `data/prompts/system_agent.txt` but only default_npc.txt and unseen_npc.txt exist.

### 15. EventModel.name convention
What is `name` for JOIN/LEAVE/ERROR events? Currently "User Message" etc. No convention defined.

### 16. ChatRequest schema
ChatRequest has `message: str` — should it become `body` or stay as-is (API-facing)?

### 17. co-author.md default data needs owner/system_actor fields

### 18. character_id/actor_id optionality
Making these Optional on all events loses validation for types that require them. Consider model_validator.

### 19. Stale connection cleanup in Campaign.broadcast()

### 20. WebSocket accept() — who calls it, Campaign.connect() or Orchestrator?
