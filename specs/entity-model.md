# entity-model: Domain class hierarchy

The world model is a small class tree rooted at `Entity`, plus a
`Campaign` container that holds and exposes every loaded entity.
Per-class invariants are split: behaviour and on-disk shape live here;
per-symbol docs (method args, raises, edge cases) live in pydoc on the
class.

`Entity.Model` is **the** canonical serialised format for every Entity
subclass. There are no parallel wire models — REST/WS hand back
`Entity.Model` instances and FE proxies hydrate from them directly.
Runtime-only state that belongs to the Entity but not its persisted
shape (listener list, bound actor, pending tasks) lives as a private
attribute on the Entity instance, not on the Model.

## entity-base: Entity

```python
class Entity:
    def __init__(self, model: Entity.Model, campaign: Campaign): ...

    @property
    def model(self) -> Entity.Model: ...                       # public Model accessor

    def __getattr__(self, name): ...                           # reads forward to _model
    def __setattr__(self, name, value): ...                    # writes go through _model
                                                                # + auto-emit on change

    def subscribe(self, listener: Listener) -> None: ...
    def unsubscribe(self, listener: Listener) -> None: ...
    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...  # default no-op
    def annotate_context(self, ctx: MessageContext) -> None: ...

    class Model(BaseModel):   # subclass-specific Pydantic wire+disk model
        id: EntityId
        name: str
        type: EntityType
        body: str
```

- entity-model-wraps: An Entity instance wraps its `Model` as
  `self._model`. The `model` property exposes it publicly. Reads
  forward to the model via `__getattr__`; writes to Model fields
  go through `__setattr__` and auto-emit `EntityChanged` on a
  value change. Non-Model attributes (`_listeners`, `_actor`,
  `_pending_tasks`, ...) are set directly on the instance. The
  discriminator is `name in model.model_fields` — not a naming
  convention.
- entity-hashable-by-id: `__hash__ = hash(self.id)`; `__eq__`
  compares ids only.
- entity-listener: Every Entity is a `Listener` — the default
  `notify` is a no-op. Subclasses override.
- entity-annotate-context: Virtual method. Default writes
  `ctx.annotations[self] = self.body`. Subclasses recurse into
  related entities. `ctx.annotations` is keyed by entity hash so
  multiple paths to the same entity collapse to one chunk.
- entity-construction: A single `Entity(model, campaign)` call is
  the canonical construction path — used by both load and runtime
  creation. No separate `deserialize` classmethod, no two-phase
  hook ladder. Subclass `__init__`s call `super().__init__(model,
  campaign)` and then handle their own subclass-specific runtime
  state (e.g. `Character._actor` binding).
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

## entity-list-attribute: EntityList collection attributes

```python
class EntityList[T](list[T]):
    """Owned mutable collection. Every mutator emits ListDelta on
    the owning Entity."""

    def __init__(self, owner: Entity, attr: str): ...

    def append(self, item: T) -> None: ...
    def extend(self, items: Iterable[T]) -> None: ...
    def insert(self, i: int, item: T) -> None: ...
    def pop(self, i: int = -1) -> T: ...
    def remove(self, item: T) -> None: ...
    def clear(self) -> None: ...
    def __setitem__(self, i: int, item: T) -> None: ...
    def __delitem__(self, i: int) -> None: ...
```

A Model field declared as `list[X]` is wrapped in an `EntityList[X]`
at construction. Mutators emit `EntityChanged(entity=owner,
attributes=[attr], deltas={attr: ListDelta(...)})` automatically — no
manual emit in `@action` methods or anywhere else (per [[events]]
`events-attribute-deltas`).

- entity-list-attribute-mechanism: At `Entity.__init__`, each
  registered list field is replaced in place: a fresh `EntityList`
  is constructed with `(self, attr_name)`, initial items extended
  from the Model's value (bypassing emit), and assigned back. The
  list IS the field; later reads see the EntityList.
- entity-list-attribute-reassignment: Whole-list reassignment
  (`entity.attr = [...]`) routes through `Entity.__setattr__` and
  re-wraps the new value in a fresh `EntityList` so the contract
  "this attribute is always an EntityList" holds.
