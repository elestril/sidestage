# TDD Plan: Campaign Import & Backup

Test stubs mirroring each section of `claude-plan.md`. Tests should be written BEFORE implementing each section.

**Testing framework:** pytest with pytest-anyio for async tests. Fixtures use `tmp_path` for isolation. FalkorDB integration tests require a running FalkorDB instance.

**Test location:** `tests/unit/test_migration_*.py` for unit tests, `tests/unit/test_migration_integration.py` for full roundtrip.

---

## 2. Canonical Data Representation (serialization.py)

### Unit Tests: `tests/unit/test_migration_serialization.py`

```python
# Test: entity_to_frontmatter_dict returns (dict, body) for Character with all fields
# Test: entity_to_frontmatter_dict returns (dict, body) for Location with connected_locations
# Test: entity_to_frontmatter_dict returns (dict, body) for Item (minimal fields)
# Test: entity_to_frontmatter_dict returns (dict, body) for Scene (excludes messages from frontmatter)
# Test: entity_to_frontmatter_dict returns (dict, body) for Event subtypes (ChatMessage, JoinEvent)
# Test: entity_to_frontmatter_dict dict is identical to model_dump() + type, minus body
# Test: entity_to_frontmatter_dict field ordering is deterministic (name, id, type first)

# Test: frontmatter_dict_to_entity reconstructs Character from dict + body
# Test: frontmatter_dict_to_entity reconstructs Location with connected_locations
# Test: frontmatter_dict_to_entity infers type from subdirectory when type field missing
# Test: frontmatter_dict_to_entity raises on unknown type
# Test: frontmatter_dict_to_entity raises on missing required fields (id, name)

# Test: memory_to_frontmatter_dict returns (dict, content) excluding embedding
# Test: memory_to_frontmatter_dict includes all Memory fields except embedding and content
# Test: frontmatter_dict_to_memory reconstructs Memory from dict + body
# Test: frontmatter_dict_to_memory roundtrip preserves all fields

# Test: full roundtrip entity -> frontmatter_dict -> YAML -> parse -> entity (all types)
# Test: full roundtrip memory -> frontmatter_dict -> YAML -> parse -> memory
```

## 3. Directory Structure

### Unit Tests: `tests/unit/test_migration_directory.py`

```python
# Test: sanitize_filename replaces special chars with underscore
# Test: sanitize_filename collapses multiple underscores
# Test: sanitize_filename preserves hyphens and underscores
# Test: sanitize_filename handles empty string

# Test: entity_type_to_subdir maps Character -> "characters", Location -> "locations", etc.
# Test: entity_type_to_subdir maps Event subtypes to "events"

# Test: resolve_filename appends _2, _3 on collision
```

## 5. Data Models (models.py)

### Unit Tests: `tests/unit/test_migration_models.py`

```python
# Test: MigrationValidationIssue accepts error and warning severity
# Test: MigrationValidationReport valid=True when no errors
# Test: MigrationValidationReport valid=False when errors present
# Test: MigrationImportResult serializes to JSON correctly
# Test: MigrationBackupResult serializes to JSON correctly
# Test: BackupStatus includes all required fields
```

## 6. Import Campaign

### 6.2 Parser: `tests/unit/test_migration_parser.py`

```python
# Test: parse_directory reads all entity types from correct subdirectories
# Test: parse_directory reads memory files from .d/ companion directories
# Test: parse_directory reads chatlog.log from scene .d/ directories
# Test: parse_directory associates memories with parent entity via .d/ naming
# Test: parse_directory infers type from subdirectory when type field missing in frontmatter
# Test: parse_directory warns on .d/ without parent .md (orphaned memories)
# Test: parse_directory warns on chatlog.log in non-scene .d/
# Test: parse_directory handles malformed YAML gracefully (error in ParseResult)
# Test: parse_directory handles missing frontmatter (error in ParseResult)
# Test: parse_directory warns on duplicate entity IDs (last-wins)
# Test: parse_directory ignores Scene.messages in frontmatter
# Test: parse_directory handles empty directory tree (no entities)
# Test: parse_directory handles missing type subdirectories gracefully
```

