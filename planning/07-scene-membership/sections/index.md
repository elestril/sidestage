<!-- PROJECT_CONFIG
runtime: python-uv
test_command: uv run pytest
END_PROJECT_CONFIG -->

<!-- SECTION_MANIFEST
section-01-graph-query
section-02-rest-api
section-03-seeding-import-export
section-04-frontend
section-05-docs
END_MANIFEST -->

# Track 07: Scene Membership — Implementation Sections Index

## Dependency Graph

| Section | Depends On | Blocks | Parallelizable |
|---------|------------|--------|----------------|
| section-01-graph-query | - | 02, 03, 04, 05 | No (foundation) |
| section-02-rest-api | 01 | 03, 04, 05 | No |
| section-03-seeding-import-export | 02 | 05 | Yes (parallel with 04) |
| section-04-frontend | 02 | 05 | Yes (parallel with 03) |
| section-05-docs | 01-04 | - | No (final) |

## Execution Order

1. section-01-graph-query (foundation — query + scene fix)
2. section-02-rest-api (REST endpoints + MCP tools)
3. section-03-seeding-import-export, section-04-frontend (parallel after 02)
4. section-05-docs (final — documentation + dev campaign fix)
