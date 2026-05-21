# entity-model: Domain class hierarchy

The world model is a small class tree rooted at `Entity`, plus a
`Campaign` container that holds and exposes every loaded entity.
Per-class invariants are split: behaviour and on-disk shape live here;
per-symbol docs (method args, raises, edge cases) live in pydoc on the
class.

`Entity.Model` is **the** canonical serialised format for every Entity
subclass. There are no parallel wire models — REST/WS hand back
`Entity.Model` instances and FE proxies hydrate from them directly.
Runtime-only fields (`Scene.messages`, listener lists, actor refs)
stay off the Model.

## entity-base: Entity

```python
class Entity:
    id: EntityId       # branded NewType[str]; never None
    name: str
    type: EntityType   # discriminator: CHARACTER | SCENE | ENTITY
    body: str          # markdown body; default annotation contribution

    def subscribe(self, listener: Listener) -> None: ...
    def unsubscribe(self, listener: Listener) -> None: ...
    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...  # default no-op
    def annotate_context(self, ctx: MessageContext) -> None: ...

    @classmethod
    def deserialize(cls, model: Entity.Model, campaign: Campaign) -> Self: ...

    class Model(BaseModel): ...   # subclass-specific Pydantic wire+disk model
```

- entity-hashable-by-id: `__hash__ = hash(self.id)`; `__eq__` compares
  ids only. `id` is in `_GHOST_SAFE` so ghost entities hash/compare
  without resolving.
- entity-ghost: An unresolved entity holds only its `id`; accessing
  any other field raises `UnresolvedEntityError` until the campaign
  hydrates it. Forward references during `Campaign.load` use the
  ghost pattern; no topological sort needed.
- entity-listener: Every Entity is a `Listener` — the default `notify`
  is a no-op. Subclasses override.
- entity-annotate-context: Virtual method. Default writes
  `ctx.annotations[self] = self.body`. Subclasses recurse into related
  entities. `ctx.annotations` is keyed by entity hash so multiple
  paths to the same entity collapse to one chunk.
- entity-deserialize: Uniform `(model, campaign) -> Self` contract on
  the Entity base. Subclasses override to resolve cross-references
  via `campaign.get(other_id)` / `campaign.ghost(other_id, type)`.
- entity-model-canonical: The nested `Entity.Model` is the single
  serialisation format — used for on-disk frontmatter, REST response
  bodies, and WS frame payloads alike. No `*Response` classes; no
  separate wire schema.
- entity-actions: Subclasses expose RPC-callable mutator methods via
  the `@action` decorator (per [[backend]]). Calling such a method
  in-process runs it directly; calling it on a FE proxy serialises
  to an `EntityAction` frame (per [[events]]).
- entity-on-disk: Generic entities serialise as self-contained
  frontmatter markdown documents. Complex subclasses (Scene) own
  their directory layout. Filename collisions resolve by `-index`
  suffix.
- .implemented-by: Entity

## entity-character: Character

```python
class Character(Entity):
    owner: Literal["user", "stub", "npc"]
    _campaign: Campaign           # set at __init__; used to resolve refs
    _actor: Actor                 # shared singleton via App.get_actor(owner)

    def notify(self, event) -> Awaitable[None]: ...   # spawns actor.respond
    def annotate_context(self, ctx) -> None: ...      # body + scene recurse

    @action
    async def speak(self, body: str) -> None: ...     # construct Message + scene.append
```

- character-init-binds-actor: `Character.__init__` resolves the Actor
  singleton for `self.owner` via `App.get_actor(owner)` and stores it
  as `self._actor`. See [[actors]] for the actor hierarchy.
- character-listener: On `EntityChanged` from a subscribed scene, if
  the new message's sender is NOT `self`, spawn an async task that
  calls `self._actor.respond(message, self, scene)`. A non-None
  reply text is delivered via `self.speak(text)`, which runs the
  normal `EntityChanged` cycle.
- character-campaign-ref: Holds `self._campaign` to resolve related
  entities (today: the scene reached via `MessageContext`; future:
  memories, items).
- character-annotate-context: Calls `super().annotate_context(ctx)`
  (writes `self.body`), then recurses into `ctx.scene` so an NPC's
  prompt includes both *who I am* and *where I am* via one
  polymorphic call.
- character-speak: `@action`-callable. Constructs
  `Message(sender=self, body=body)` and calls
  `self._current_scene.append(message)`. The single mutator for
  "this character says something" — unifies user input (FE-issued
  `EntityAction`) and NPC response (in-process call from
  `notify`).
- .implemented-by: Character

## entity-scene: Scene

```python
class Scene(Entity):                  # abstract
    characters: list[Character]
    user_characters: list[Character]  # has_human_actor() == True subset
    messages: list[Message]           # runtime-only; not in Scene.Model

    def append(self, msg: Message) -> int: ...    # mutate + emit
    def serialize_message(self, i: int) -> Message.Model: ...
    async def idle(self, timeout: float = 5.0) -> None: ...

class SimpleScene(Scene):             # concrete: exactly two characters
    def __init__(...): ...            # validates 1 user + 1 non-user
```

