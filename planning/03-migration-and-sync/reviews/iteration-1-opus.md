# Opus Review

**Model:** claude-opus-4-6
**Generated:** 2026-02-07

---

## Critical Issues

### 1. No Relationship Type for Character Inventory

Section 4.4, bullet "Character.inventory -> iterate item IDs, create appropriate relationships" says to create "appropriate relationships" but never specifies which relationship type to use. The `VALID_REL_TYPES` frozenset contains no inventory-related relationship type (OWNS, HAS_ITEM, POSSESSES, etc.). Inventory is only stored as a list of item IDs on the Character schema field. The plan's importer will call `link()` with some relationship type, but that type does not exist and will be rejected by `_validate_rel_type()`. The plan must either:
- Define and add a new relationship type (e.g., `HAS_ITEM`) to `VALID_REL_TYPES`.
- Or explicitly document that inventory is stored as a node property (the list of IDs) and not as graph edges.

### 2. graph.delete() Does Not Exist in the Codebase

Section 4.4, step 1 states: "Drop the entire FalkorDB graph using `graph.delete()`". There is no `graph.delete()` call anywhere in the codebase. The plan should specify the exact API call, including verification that it works with the async client, and whether it requires re-creating the GraphClient afterward.

### 3. Schema Re-creation After Graph Drop Has Unverified Assumptions

Section 4.4, step 2 calls `ensure_schema()` which does not exist. The actual function is `initialize_schema()` in `graph/schema.py`. After dropping the graph, the SchemaVersion node is gone, so it will try to run all migrations from v1 to v2. The plan should:
- Use the correct function name (`initialize_schema`, not `ensure_schema`).
- Confirm reconnection flow after graph deletion.
- Note that `initialize_schema` needs `vector_dimension` for v2 migration.

### 4. Concurrent Access During Import is Destructive

During the import window (seconds to minutes), any other operation will fail catastrophically. The plan does not address locking, active_scenes cleanup, or frontend handling of the "graph is empty" state. At minimum, the import endpoint should set a flag causing other graph-accessing endpoints to return 503.

### 5. Backup Deletes Existing Files Before Writing New Ones

Section 5.2, step 5: "Clear any existing `.md` files in the directory first." If the export crashes mid-write, the user's previous backup is already deleted. Safe approach: write to temp directory, then atomically swap.

## Significant Design Issues

### 6. Import Filename Convention Inconsistent with Existing Export

Existing `export_entities()` writes `{entity.id}.md`. The plan proposes `{type}_{id}.md`. This creates confusion. The plan should clarify whether old routes are deprecated, replaced, or left alongside.

### 7. Event and Scene Entities Are Partially Handled

The parser includes `Event` but not subclasses: `ChatMessage`, `JoinEvent`, `LeaveEvent`, `FastForwardEvent`. Scene.messages is a complex nested structure excluded from graph properties. The plan should explicitly state that scene messages are NOT part of this import/export.

### 8. Missing Relationship Type: Character Inventory Has No Graph Edge (duplicate of #1)

Character.inventory is a list field stored as a node property. There is no relationship type for inventory. The plan's relationship reconstruction for inventory is wrong if inventory stays as a property.

### 9. CONNECTS_TO Bidirectionality Creates Duplicate Edges

If Location A connects to B and B connects to A, the importer creates two directed edges. Existing queries use undirected match, so connected_locations(A) returns B twice. Must deduplicate or use MERGE.

## Moderate Issues

### 10. No Test Plan

The plan has no testing section.

### 11. No Progress Streaming

API endpoints are synchronous POST requests returning final state only. ImportProgress intermediate fields are meaningless.

### 12. force:true After Validation Creates TOCTOU Race

Files could change between validate and execute calls. Minor for single-user but should be documented.

### 13. Missing type Field Handling in Parser

Existing code defaults to "Character" when type is missing. Plan says missing type is an error. Breaking change should be documented.

### 14. Plan Says "Implement Fresh" Serialization But Should Not

Existing `entity_to_markdown()` already handles all types generically. Reimplementing creates maintenance burden and format drift risk.

### 15. Memory Nodes Are Not Addressed

Import drops entire graph, destroying all Memory nodes. Backup only exports Entity nodes. This silent data loss should be called out explicitly.

### 16. Entity Counts Verification Query

Post-import verification should use `MATCH (n:Entity)` not `MATCH (n)` to exclude SchemaVersion node.

### 17. API Response Type Ambiguity

ImportResponse is polymorphic. Need discriminator field. Existing schemas.py already has ImportResponse/ExportResponse classes - naming conflict.

### 18. Existing Routes Conflict

Old routes: `POST /v1/entities/import`, `POST /v1/entities/export`. New routes: `POST /v1/campaign/import`, `POST /v1/campaign/backup`. Having both is confusing.

## Minor Issues

### 19. File Naming Sanitization Underspecified
### 20. Entities Directory Non-Recursive Not Enforced (should log warning for subdirectories)
### 21. No Backup Confirmation (backup clears files without asking)
### 22. Dataclass vs. Pydantic Inconsistency (API models should be Pydantic BaseModel)

## Summary of Priorities

**Must fix:** Issues 1/8, 2, 3, 4, 5, 9, 15
**Should fix:** Issues 6, 7, 10, 17, 18, 22
