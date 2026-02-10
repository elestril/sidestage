# Code Review: Section 01 - Event Model

The implementation faithfully matches the plan in all structural respects -- enums, flattened EventModel, CharacterModel additions, SceneModel removal, Event wrapper, EventQueue. However, there are several issues ranging from critical runtime breakage to design concerns.

## CRITICAL: Runtime Breakage Not Addressed in Plan's Own Scope

1. **`ChatResponse` schema change breaks the orchestrator at runtime.** In `orchestrator.py` line 443, the code calls `ChatResponse(user_message=user_msg)`. The schema was changed to accept `event: EventModel` instead of `user_message: ChatMessageModel`. The plan says downstream consumers are fixed in later sections, but `orchestrator.py` directly imports and uses `ChatResponse` -- the very schema this section changed. This means the `/v1/chat` endpoint will crash immediately with a Pydantic validation error.

2. **`graph/entities.py` LABEL_TO_MODEL -- stale graph nodes with old labels will silently deserialize incorrectly.** Old `ChatMessage` nodes do not have `event_type` -- a required field with no default -- causing `ValidationError` on deserialization. `extra="ignore"` only handles extra fields, not missing required ones.

3. **`scene_events` query in `graph/queries.py` still has a stale docstring** referencing 'ChatMessage subtype based on node labels'.

## HIGH: Semantic Issues

4. **`EntityModel.body` default changed from required to `""`.** This is an undocumented side effect broader than the plan specifies.

5. **`EventQueue._worker` silently swallows exceptions and continues** without calling `task_done()`. Pre-existing bug carried forward.

6. **`Event.character` property uses `getattr(self.scene, "characters", {})`.** Zero type safety; a `Protocol` type would be safer.

## MEDIUM: Test Coverage Gaps

7. **No test for `Event.from_model()` when an active OpenTelemetry span IS present.**

8. **No test for `EventQueue` error handling behavior.**

9. **No negative test for `EventModel` with invalid `event_type` value.**

10. **Async tests use `anyio_backend` fixture but plan specifies `pytest.mark.asyncio`.** Valid approach but diverges from plan.

## LOW: Minor Issues

11. **`EventModel.metadata` will be written to graph properties.** FalkorDB doesn't support nested dicts natively. No `EXCLUDED_FIELDS` entry for metadata.

12. **`bus.py` left intact -- two `EventQueue` classes with different type signatures.**

13. **No `__all__` export in `event.py`.**

14. **`SpanContext` only imported under `TYPE_CHECKING` but used at runtime.** Works via duck typing but fragile.
