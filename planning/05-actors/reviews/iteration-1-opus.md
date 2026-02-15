# Opus Review

**Model:** claude-opus-4
**Generated:** 2026-02-08T00:00:00Z

---

# Plan Review: Actor Restructuring (05-actors)

## Overall Assessment

This is a well-structured plan that addresses real architectural debt. The goals are clear, the implementation order is sensible, and the dependency chain is correctly identified. However, there are several significant issues ranging from a fundamental Pydantic modeling problem to missing details on critical subsystems.

---

## 1. Critical: entity_type ClassVar-to-Instance Field Conversion (Section 2.2)

**The single biggest risk in this plan.**

The plan says:

> `entity_type` is no longer a ClassVar -- it's a per-instance field from the EventType enum

But `entity_type` is a `ClassVar` on **every model in the hierarchy**, not just EventModel subclasses. In `src/sidestage/models.py`:

```python
class EntityModel(BaseModel):
    entity_type: ClassVar[str] = "Entity"

class CharacterModel(EntityModel):
    entity_type: ClassVar[str] = "Character"
```

The plan only converts `entity_type` to a per-instance field on EventModel, while all other models (CharacterModel, LocationModel, ItemModel, SceneModel) keep it as a ClassVar. This creates an inconsistency in the EntityModel hierarchy: the base class has `entity_type: ClassVar[str]`, but EventModel overrides it as `entity_type: EventType` (a regular instance field). This is a Pydantic anti-pattern and will likely cause confusing behavior.

**Specific problems:**

- Pydantic's `model_dump()` does not include ClassVar fields. The code in `src/sidestage/entities.py` line 22 relies on `entity.entity_type` returning the class-level string for serialization (`data["type"] = entity.entity_type`). For EventModel instances, this will now return an `EventType` enum member instead of a plain string, which will break YAML serialization in the markdown export pipeline.

- The graph entity layer in `src/sidestage/graph/entities.py` uses `LABEL_TO_MODEL` and `MODEL_TO_LABELS` registries that map specific Python classes to graph labels. The plan says to delete `ChatMessageModel`, `JoinEventModel`, etc., but does not explain how the graph label system handles a single `EventModel` class that can be any of several EventTypes. Currently, ChatMessages are stored with labels `["Entity", "Event", "ChatMessage"]`. After the flattening, what labels will a CHAT_MESSAGE event get? Just `["Entity", "Event"]`? The plan does not specify this, and it will cause loss of query granularity in FalkorDB.

- `model_dump()` will include `entity_type` as a regular field for EventModel but not for other EntityModel subclasses. Code that calls `model_dump()` on mixed entity lists will get inconsistent dictionaries. The migration serializer does `data["type"] = entity.entity_type`, and the exporter does `type_name = entity.entity_type`. Both of these patterns work for ClassVar access but will behave differently when `entity_type` is an instance field of an enum type.

**Recommendation:** Either (a) make `entity_type` an instance field on ALL EntityModel subclasses (a much larger change), or (b) keep `entity_type` as a ClassVar on EventModel too and use a separate `event_type: EventType` field for the event-specific discriminator. Option (b) is far less invasive and preserves consistency with the rest of the hierarchy.

---

## 2. Significant: Graph Label Strategy After Flattening (Section 10.2)

The plan says:

> The graph entity creation (`create_entity`) works with any EntityModel -- it just needs `entity_type` as a string for the node label. Since EventType is a `str` enum, `event.entity_type.value` gives the label string.

This is under-specified. Currently in `src/sidestage/graph/entities.py`, `entity_to_labels()` uses `MODEL_TO_LABELS` which is a class-level mapping:

```python
MODEL_TO_LABELS: dict[type[EntityModel], list[str]] = {
    ChatMessageModel: ["Entity", "Event", "ChatMessage"],
    JoinEventModel: ["Entity", "Event", "JoinEvent"],
    ...
}
```

After flattening to a single EventModel, `type(event)` is always `EventModel`, so this lookup returns `["Entity", "Event"]` for ALL events. The plan needs to specify how the label mapping works for a single class with a discriminating instance field.