- entity-list-attribute-no-subclass: Lists that need per-item
  processing on add (e.g. ordered timelines that timestamp items)
  subclass `EntityList[T]` and override an `_on_add` hook. Today's
  only list (`Scene.messages`) doesn't need one — the base
  `EntityList[Message]` is enough.
- .implemented-by: EntityList

## entity-character: Character

```python
class Character(Entity):
    _actor: Actor                  # shared singleton via App.get_actor(owner)

    class Model(Entity.Model):
        owner: Literal["user", "stub", "npc"]

    def notify(self, event) -> Awaitable[None]: ...   # spawns actor.respond
    def annotate_context(self, ctx) -> None: ...      # body + scene recurse

    @action
    async def say(self, scene_id: EntityId, body: str) -> None: ...
```

- character-init-binds-actor: `Character.__init__` resolves the Actor
  singleton for `model.owner` via `App.get_actor(owner)` and stores
  it as `self._actor`. See [[actors]] for the actor hierarchy.
- character-listener: On `EntityChanged` from a subscribed scene, if
  the new message's sender is NOT `self`, spawn an async task that
  calls `self._actor.respond(message, self, scene)`. A non-None
  reply text is delivered via `self.say(scene.id, text)`, which
  runs the normal `EntityChanged` cycle.
- character-campaign-ref: Inherited from `Entity` — every Entity
  carries `self._campaign` to resolve cross-entity references.
  Today's only use is `self.say` resolving the target scene; future
  uses (memories, items) follow the same path.
- character-annotate-context: Calls `super().annotate_context(ctx)`
  (writes `self.body`), then recurses into `ctx.scene` so an NPC's
  prompt includes both *who I am* and *where I am* via one
  polymorphic call.
- character-say: `@action`-callable. Resolves
  `self._campaign.get(scene_id)`, constructs
  `Message(sender_id=self.id, body=body)`, and calls
  `scene.messages.append(message)`. The single mutator for "this
  character produces a message" — unifies user input (FE-issued
  `EntityAction`) and NPC response (in-process call from
  `notify`). The verb `say` covers both dialogue (`"Hi"`) and
  narration (`"/me leaves the tavern"`) — the body convention
  signals which.
- .implemented-by: Character

## entity-scene: Scene

```python
class Scene(Entity):                  # abstract
    class Model(Entity.Model):
        character_ids: list[EntityId]
        messages: list[Message] = []   # EntityList[Message] at runtime

    @property
    def characters(self) -> list[Character]: ...        # resolved via campaign
    @property
    def user_characters(self) -> list[Character]: ...   # has_human_actor() subset

    async def idle(self, timeout: float = 5.0) -> None: ...

class SimpleScene(Scene):             # concrete: exactly two characters
    def __init__(...): ...            # validates 1 user + 1 non-user; subscribes
```

- scene-pure-data: Scene is pure data + event source. The single
  mutation surface is `scene.messages.append(msg)` (the EntityList
  mutator) — no `Scene.append` method, no `dispatch`, no
  orchestration. The mutator's auto-emit fires the EntityChanged
  cascade. Wire identity of a message is the composite
  `(scene.id, position-in-messages)`; nothing on the Message itself
  carries identity.
- scene-characters-resolve-on-demand: `Scene.characters` is a
  property that resolves `self._model.character_ids` through the
  campaign on every access. No cached list on the Entity.
- scene-init-subscribes-characters: `SimpleScene.__init__` subscribes
  every character to itself, wiring the listener-driven response
  cycle automatically.
- scene-on-disk: `Scene.Model.character_ids` is persisted to the
  scene's markdown frontmatter. `Scene.Model.messages` is a Model
  field but runtime-only at the persistence layer: on `App` reload
  it's wiped (per [[backend]] `backend-reload`); the loader does
  not read or write `messages` to disk. Save-game persistence adds
  a messages sidecar later.
- scene-idle: `await scene.idle()` waits for all background tasks
  spawned in response to recent emissions to settle. Lives on Scene
  (not Entity) because Scene is where mutation cascades actually
  happen; test-only primitive, production never calls it.
