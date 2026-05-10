# entity: The base object of Sidestage

Sidestage represents its entire world as Entities. All entities belong to a
Campaign and are managed by an EntityFactory. Entities support lazy loading
via the ghost pattern: an unresolved entity holds only its `id`; accessing
any other field raises `UnresolvedEntityError` until the factory hydrates it.

## entity-id: EntityId type

`EntityId = NewType('EntityId', str)`
- entity-id-newtype: All entity references use `EntityId` rather than bare `str`, so the type checker distinguishes ids from arbitrary strings.

## entity-impl: Entity class

### entity-class: Entity

`id: EntityId`
`name: str`
`type: EntityType`
`body: str`
`_loaded: bool`

`__getattribute__(self, name: str)`
- entity-ghost-safe: `id` and `_loaded` are accessible on unresolved entities.
- entity-ghost-unresolved: Accessing any other field raises `UnresolvedEntityError` if `_loaded` is False.

### entity-model: Entity.Model

Inner Pydantic model defining the on-disk / on-wire schema for an Entity.
Subclasses define their own `Model(Entity.Model)` adding subclass-specific
fields.

`id: EntityId`
`name: str`
`type: EntityType`
`body: str`

`serialize(self) -> Model`
- entity-serialize-fields: Returns `self.Model` populated from this entity's public fields.
- entity-serialize-ghost-rejects: Raises `UnresolvedEntityError` if called on an unresolved ghost.

`deserialize(cls, model: Model) -> Self` *(classmethod)*
- entity-deserialize-returns: Returns an instance of `cls` (not `Entity`) populated from `model`.
- entity-deserialize-loaded: Sets `_loaded = True` on the returned instance.

## entity-factory-impl: EntityFactory classes

### entity-factory: EntityFactory *(abstract)*

`get(self, id: str) -> Optional[Entity]`
- entity-factory-get: Returns the entity for the given id, or None if unknown.

`add(self, entity: Entity) -> None`
- entity-factory-add: Registers a hydrated entity; if a ghost with the same id exists, hydrates it in place.

`ghost(self, id: str, type: EntityType) -> Entity`
- entity-factory-ghost: Returns an unresolved ghost entity; creates and registers one if not yet known.

### dict-entity-factory: DictEntityFactory(EntityFactory)

Backed by `dict[str, Entity]`. Used at load time.

`get(self, id: str) -> Optional[Entity]`
- dict-factory-get: Returns entity from the dict, or None if not found.

`add(self, entity: Entity) -> None`
- dict-factory-add: Stores entity in the dict, sets `_loaded = True`; hydrates existing ghost if present.

`ghost(self, id: str, type: EntityType) -> Entity`
- dict-factory-ghost: Creates an unresolved Entity with `_loaded = False` and stores it.

## entity-disk-format: Serialization format

- entity-frontmatter: Generic entities are serialized as self-contained
  frontmatter documents; the `body` attribute is stored in the markdown body.
- entity-filename: The filename SHOULD represent the name of the entity. In
  case of collision within a directory the name is suffixed with `-index`.
- entity-directory: Some complex entity subclasses define their own directory
  structure; the directory name follows the same entity-filename convention.