**Recommendation:** The plan should specify that `entity_to_labels()` be updated to inspect `event_type` and generate labels like `["Entity", "Event", "ChatMessage"]` for CHAT_MESSAGE events, and that `node_to_entity()` should populate the `event_type` instance field from the most-specific label.

---

## 3. Significant: body Field Collision (Section 2.2)

The plan says:

> `EntityModel.body` (inherited) is repurposed: for CHAT_MESSAGE it holds the message content as rich markdown

But `EntityModel.body` already has a defined purpose -- it is the entity description markdown that appears after the YAML frontmatter. In `src/sidestage/entities.py`:

```python
def entity_to_markdown(entity: EntityModel) -> str:
    data = entity.model_dump()
    body = data.pop("body", "")
    # ...
    return f"---\n{frontmatter}\n---\n\n{body}"
```

If a ChatMessage event has `body = "Hello everyone, let's roll for initiative!"`, then exporting that event to markdown will produce a markdown file where the entity description IS the chat message text. This is semantically confused. The current design has `message` as a separate field for exactly this reason.

**Recommendation:** Keep a distinct field for chat content rather than overloading `body`. Call it `content` or keep `message` as an optional field on EventModel. This avoids subtle bugs in the markdown import/export roundtrip and keeps entity serialization consistent.

---

## 4. Significant: Character Registry is a Global Singleton with No Scoping (Section 5.1)

The plan introduces:

```python
class Character:
    _instances: ClassVar[Dict[str, "Character"]] = {}
```

This is a process-global dictionary. The plan acknowledges "the app is single-threaded (asyncio), so no locking needed," but misses a more fundamental concern: **campaign scoping**. The orchestrator manages multiple campaigns (`self.campaigns: Dict[str, Campaign]`). A global Character registry shared across campaigns means:

- Character IDs from different campaigns could collide.
- `Character.clear_registry()` for one campaign's shutdown wipes characters from all campaigns.
- There is no isolation between campaigns.

**Recommendation:** Scope the registry per-Campaign or per-Scene instead of making it global. Pass a campaign-scoped registry dict, or make it an instance attribute on Campaign rather than a ClassVar on Character.

---

## 5. Significant: NPCActor Tight Coupling to Scene Internals (Section 4.2)

The plan says NPCActor.process() will:

> create an EventModel with `entity_type=CHAT_MESSAGE`, wrap in Event, enqueue back to scene

But the plan does not specify how NPCActor gets a reference to the scene's queue. The current `AgentActor` solves this via `self.scene_logic` -- a direct reference to the Scene object.

The new design says Actor has only `actor_id` and `process()`. How does NPCActor put events back on the queue?

**Recommendation:** Define explicitly in the plan how NPCActor enqueues response events. Consider having `process()` return `Optional[Event]` instead of `None`, with the Scene handling the enqueue. This eliminates the circular dependency entirely.

---

## 6. Moderate: _dispatch Runs Actors Sequentially, Not Concurrently (Section 6.5)

The plan says:

> Calls `actor.process(event)` on every present Character's actor.

With multiple NPCs each making LLM calls, this means NPC responses are generated one at a time.

**Recommendation:** Consider using `asyncio.gather()` for concurrent dispatch to NPCs. Add a note about whether concurrent or sequential dispatch is intentional.

---

## 7. Moderate: Missing ADJUST_GAMETIME Semantics (Section 2.2)

The plan says:

> For ADJUST_GAMETIME: the `gametime` field carries the target absolute gametime; Scene sets `current_gametime = event.gametime` when processing

But there is no specification of:

- Who creates ADJUST_GAMETIME events
- Whether _process_event has special-case logic for ADJUST_GAMETIME beyond persisting/broadcasting
- What replaces `FastForwardEventModel.duration_str` in terms of user experience

**Recommendation:** Add an explicit subsection for event type-specific processing in `_process_event`.

---

## 8. Moderate: Chat Endpoint API Breaking Change Not Fully Specified (Section 12.1)

The MCP bridge's `send_chat_message` tool does:

```python
return {"user_message": user_msg.model_dump()}
```