### 6.3 Validator: `tests/unit/test_migration_validator.py`

```python
# Test: validates successfully with correct references
# Test: detects duplicate entity IDs
# Test: detects Character.location_id referencing nonexistent Location
# Test: detects Character.inventory referencing nonexistent Item
# Test: detects Location.connected_locations referencing nonexistent Location
# Test: detects Scene.location_id referencing nonexistent Location
# Test: detects Event.scene_id referencing nonexistent Scene
# Test: detects missing required entity fields (id, name)
# Test: detects Memory.owner_id referencing nonexistent entity
# Test: detects Memory.target_id referencing nonexistent entity
# Test: allows Memory.owner_id = null
# Test: detects invalid memory_type
# Test: detects missing required memory fields (id, content, memory_type, target_id)
# Test: always includes data-loss warning
# Test: distinguishes errors from warnings
```

### 6.4 Importer: `tests/unit/test_migration_importer.py`

```python
# Test: sets campaign health to DEGRADED before import
# Test: restores campaign health to HEALTHY after successful import
# Test: restores campaign health to HEALTHY after failed import
# Test: inserts all entities via create_entity
# Test: creates LOCATED_IN edges for characters with location_id
# Test: creates CONNECTS_TO edges (deduplicated for bidirectional pairs)
# Test: creates AT_LOCATION edges for scenes
# Test: creates HAS_EVENT edges for events
# Test: inserts memories via upsert_memory with HAS_MEMORY + ABOUT edges
# Test: skips embedding generation during import
# Test: restores chat logs via storage
# Test: verifies entity counts after import
# Test: clears active scenes after import
# Test: broadcasts entities_updated after import
```

## 7. Backup Campaign

### Exporter: `tests/unit/test_migration_exporter.py`

```python
# Test: queries all entities from FalkorDB
# Test: queries all memories from FalkorDB
# Test: retrieves chat logs from SQLite for scenes
# Test: writes entity files to correct type subdirectories
# Test: writes memory files to correct .d/ directories
# Test: writes chatlog.log to scene .d/ directories
# Test: creates .d/ only when entity has memories or chat logs
# Test: writes status.json with correct counts
# Test: atomic backup via temp dir swap (old files untouched on failure)
# Test: handles filename collisions with _2, _3 suffix
# Test: places memory in owner's .d/ when owner_id set
# Test: places memory in target's .d/ when owner_id is null
# Test: queries LOCATED_IN for character location_id in frontmatter
# Test: queries CONNECTS_TO for location connected_locations in frontmatter
```

## 9. FastAPI Route Integration

### Route Tests: `tests/unit/test_migration_routes.py`

```python
# Test: POST /v1/campaign/import with action=validate returns validation report
# Test: POST /v1/campaign/import with action=execute performs import
# Test: POST /v1/campaign/import returns 409 when health is DEGRADED
# Test: POST /v1/campaign/backup returns backup result
# Test: POST /v1/campaign/backup returns 409 when health is DEGRADED
```

## 10. Error Recovery

```python
# Test: parse failure reported in validation, import not attempted
# Test: graph drop failure restores health to HEALTHY
# Test: partial insertion restores health to HEALTHY and returns error counts
# Test: backup failure leaves old files untouched
# Test: status.json reflects previous state if backup fails
```

## 12. Test Campaign and Integration Tests

### Integration Tests: `tests/unit/test_migration_integration.py`

```python
# Test: full roundtrip - import test campaign, backup, compare
# Test: entity fidelity - JSON API dict matches frontmatter dict from disk
# Test: memory fidelity - all fields preserved through roundtrip
# Test: chat log fidelity - messages preserved with correct ordering
# Test: relationship integrity - LOCATED_IN, CONNECTS_TO (deduplicated), AT_LOCATION
# Test: validation errors - broken references detected
# Test: concurrency guard - health DEGRADED during import, 409 for concurrent requests, HEALTHY after
# Test: re-import from backup produces identical graph state
```
