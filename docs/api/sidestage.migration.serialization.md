# `sidestage.migration.serialization`

Canonical frontmatter serialization for campaign migration.

Converts entities and memories to/from YAML frontmatter dict + markdown body
format. Also provides filename sanitization and type-to-subdirectory mapping.

## Functions

### `entity_to_frontmatter_dict(entity: Entity) -> tuple[dict[str, Any], str]`

Convert entity to (frontmatter_dict, body_markdown).

### `entity_type_to_subdir(type_name: str) -> str`

Map an entity type name to its directory name.

### `frontmatter_dict_to_entity(data: dict[str, Any], body: str, type_hint: str | None = None) -> Entity`

Reconstruct entity from frontmatter dict + body.

### `frontmatter_dict_to_memory(data: dict[str, Any], body: str) -> Memory`

Reconstruct memory from frontmatter dict + body.

### `memory_to_frontmatter_dict(memory: Memory) -> tuple[dict[str, Any], str]`

Convert memory to (frontmatter_dict, content_body).

### `resolve_filename(stem: str, used: set[str]) -> str`

Resolve filename collisions by appending _2, _3, etc.

### `sanitize_filename(name: str) -> str`

Sanitize a string for use as a filename.
