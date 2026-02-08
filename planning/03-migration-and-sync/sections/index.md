<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-data-models
section-02-serialization
section-03-test-campaign
section-04-parser
section-05-validator
section-06-exporter
section-07-importer
section-08-routes-and-frontend
section-09-integration-tests
END_MANIFEST -->

# Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-data-models | - | 02, 04, 05, 06, 07 | Yes |
| section-02-serialization | 01 | 03, 04, 06, 07 | No |
| section-03-test-campaign | 02 | 09 | Yes |
| section-04-parser | 01, 02 | 05, 07 | Yes |
| section-05-validator | 01, 04 | 07 | Yes |
| section-06-exporter | 01, 02 | 09 | Yes |
| section-07-importer | 01, 02, 04, 05 | 08, 09 | No |
| section-08-routes-and-frontend | 07 | 09 | No |
| section-09-integration-tests | 03, 06, 07, 08 | - | No |

## Execution Order

1. section-01-data-models (no dependencies)
2. section-02-serialization (after 01)
3. section-03-test-campaign, section-04-parser, section-05-validator, section-06-exporter (parallel after 02)
4. section-07-importer (after 04, 05)
5. section-08-routes-and-frontend (after 07)
6. section-09-integration-tests (final)

## Section Summaries

### section-01-data-models
Create `migration/models.py` with all Pydantic data models: `MigrationValidationIssue`, `MigrationValidationReport`, `MigrationImportResult`, `MigrationBackupResult`, `BackupStatus`, `ParseResult`, and API request/response models. Also create `migration/__init__.py`.

### section-02-serialization
Create `migration/serialization.py` with canonical frontmatter serialization functions: `entity_to_frontmatter_dict()`, `frontmatter_dict_to_entity()`, `memory_to_frontmatter_dict()`, `frontmatter_dict_to_memory()`. Also filename sanitization and type-to-subdirectory mapping utilities. Unit tests for roundtrip fidelity.

### section-03-test-campaign
Create `data/test_campaign/markdown/` with representative entity and memory markdown files: 2 characters, 3 locations (triangle connectivity), 2 items, 2 scenes (one with chatlog), 1 event, and memories of all types. This serves as both documentation and test fixtures.

### section-04-parser
Create `migration/parser.py` that reads the `markdown/` directory tree, parses entity and memory files using the canonical serialization functions, associates memories with parent entities via `.d/` naming, and handles chat logs. Unit tests for all parsing edge cases.

### section-05-validator
Create `migration/validator.py` with referential integrity checks: ID uniqueness, location/inventory/scene references, memory owner/target references, required fields. Returns `MigrationValidationReport`. Unit tests for each check type.

### section-06-exporter
Create `migration/exporter.py` that reads all entities and memories from FalkorDB, chat logs from SQLite, and writes the `markdown/` directory tree with atomic swap. Writes `status.json`. Unit tests for directory layout and atomicity.

### section-07-importer
Create `migration/importer.py` that orchestrates: set health DEGRADED, drop graph, recreate schema, insert entities, create relationships (with CONNECTS_TO deduplication), insert memories, restore chat logs, verify counts, restore health HEALTHY. Unit tests for concurrency guard and entity insertion.

### section-08-routes-and-frontend
Add `POST /v1/campaign/import` and `POST /v1/campaign/backup` endpoints to `orchestrator.py`. Two-phase import (validate then execute). 409 when health DEGRADED. Frontend buttons for import/backup. WebSocket broadcast after operations.

### section-09-integration-tests
Full roundtrip integration tests using the test campaign fixture: import -> verify graph -> backup -> compare. Entity/memory/chatlog fidelity tests. Relationship integrity tests. Concurrency guard tests. Uses `tmp_path` fixture, copies from `data/test_campaign/`.
