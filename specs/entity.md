# entity: The base object of Sidestage

Sidestage represents its entire world as Entities. All entities belong to a
Campaign and are managed by an `EntityFactory`. Every Entity is BOTH a
potential emitter AND a potential listener (per `events.md`).

Entities support lazy loading via the ghost pattern: an unresolved entity
holds only its `id`; accessing any other field raises `UnresolvedEntityError`
until the factory hydrates it.

## entity-disk-format: Serialization format

- entity-frontmatter: Generic entities are serialized as self-contained
  frontmatter documents; the `body` attribute is stored in the markdown body.
- entity-filename: The filename SHOULD represent the name of the entity.
  In case of collision within a directory the name is suffixed with `-index`.
- entity-directory: Some complex entity subclasses define their own
  directory structure; the directory name follows the same convention.
