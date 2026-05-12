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

## entity-hashable-by-id: Identity by EntityId

Entities are hashable so they can key the `MessageContext.annotations`
dict; identity is by `EntityId`.

- entity-hashable-by-id: `__hash__` returns `hash(self.id)`; `__eq__`
  compares `self.id` (and that `other` is an `Entity`).
- entity-hashable-by-id-ghost-safe: `id` is in `_GHOST_SAFE`, so ghost
  entities hash and compare correctly without resolving — required so
  that a ghost reached during a forward pass collapses with the loaded
  entity that hydrates it later.
- .implemented-by: Entity.__hash__, Entity.__eq__

## entity-message-context: Per-call accumulator for prompt context

`MessageContext` is the carrier passed through `annotate_context`
recursion. Scoped to the triggering message; entities add their
contributions to `annotations`.

```python
@dataclass
class MessageContext:
    message: Message
    annotations: dict[Entity, str] = field(default_factory=dict)
```

- entity-message-context: Folded into `entity.py` because Entity is its
  only producer. Grows naturally (budget, depth, requestor) when those
  become real concerns.
- entity-message-context-named-for-scope: Named for what it is scoped
  to (the triggering message), not what it contains. Entities are
  contributors — annotations live INSIDE the context, they don't own it.
- .implemented-by: MessageContext

## entity-annotate-context: Contributing to a prompt context

Every entity participates in prompts the same way: it adds a chunk of
text keyed by itself to a `MessageContext`. `NpcActor` calls
`character.annotate_context(ctx)` and joins `ctx.annotations.values()`
into the system prompt.

- entity-annotate-context: Virtual instance method.
  `annotate_context(ctx: MessageContext) -> None`. Default writes
  `ctx.annotations[self] = self.body`. Subclasses override to recurse
  into related entities (e.g. `Character` resolves the scene via
  factory and calls `scene.annotate_context(ctx)`).
- entity-annotate-context-idempotent: Multiple paths to the same entity
  collapse — `annotations` is keyed by entity (`__hash__` by id), so a
  scene reached twice appears once.
- entity-annotate-context-formatting: How annotations are joined,
  ordered, or section-headed is the consumer's job (`NpcActor`),
  NOT the entity's. Entities contribute labeled chunks; the consumer
  formats.
- .implemented-by: Entity.annotate_context
