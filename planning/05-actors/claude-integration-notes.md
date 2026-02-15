# Integration Notes: Opus Review Feedback

## Iteration 1 Review Source
- `reviews/iteration-1-opus.md` — Claude Opus subagent review

## Iteration 2 Review Source
- `reviews/iteration-2-opus.md` — Claude Opus subagent review (post-revisions)

## Iteration 2 Changes Applied

### ACCEPTED (Critical): entity_to_markdown / markdown_to_entity — Issue #1
Events lose event_type discriminator on export since entity_type ClassVar is "Event" for all. Added Section 10.3 to explicitly serialize event_type in frontmatter.

### ACCEPTED (Critical): Migration pipeline — Issue #2
migration/serialization.py, importer.py, exporter.py all break. Added to downstream impact list and detailed in Section 10.3.

### ACCEPTED (Critical): NPCActor context assembly — Issue #3
AgentActor needs recent_messages for assemble_context(). Added `recent_events` parameter to Actor.process() signature. Scene passes its event history.

### ACCEPTED (Critical): entity_content_sync exclude-sender — Issue #4
Campaign.broadcast() now has `exclude: WebSocket | None` parameter to support entity_content_sync rebroadcast.

### ACCEPTED (Critical): Graph storage of metadata dict — Issue #5
Added Section 10.4 specifying JSON serialization for metadata and ISO string for walltime in entity_to_properties().

### ACCEPTED (Critical): scene.chat() ownership — Issue #6
Clarified Scene.chat() accepts raw data (actor_id, text, character_id), creates Event internally. Campaign passes raw data, doesn't create events.

### ACCEPTED (Critical): actor_status needs scene_id — Issue #7
Added scene_id to ActorStatusMessage TypeScript interface.

### ACCEPTED (Significant): MCP bridge sync_manager references — Issue #8
Updated Section 12.3 to cover ALL ~6 sync_manager.broadcast() call sites in mcp_bridge.py.

### ACCEPTED (Significant): import_campaign sync_manager parameter — Issue #9
Noted in migration/importer.py updates (Section 10.3).

### ACCEPTED (Significant): Active scene ownership — Issue #10
Added to downstream impact: campaign.py gets active_scenes (moved from orchestrator).

### ACCEPTED (Significant): visibility should be enum — Issue #11
Added Visibility(str, Enum) to Section 2.1, updated EventModel field.

### ACCEPTED (Significant): metadata default_factory — Issue #12
Changed to Field(default_factory=dict).

### ACCEPTED (Significant): walltime graph handling — Issue #13
Covered in Section 10.4 (serialize to ISO string for FalkorDB).

### ACCEPTED (Minor): system_agent.txt — Issue #14
Added to Section 9.1 data file changes.

### ACCEPTED (Minor): EventModel.name convention — Issue #15
Added name convention by event type to Section 2.2.

### NOTED (Minor): ChatRequest schema — Issue #16
ChatRequest keeps `message: str` as its API-facing field name. Scene.chat() maps it internally.

### ACCEPTED (Minor): co-author.md needs owner/system_actor — Issue #17
Added to Section 9.1 data file changes.

### NOTED (Minor): character_id/actor_id optionality — Issue #18
Acknowledged. Can add model_validator during implementation if needed.

### ACCEPTED (Minor): Stale connection cleanup — Issue #19
Campaign.broadcast() removes dead connections on send failure.

### ACCEPTED (Minor): WebSocket accept() — Issue #20
Campaign.connect() calls accept(). Clarified in Section 8.1.
