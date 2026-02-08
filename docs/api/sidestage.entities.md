# `sidestage.entities`

## Functions

### `entity_to_markdown(entity: Entity) -> str`

Serializes an Entity to a standardized Markdown format with YAML frontmatter.

### `markdown_to_entity(content: str, override_id: str | None = None) -> Entity`

Parses a Markdown string with YAML frontmatter into an Entity object.
If override_id is provided, it is used as the entity ID, overriding any ID in the frontmatter.
