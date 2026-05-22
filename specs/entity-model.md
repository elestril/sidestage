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
  subclass `EntityList[T]` and override an `_on_add` hook.
  `Scene.characters` uses the base `EntityList[EntityId]`; no per-
  item hook needed. `Scene.messages` uses `MessageList`, whose
  `_on_add` calls `factory.append_message(scene_id, msg)` so each
  append also lands in the Redis stream (per [[persistence]]
  `persistence-streams-append`); the in-memory
  `DictEntityFactory.append_message` is a no-op since the
  `EntityList` already stores the item on `Scene.Model.messages`.
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
        characters: list[EntityId] = []   # EntityList[EntityId] at runtime
        messages: list[Message] = []      # MessageList at runtime; stream-backed

    async def idle(self, timeout: float = 5.0) -> None: ...

class SimpleScene(Scene):             # concrete: exactly two characters
    def __init__(self, model, campaign):    # validates 1 user + 1 npc; subscribes
        ...
```

- scene-pure-data: Scene is pure data + event source. The mutation
  surfaces are `scene.characters.append(id)` and
  `scene.messages.append(msg)` (both EntityList mutators) — no
  `Scene.append` method, no `dispatch`, no orchestration. The
  mutators auto-emit `EntityChanged`, firing the cascade. Wire
  identity of a message is the composite
  `(scene.id, position-in-messages)`; nothing on the Message itself
  carries identity.
- scene-characters-list: `Scene.Model.characters` is a `list[EntityId]`
  carrying the in-scene character ids. Wrapped in an
  `EntityList[EntityId]` at construction (registered in
  `_entity_lists` alongside `messages`), so add/remove mutations
  emit a `ListDelta` and the FE picks them up over the WS. The
  `EntityId`-typed element signals "list of references"; consumers
  resolve via `self._campaign.get(id)`.
- scene-characters-graph-edges: FalkorEntityFactory translates
  `EntityList[EntityId]`-typed Model fields into real graph
  relationships internally (per [[persistence]]
  `persistence-graph-edges`). The rest of the codebase never sees
  edges as a primitive; the Model field is the only surface.
- simple-scene-init-roles: `SimpleScene.__init__` validates count
  and roles at construction. Role identification is by
  `Character.owner` (the human-controlled character is the user;
  the other is the NPC), NOT by position in `model.characters`.
  Raises `ValueError` unless exactly one of each role is present.
- simple-scene-init-subscribes-characters: After validation,
  subscribes every character so the listener-driven response cycle
  runs.
  - .tested-by: test_events_dataflow
- scene-on-disk: Scene serialises as YAML frontmatter +
  markdown body. `characters: [...]` lists the in-scene character
  ids. `messages` is NOT persisted to markdown — chat history lives
  in the per-scene Redis stream (per [[persistence]]
  `persistence-streams-key`) and is populated from `XRANGE` at
  scene open, appended through `XADD` on mutation.
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
  list[Message]` — a `MessageList` at runtime (per
  `entity-list-attribute-no-subclass`). Per-message operations
  beyond append (edit/react/redact, if/when added) are exposed as
  `@action` methods on Scene; Scene is the entity-level addressable
  container.
- message-stream-backed: `Scene.Model.messages` is backed by a per-scene
  Redis stream when the campaign runs against
  `FalkorEntityFactory` (per [[persistence]] `persistence-streams-key`).
  Population is one-shot at scene open: the factory's
  `read_messages(scene_id)` is called *before* the Scene wrapper is
  constructed, so the load-time `list.extend` bypasses emit (per
  `entity-list-attribute-mechanism`). Mutations write through:
  `MessageList._on_add` calls `factory.append_message(scene_id, msg)`
  before the item lands in the list, so `XADD` and the in-memory
  append are atomic from the caller's perspective. Chat history
  survives reload. Against `DictEntityFactory` (unit tests), the
  message methods are no-ops / empty: the in-memory list IS the
  authority.
- message-dataflow: Every message is appended via
  `scene.messages.append(msg)`. The MessageList mutator writes
  through to the stream and emits `EntityChanged` carrying a
  `ListDelta(start=-1, len=0, items=[msg])` (per [[events]]
  `events-attribute-deltas`). Reactions cascade via listener
  fanout per [[events]] (`events-dataflow`). Both user input (via
  `Character.say` from an `EntityAction`) and NPC response
  (in-process call from `Character.notify`) flow through the same
  append.
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
    def open(cls, name: str, store: EntityFactory) -> Campaign: ...
    @classmethod
    def import_from_disk(cls, path: Path, store: EntityFactory) -> Campaign: ...
    def export(self, path: Path) -> None: ...

    class Model(BaseModel):                # canonical serialised form
        name: str
        default_scene_id: EntityId | None
```

- campaign-container: Campaign holds every loaded entity directly,
  backed internally by an `EntityFactory`. Storage is private
  (`self._store`); the public surface is `get` / `add` / `delete`.
  Two concrete factories exist: `DictEntityFactory` (in-memory, used
  by unit tests) and `FalkorEntityFactory` (FalkorDBLite-backed, used
  in production and integration tests — per [[persistence]]).
- campaign-open: Open a Campaign from a populated graph + stream
  store. Reads `<sidestage_dir>/campaigns/<name>/config.yaml` for
  intrinsic campaign metadata; walks `store.entities()` to construct
  Entity wrappers around the rehydrated Models. No markdown is read
  for entity state. Used when the campaign's graph already exists
  (per [[persistence]] `persistence-startup-import-on-empty`).
- campaign-import-from-disk: Import a Campaign from its markdown
  directory into an empty store. Reads `config.yaml`, walks each
  entity directory in dependency order (characters before scenes —
  so a scene's `characters: [...]` ids resolve at construction time
  via `campaign.get(id)`), parses YAML frontmatter + body into
  `Entity.Model`, and calls `store.add(entity)`. For
  `FalkorEntityFactory`, the factory introspects each Model's fields
  on `add` and translates any `EntityList[EntityId]`-typed field
  into real graph relationships (per [[persistence]]
  `persistence-graph-edges`); the rest of the codebase is unaware
  of the translation. The single cross-cutting load path used when
  `persistence-startup-import-on-empty` fires.
- campaign-export: Regenerate the markdown directory canonically
  from the store. Writes `config.yaml`, walks `store.entities()`
  to emit each entity's `.md` (frontmatter + body). The
  `EntityList[EntityId]` fields serialise as plain YAML lists in
  the frontmatter (e.g. `characters: [alice, bob]`); chat history
  is NOT exported (lives in the stream, not in markdown). First-
  export diff noise against hand-written markdown is accepted
  (per [[persistence]] `persistence-export-dataflow-canonical`).
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
- .implemented-by: Campaign, Campaign.open, Campaign.import_from_disk,
  Campaign.export

## entity-campaign-tree: On-disk layout

```
<sidestage_dir>/campaigns/<campaign_name>/
├── config.yaml                       # CampaignConfig fields
├── characters/<id>.md                # Character.Model frontmatter + body
└── scenes/<id>.md                    # Scene.Model frontmatter + body
```

`config.yaml` serialises a `CampaignConfig`. Each Entity subclass
serialises as a single `.md` file: YAML frontmatter holds the Model's
intrinsic fields (`name`, plus subclass extras like `owner` and
`characters: [...]`); the markdown body is the entity's `body`. The
on-disk directory is the savegame format — entity state at runtime
lives in the graph (per [[persistence]]). Edits to markdown while the
server runs have no effect until `Campaign.import_from_disk` reimports.