The plan does not mention updating the MCP tool's return value.

**Recommendation:** Be explicit about the MCP bridge return format change and test it. MCP tool return values are consumed by external AI agents.

---

## 9. Moderate: WebSocket Reconnection is Broken in Current Code (Section 8)

The frontend AppContext has:

```javascript
s.onclose = () => {
    console.log('WebSocket disconnected. Retrying in 2s...');
    setSocket(null);
    setTimeout(() => {}, 2000);  // This does nothing
};
```

The reconnection is a no-op. Since this is a breaking refactor anyway, it is worth fixing.

---

## 10. Moderate: Missing Frontend Widget Migration Path (Section 11.4)

The plan says:

> Remove widget rendering from separate field -- widgets are now part of the markdown body

But there is no specification for what markdown syntax will represent an entity card widget, how the ChatWidget will parse and render these, or how the LLM agent will be instructed to produce this new format.

**Recommendation:** Either (a) keep the `widget` field as an optional field on EventModel (simplest), or (b) specify the exact markdown embedding syntax and the frontend parser for it.

---

## 11. Minor: Event ID Prefix Inconsistency (Section 6.6)

The current `create_message()` uses prefix `msg_`. The plan replaces this with `create_event()` but does not specify the ID prefix scheme for different event types.

**Recommendation:** Define the ID prefix scheme: `evt_chat_`, `evt_join_`, etc., or just `evt_` for all.

---

## 12. Minor: system_actor Determination is Vague (Section 9.1)

"e.g." and "or" are not a specification. This needs to be a definite rule.

**Recommendation:** Add a field to CharacterModel (e.g., `system_actor: bool = False`) or use a deterministic convention. Make it explicit and testable.

---

## 13. Minor: Removed `message` Field but Existing Data in Graph (Section 2.2 / Section 10.3)

The plan says "No migration" for SQLite, but FalkorDB graph nodes may also have `message` properties. If the graph is not wiped, `node_to_entity()` will try to construct EventModel from properties that include a `message` field that no longer exists.

**Recommendation:** Make the clean break explicit: "Wipe both SQLite AND FalkorDB graph."

---

## 14. Minor: No Error Event Broadcasting to Frontend (Section 7.4 / Section 11)

The plan introduces `EventType.ERROR` but the frontend changes only describe rendering `CHAT_MESSAGE` body content. There is no specification for how ERROR events render in the chat UI.

---

## 15. Architectural: Co-Author NPCActor Gets NPC-Specific Prompts (Section 9.2)

The plan says the Co-Author becomes an NPCActor that "participates in scenes like any other NPC." But the current Co-Author agent has world-building tools and system-level instructions, while regular NPCs get character-specific tools.

**Recommendation:** Specify how NPCActor differentiates between regular NPCs and the Co-Author in terms of prompt templates, tool sets, and instructions.

---

## Summary of Recommendations by Priority

| Priority | Item | Section |
|---|---|---|
| **Critical** | Resolve entity_type ClassVar vs instance field inconsistency | 2.2 |
| **Critical** | Specify graph label strategy for flattened EventModel | 10.2 |
| **Significant** | Avoid body field collision -- use a distinct content field | 2.2 |
| **Significant** | Scope Character registry per-Campaign, not global | 5.1 |
| **Significant** | Specify how NPCActor enqueues responses back to Scene | 4.2 |
| **Moderate** | Consider concurrent NPC dispatch | 6.5 |
| **Moderate** | Specify ADJUST_GAMETIME processing semantics | 2.2, 6.4 |
| **Moderate** | Specify MCP bridge return format change | 12.3 |
| **Moderate** | Address or note broken WebSocket reconnection | 8 |
| **Moderate** | Specify widget embedding strategy or keep the field | 11.4 |
| **Minor** | Define event ID prefix scheme | 6.6 |
| **Minor** | Make system_actor determination deterministic | 9.1 |
| **Minor** | Clarify clean break scope (graph + SQLite) | 10.3 |
| **Minor** | Specify error event frontend rendering | 11 |
| **Minor** | Address Co-Author tool/prompt differentiation | 9.2 |
