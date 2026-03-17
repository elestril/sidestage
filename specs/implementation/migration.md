# migration

Implements: [sidestage#principle-markdown-first](/specs/sidestage.md#principle-markdown-first)

## Overview {#overview}

The system supports exporting and importing campaign data to and from a
structured markdown directory tree. This provides a universal format for
storing campaign contents outside of the database, enabling version control,
external editing, and portability. The system provides roundtrip fidelity —
all entity data, relationships, memories, and chat logs are preserved across
export/import cycles.

## Two-Phase Import {#two-phase-import}

### Validate Phase {#validate-phase}

The validate phase MUST parse the `markdown/` directory tree and return a
report including:

- Total entities and memories found.
- Entity counts by type.
- Errors (fatal issues that prevent import).
- Warnings (non-fatal issues, e.g., missing cross-references).

<a id="validation-warning-format"></a>
Each warning MUST include: `entity_id`, `file_path`, `severity`, and
`message`.

### Execute Phase {#execute-phase}

<a id="import-graph-drop"></a>
The execute phase MUST drop and recreate the graph before importing.

The execute phase MUST import:
- All entities with their properties.
- All relationships (edges).
- All memories.
- All chat logs.

<a id="import-force"></a>
The `force` flag MAY skip validation on execute.

### Health Gating {#import-health-gating}

<a id="import-degraded-409"></a>
Import MUST return `409 Conflict` if campaign health is DEGRADED (another
operation is in progress).

## Atomic Backup {#atomic-backup}

### Backup Process {#backup-process}

<a id="backup-atomic-swap"></a>
Backup MUST use atomic swap to prevent partial writes.

The backup MUST export:
- All entities with their properties and relationships.
- All memories.
- All chat logs.

<a id="backup-status-json"></a>
A `status.json` file MUST be written with backup metadata (timestamp, counts,
version).

### Health Gating {#backup-health-gating}

<a id="backup-degraded-409"></a>
Backup MUST return `409 Conflict` if campaign health is DEGRADED.

## Roundtrip Fidelity {#roundtrip-fidelity}

<a id="roundtrip-preservation"></a>
The markdown format MUST preserve all entity data, relationships, memories, and
chat logs, enabling full backup/restore cycles.

## Markdown Directory Layout {#directory-layout}

The `markdown/` directory MUST follow this structure:

```
markdown/
├── status.json
├── characters/
│   ├── Character_Name.md
│   └── Character_Name.d/
│       └── mem_id.md
├── locations/
│   └── Location_Name.md
├── items/
│   └── Item_Name.md
├── scenes/
│   ├── Scene_Name.md
│   └── Scene_Name.d/
│       └── chatlog.log
└── events/
    └── Event_Name.md
```

### Directory Organization {#dir-organization}

<a id="dir-by-type"></a>
Entities MUST be organized into subdirectories by type: `characters/`,
`locations/`, `items/`, `scenes/`, `events/`.

<a id="companion-directories"></a>
Characters with memories MUST have a companion directory named
`<Character_Name>.d/` alongside the character file. Scenes with chat logs
MUST have a companion directory named `<Scene_Name>.d/`.

### Memory Files {#dir-memory-files}

Memory files MUST reside in the companion directory of their owning character.
Only characters can own memories.
See [memory#memory-file-format](/specs/implementation/memory.md#memory-file-format) for the file
format.

### Chat Log Files {#dir-chatlog-files}

Chat log files MUST be named `chatlog.log` and reside in the scene's companion
directory. See [scenes#chatlog-format](/specs/implementation/scenes.md#chatlog-format) for the file
format.

### Status File {#dir-status-file}

<a id="status-json-contents"></a>
The `status.json` file MUST contain backup metadata including timestamp,
entity/memory counts, and version.

## Cross-Reference Validation {#cross-ref-validation}

<a id="cross-ref-check"></a>
During validation, the system MUST check for cross-reference integrity — e.g.,
a character's `location_id` referencing a location that exists in the import
set. Missing references MUST be reported as warnings.
