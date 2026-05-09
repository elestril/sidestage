# Entity: The base object of Sidestage

Sidestage represents it's entire world as Entities.

All entities belong to a [[campaign]] and have the following attributes:

```python
- id: str         # A campaign-wide unique id.
- name: str       # A name (not necessrily unique)
- type: enum      # They type of entity
- body: str       # A potentially long markdown description of the entity.
```

## entity-disk-format: Serialization format

- entity-frontmatter: Generic entities are serialized as self contained
  frontmatter document, the `body` attribute is stored in the markdown body.
- entity-filename: The filename SHOULD be chosen to represent the name of the
  entity. In case of collision within a directory the name should be suffixed
  with `-index`.
- entity-directory: Some complex entity subclasses define their own directory
  structure. In this case the directory name follows the same entity-filename
  convention.
