# Integration Notes: Opus Review Feedback

## Integrating (must-fix issues)

### Issue 1/8: Inventory has no graph relationship type
**Integrating.** Reviewer is correct — `VALID_REL_TYPES` has no inventory edge. The current system stores inventory as a list property on Character nodes. The plan should keep inventory as a node property (not edges) since that matches the existing system. Will remove the misleading "create inventory relationships" from the import plan and clarify that inventory is stored as a node property.

### Issue 2: graph.delete() API
**Integrating.** Will specify the correct FalkorDB API for graph deletion. The FalkorDB Python client uses `g.delete()` on the graph object returned by `db.select_graph()`. Will also document the reconnection flow needed after deletion.

### Issue 3: ensure_schema -> initialize_schema
**Integrating.** Will fix function name to `initialize_schema` and note the `vector_dimension` requirement for schema v2 migration.

### Issue 4: Concurrent access during import
**Integrating.** Will add an `importing` flag on the campaign/orchestrator that causes other graph-accessing endpoints to return 503 during import. Will also document the need to clear active_scenes after import.

### Issue 5: Backup atomicity
**Integrating.** Will change backup to write to a temporary directory first, then swap atomically. This prevents data loss if export crashes mid-write.

### Issue 9: CONNECTS_TO duplicate edges
**Integrating.** Will deduplicate CONNECTS_TO edges during import: sort the pair (A,B) and only create the edge once per unique pair.

### Issue 15: Memory nodes destroyed on import
**Integrating.** Will add explicit warning in the plan that import destroys all data including Memory nodes. The API should include this in the validation report warning. This matches the user's decision (Q10: "Drop graph entirely").

## Integrating (should-fix issues)

### Issue 7: Event subclasses not handled
**Integrating.** Will add ChatMessage, JoinEvent, LeaveEvent, FastForwardEvent to the type map. Will also explicitly exclude Scene.messages from import/export since messages live in SQLite.

### Issue 10: No test plan
**Integrating.** Will add a testing section. (TDD plan comes in step 16 anyway, but basic testing guidance belongs in the plan.)

### Issue 17: API response type ambiguity
**Integrating.** Will use discriminated union with `action` field. Will also use distinct names to avoid conflict with existing ImportResponse/ExportResponse in schemas.py.

### Issue 18: Existing routes conflict
**Integrating.** Will explicitly state that old /v1/entities/import and /v1/entities/export routes are deprecated but left in place for now.

### Issue 22: Dataclass vs Pydantic
**Integrating.** Will change to Pydantic BaseModel for consistency with codebase patterns.

## NOT Integrating

### Issue 6: Filename convention inconsistency
**Not integrating.** The new system is a clean break. Old export used `{id}.md`; new backup will use `{type}_{id}.md` for clarity. Since import ignores filenames, this is not a compatibility issue. The old export function is left untouched.

### Issue 11: Progress streaming
**Not integrating.** For the initial implementation, a synchronous POST returning final status is sufficient. The ImportProgress model is still useful for the response — it reports the final counts and any errors. Streaming can be added later if needed.

### Issue 12: TOCTOU race
**Not integrating.** Acknowledged as a known limitation. For a single-user system this is acceptable. The `force: false` path re-validates, and users who click "proceed" accept the current state.

### Issue 13: Missing type field default behavior change
**Not integrating as an error.** Will match existing behavior: default to "Character" when type is missing, but log a warning. This preserves backward compatibility with existing campaigns.

### Issue 14: Reuse entity_to_markdown()
**Partially integrating.** Will reuse `entity_to_markdown()` for serialization in the exporter rather than reimplementing. But the importer still needs its own parser since the existing `markdown_to_entity()` has different error handling needs.

### Issue 16: Verification query specificity
**Not integrating separately.** Obvious that verification should use `MATCH (n:Entity)`. No plan change needed.

### Issues 19-21: Minor issues
**Not integrating.** These are implementation details that don't need plan-level changes.