- .implemented-by: Scene, SimpleScene

## entity-message: Message

```python
class Message(BaseModel):
    sender_id: EntityId
    body: str
```

- message-shape: A single Pydantic class — both wire shape and the
  in-memory representation. No dataclass / `Message.Model` split,
  no `Entity.Model`-style wrapper. Two fields: who sent it, what
  they said.
- message-wire-identity: Position is identity. A message's address
  is the composite `(scene.id, position-in-scene.messages)`,
  assembled externally by callers that need to reference a
  specific message. Nothing on the Message itself carries
  identity — `scene_id`, `index`, message_id all absent by design.
- message-not-entity: Messages are NOT Entities. No `EntityId`, no
  individual subscribe. They live as `Scene.Model.messages:
  list[Message]` — an `EntityList[Message]` at runtime (per
  `entity-list-attribute`). Per-message operations beyond append
  (edit/react/redact, if/when added) are exposed as `@action`
  methods on Scene; Scene is the entity-level addressable
  container.
- message-dataflow: Every message is appended via
  `scene.messages.append(msg)`. The EntityList mutator emits
  `EntityChanged` carrying a `ListDelta(start=-1, len=0,
  items=[msg])` (per [[events]] `events-attribute-deltas`).
  Reactions cascade via listener fanout per [[events]]
  (`events-dataflow`). Both user input (via `Character.say` from
  an `EntityAction`) and NPC response (in-process call from
  `Character.notify`) flow through the same append.
- .implemented-by: Message, Character.say, EntityList

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

    def get(self, entity_id: EntityId) -> Entity | None: ...
    def add(self, entity: Entity) -> None: ...
    def delete(self, entity_id: EntityId) -> None: ...

    @classmethod
    def load(cls, path: Path) -> Campaign: ...

    class Model(BaseModel):                # canonical serialised form
        name: str
        default_scene_id: EntityId | None
```

- campaign-container: Campaign holds every loaded entity directly,
  backed internally by an `EntityFactory` (default
  `DictEntityFactory` — in-memory dict). Storage is private
  (`self._store`); the public surface is `get` / `add` / `delete`.
  The storage abstraction is the seam for future persistent
  backends; today nothing else implements `EntityFactory`.
- campaign-load: Single forward pass in dependency order
  (characters before scenes, so a scene's cross-refs resolve at
  construction time via `campaign.get(id)`). Reads `config.yaml`,
  walks each directory, parses YAML frontmatter + body into
  `Entity.Model`, calls `EntityClass(model, self)`, then
  `self.add(entity)`. No ghost pattern, no two-phase wire-up —
  load order eliminates the need.
- campaign-model: `Campaign.Model` is the canonical serialised form
  (carries `name` + `default_scene_id`). Same one-model rule as
  Entity: no parallel `CampaignResponse`.
- campaign-no-subscribe-method: The architectural Campaign
  interface ([[architecture]] `architecture-interface-campaign`)
  includes `subscribe(entity_ids)` for the wire-mirror surface
  (see FE Campaign in [[frontend]]). On the BE, subscription is
  per-entity via `entity.subscribe(listener)`; `WsConnection`
  uses that primitive directly. No separate `Campaign.subscribe`
  method exists or is needed.
- campaign-runtime-mutation-deferred: `Campaign.add` and
  `Campaign.delete` exist on the architectural surface but emit no
  events today, and Campaign carries no listeners. Runtime
  scene/entity addition or removal is therefore not visible to
  subscribed clients. This is benign today — scenes load from disk
  at startup and the only runtime mutation surface is
  `scene.messages.append`. When runtime entity mutation lands,
  Campaign becomes subscribable: a reserved `entity_id` (or the
  cid itself) resolves to a Campaign-as-Entity exposing an
  `entity_ids` or `scene_ids` Model field wrapped in an
  `EntityList`. `add`/`delete` mutate that list, fire
  `EntityChanged` through the existing machinery, and the FE picks
  up the diff as a normal `ListDelta`. Not implemented; flagged so
  the design point isn't lost.
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
