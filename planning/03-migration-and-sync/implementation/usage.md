# Usage Guide: Campaign Migration & Sync

## Quick Start

### Backup Campaign to Markdown

```bash
curl -X POST http://localhost:8000/v1/campaign/backup
```

Writes all entities, memories, and chat logs from FalkorDB/SQLite to `~/.sidestage/<campaign>/markdown/`.

### Import Campaign from Markdown

Two-phase flow:

```bash
# Phase 1: Validate
curl -X POST http://localhost:8000/v1/campaign/import \
  -H "Content-Type: application/json" \
  -d '{"action": "validate"}'

# Phase 2: Execute (if validation passes)
curl -X POST http://localhost:8000/v1/campaign/import \
  -H "Content-Type: application/json" \
  -d '{"action": "execute"}'

# Force import even with warnings
curl -X POST http://localhost:8000/v1/campaign/import \
  -H "Content-Type: application/json" \
  -d '{"action": "execute", "force": true}'
```

### Frontend

The EntityBrowser has two new buttons:
- **Import Campaign** (purple) — Two-phase: validates first, shows confirmation with entity counts, then executes
- **Backup Campaign** (purple) — One-click backup with result summary

Both return 409 if another operation is in progress.

## API Reference

### POST /v1/campaign/import

Request body: `MigrationImportRequest`
- `action`: `"validate"` or `"execute"`
- `force`: `false` (default) — set `true` to bypass validation warnings

Response: `MigrationImportResponse`
- `action`: echoed from request
- `validation`: `MigrationValidationReport` (always present)
- `result`: `MigrationImportResult` (only on execute)

### POST /v1/campaign/backup

No request body required.

Response: `MigrationBackupResult`
- `phase`: `"complete"` or `"failed"`
- `written_entities`, `written_memories`, `written_chatlogs`: counts
- `errors`: list of error messages

## Markdown Directory Layout

```
markdown/
├── characters/
│   ├── Character_Name.md
│   └── Character_Name.d/
│       └── mem_id.md
├── locations/
│   ├── Location_Name.md
│   └── Location_Name.d/
│       └── mem_id.md
├── items/
│   └── Item_Name.md
├── scenes/
│   ├── Scene_Name.md
│   └── Scene_Name.d/
│       ├── mem_id.md
│       └── chatlog.log
└── events/
    └── Event_Name.md
```

## Pipeline Modules

| Module | Function | Description |
|--------|----------|-------------|
| `migration/parser.py` | `parse_directory(path)` | Parse markdown tree → `ParseResult` |
| `migration/validator.py` | `validate_parse_result(pr)` | Validate references → `MigrationValidationReport` |
| `migration/importer.py` | `import_campaign(campaign, pr, ...)` | Drop graph, insert all data |
| `migration/exporter.py` | `export_campaign(campaign)` | Query graph, write markdown tree |
| `migration/serialization.py` | `entity_to_frontmatter_dict()` etc. | Canonical frontmatter format |
| `migration/models.py` | Pydantic models | Request/response/result schemas |
