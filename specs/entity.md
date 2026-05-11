# entity: The base object of Sidestage

Sidestage represents its entire world as Entities. All entities belong to a
Campaign and are managed by an EntityFactory. Entities support lazy loading
via the ghost pattern: an unresolved entity holds only its `id`; accessing
any other field raises `UnresolvedEntityError` until the factory hydrates it.

## entity-id: EntityId type

`EntityId` is the project-wide identifier type for entities. The `NewType`
declaration and its `entity-id-newtype` invariant live as a labeled comment
on the `EntityId` definition in `src/sidestage/entity.py` per
`spec-location-pydoc`.

## entity-impl: Entity class

The `Entity` class spec — class-level invariants, the inner `Entity.Model`
schema, the ghost-pattern attribute guard, and the `serialize` / `deserialize`
invariants — lives in pydoc on `src/sidestage/entity.py` per
`spec-location-pydoc`.

## entity-factory-impl: EntityFactory classes

The `EntityFactory` ABC and `DictEntityFactory` concrete implementation specs
— including their `get` / `add` / `ghost` invariants — live in pydoc on
`src/sidestage/entity.py` per `spec-location-pydoc`.

## entity-disk-format: Serialization format

- entity-frontmatter: Generic entities are serialized as self-contained
  frontmatter documents; the `body` attribute is stored in the markdown body.
- entity-filename: The filename SHOULD represent the name of the entity. In
  case of collision within a directory the name is suffixed with `-index`.
- entity-directory: Some complex entity subclasses define their own directory
  structure; the directory name follows the same entity-filename convention.

## Label index

Run `uv run pydoc-markdown`
to render the generated markdown view at `specs/generated/api.md`.

Labels defined in pydoc (for cross-reference from this and other markdown
specs):

- `entity-id-newtype` — labeled comment on `EntityId` (module-level NewType)
- `entity-class` — `Entity` class docstring
- `entity-ghost-safe`, `entity-ghost-unresolved` — `Entity.__getattribute__`
- `entity-model` — `Entity.Model` class docstring
- `entity-serialize-fields`, `entity-serialize-ghost-rejects` —
  `Entity.serialize`
- `entity-deserialize-returns`, `entity-deserialize-loaded` —
  `Entity.deserialize`
- `entity-factory` — `EntityFactory` ABC class docstring
- `entity-factory-get`, `entity-factory-add`, `entity-factory-ghost` —
  `EntityFactory` abstract methods
- `dict-entity-factory` — `DictEntityFactory` class docstring
- `dict-factory-get`, `dict-factory-add`, `dict-factory-ghost` —
  `DictEntityFactory` methods