- scene-pure-data: Scene is pure data + event source. `append` is the
  single internal mutation API — no `dispatch`, no `_respond`
  orchestration. The composite `(scene.id, index)` is the message's
  wire identity, assembled by `serialize_message`.
- scene-init-subscribes-characters: `SimpleScene.__init__` subscribes
  every character to itself, wiring the listener-driven response
  cycle automatically.
- scene-on-disk: `Scene.Model` carries `characters: list[EntityId]`
  plus inherited Entity fields. Messages are runtime-only; on `App`
  reload they're wiped (per [[backend]] `backend-reload`). Save-game
  persistence adds a messages sidecar later.
- scene-idle: `await scene.idle()` waits for all background tasks
  spawned in response to recent emissions to settle. Lives on Scene
  (not Entity) because Scene is where mutation cascades actually
  happen; test-only primitive, production never calls it.
- .implemented-by: Scene, SimpleScene

## entity-message: Message

```python
@dataclass
class Message:
    sender: Character
    body: str

    class Model(BaseModel):
        scene_id: EntityId
        index: int
        sender_id: EntityId
        body: str
```

- message-wire-identity: `(scene_id, index)` is the composite wire
  identity. The bare `Message` carries the sender object; the
  `Model` is built by `Scene.serialize_message` at the wire boundary.
- message-not-entity: Messages are NOT Entities. They have no
  `EntityId`, no individual subscribe. They live as
  `Scene.messages: list[Message]` — a collection attribute on Scene
  (per [[events]] `events-attribute-deltas`). Per-message operations
  beyond append (edit/react/redact, if/when added) are exposed as
  `@action` methods on Scene — Scene is the entity-level addressable
  container. Promotion of Message to an Entity is deferred until a
  concrete need exists; today's domain treats messages as
  append-only chat history.
- message-dataflow: Every message flows through `scene.append(message)`,
  always called from `Character.speak`. `append` records, assigns
  the index, fires `EntityChanged` carrying the appended-count delta
  (per [[events]] `events-attribute-deltas`). Reactions cascade via
  listener fanout per [[events]] (`events-dataflow`).
- .implemented-by: Message, Message.Model, Scene.append,
  Scene.serialize_message

## entity-context: MessageContext

```python
@dataclass
class MessageContext:
    message: Message
    scene: Entity                           # the scene message landed in
    annotations: dict[Entity, str] = ...    # keyed by entity (hash)
```

- message-context-carrier: Carried through `annotate_context`
  recursion. Scoped to one triggering message; entities contribute
  chunks to `annotations`. Consumers (NpcActor) format and join the
  values into a system prompt.
- .implemented-by: MessageContext

## entity-campaign: Campaign

```python
class Campaign:
    name: str
    default_scene_id: EntityId | None      # client navigation hint

    # Architectural surface (mirrored on the FE)
    def get(self, entity_id: EntityId) -> Entity: ...
    def add(self, entity: Entity) -> None: ...
    def delete(self, entity_id: EntityId) -> None: ...
    def subscribe(self, entity_ids: list[EntityId]) -> None: ...

    # Load-time helper (see Campaign.load)
    def ghost(self, entity_id: EntityId, type_: EntityType) -> Entity: ...

    # Lifecycle
    @classmethod
    def load(cls, path: Path) -> Campaign: ...

    class Model(BaseModel):                # canonical serialised form
        name: str
        default_scene_id: EntityId | None
```

- campaign-container: Campaign holds every loaded entity directly.
  `get` resolves by id (returning a ghost if not yet loaded); `add`
  registers (hydrating any matching ghost in place); `delete`
  removes. There is no separate `EntityFactory` class today —
  Campaign IS the container.
- campaign-subscribe: Cross-wire projection-facing API. The caller
  identity (which connection) is implicit in the caller — on the WS
  surface it's the `WsConnection`; in-process subscribers use the
  per-entity `entity.subscribe(listener)` primitive directly.
- campaign-load: Single forward pass using the ghost pattern. Reads
  `config.yaml`, walks the tree, classifies each entity by location,
  parses YAML frontmatter + body into `Entity.Model`, calls
  `EntityClass.deserialize(model, self)`, then `self.add(entity)`.
  Forward references hydrate when their target is later `add`-ed.
  Ghosts that remain unresolved at the end log a warning and stay
  in place; access raises `UnresolvedEntityError`.
- campaign-model: `Campaign.Model` is the canonical serialised form
  (carries `name` + `default_scene_id`). Same one-model rule as
  Entity: no parallel `CampaignResponse`.
- .implemented-by: Campaign, Campaign.load

## entity-campaign-tree: On-disk layout

```
<sidestage_dir>/campaigns/<campaign_name>/
├── config.yaml                # Campaign.Model fields
├── characters/<id>/CHARACTER.md
├── scenes/<id>/SCENE.md
├── locations/<id>.md
└── entities/<id>.md           # generic
```

`config.yaml` serialises a `Campaign.Model`. The example above includes
aspirational subdirs (per-character `inventory/`, `attributes.yaml`,
`locations/`) not yet implemented; generic entities live in
`entities/`.
