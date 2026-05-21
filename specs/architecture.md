# architecture: Key architectural choices

Sidestage is an agentic AI chat system for ttRPG roleplay. The domain (entities,
scenes, characters, messages) is specified in [[entity-model]]; this file is
about the **shape** of the system — the architectural decisions that distinguish
it from "another chat app". Implementation details live in [[backend]],
[[frontend]], [[actors]], and [[events]].

## architecture-interface: Core operations + one event

Campaign and Entities expose a small, uniform surface. **All world interaction
is one of these operations, plus the one event.**

### architecture-interface-campaign: The central container for all world state.

The backend has the authoritative copy of campaign, the frontend has a
synchronized copy that tracks the authoritative campaign via websocket rpc
calls.

```python
class Campaign:
    def get(self, entity_id: EntityId) -> Entity: ...
    def add(self, entity: Entity) -> None: ...
    def delete(self, entity_id: EntityId) -> None: ...
    def subscribe(self, entity_ids: list[EntityId]) -> None: ...
    # plus partial-update variants for incrementally adjusting subscriptions
```

### architecture-interface-entity: The generic representation of all in-world things

Everything in the world is represented as an Entity. The core functional
subclasses are Character and Scene, but e.g. Location or Item would also be
modeled as Entity.

Entities have an attribute centered interface, but implement e.g. the event
logic under the hood of python property decorators.

```python
class Entity:
    id: EntityId      # campaign-wide unique id
    body: str         # long-form markdown description
```

Entities can _also_ implement `actions`, e.g. the 'Character' subclass
implements 'speak'. Those actions are available via rpc and can be triggered by
the frontend.

Entities are also EntityChanged event subscribers, so cascading updates are
possible and desired.

### architecture-interface-event: Event-driven logic

The entire logic of Sidestage is built around `EntityChanged` events and
`Listener` subscribers. See [[events]] for the full protocol.

The `Listener` protocol:

```python
class Listener(Protocol):
    def notify(self, event: EntityChanged) -> None | Awaitable[None]: ...
```

## architecture-uniformity: The frontend mirrors the backend

The above architecture is mirrored in the frontend; the FE/BE connection is
itself a JSON-over-WebSocket RPC of the same Campaign interface.

### architecture-uniformity-entities

The frontend has a `Campaign` class. Its `get` method returns promises of
Entities, which are hydrated on demand. It subscribes to `EntityChanged`
events on the backend to keep its entities in-sync, and it relays updates of
its own entities back to the backend.

There is NO other communication channel, **everything** is routed through Entity
updates.

### architecture-uniformity-widgets: Entity representation

All entity subclasses have widgets that render the entity. Those are wired as
promises to the underlying dataclass and update when the dataclass changes.

## architecture-corollary: Consequences of this architecture

### architecture-listener-cascade: No central dispatcher

Events cascade as needed. There is no central dispatcher, all logic is driven by
Entity updates and event subscriptions.

### architecture-actor-character-split: Edge-state lives outside Campaign

`Characters` (a subclass of Entity) define the in-world persona. They are
coupled to a (non-Entity) `Actor`, which acts as the controller. Core Actor
subclasses are the `NpcActor` (which manages the connection to an LLM), and
`UserActor` which represents ownership by a human user.

### architecture-rejected: Explicit non-choices

The shape excludes several common patterns by construction:

- **No domain-specific event types.** Only `EntityChanged`. New behaviours
  subscribe and inspect `attributes`; they don't get a new event class.
- **No orchestrator class.** Reactions are listeners on entities, not branches
  in a top-level coordinator.
- **No optimistic projection state.** Would create a competing source of truth
  alongside Campaign.
- **No GraphQL or query language.** The uniform interface IS the protocol; query
  languages shift authority toward the query-issuer.
- **No SSE-style one-way notification.** The wire surface is bidirectional from
  the start because the interface is — projections observe, mutate, and
  unsubscribe through the same channel.
- **No mutation pipeline per consumer.** Mutations go through Campaign;
  consumers only read.
- **No REST sync protocol.** The FE talks to Campaign only over the
  WebSocket. REST endpoints exist as a read-only debug/ops mirror
  (per [[backend]] `backend-rest-debug`), never as the FE's sync
  channel and never as a write path.

## architecture-spec-driven: Specs and code stay in lockstep

The project is driven by specs in `specs/*.md`. Markdown owns cross-cutting
concerns (this file, [[events]], [[testing]]) and class prose ([[entity-model]],
[[actors]], [[backend]], [[frontend]]). Per-symbol invariants live in pydoc on
the class. Labels link specs to code via `.implements:` / `.tested-by:`
annotations. CLAUDE.md is explicit: specs are the source of truth, code is kept
in sync, spec amendments require a design conversation. See [[spec]].

## architecture-cuj: Canonical CUJs

Two journeys traverse the whole shape end-to-end:

1. **cuj-startup**: User runs `sidestage` → server loads the first campaign →
   flips to `SERVING` → SPA loads → FE Campaign connects → resolves the scene
   → DOM renders.
   - .implemented-by: App.run, App._setup_routes, Campaign
2. **cuj-hello-send / cuj-hello-respond**: User types a message → FE widget
   calls `alice.speak("Hi")` → relayed to BE as EntityAction → BE
   `Character.speak` constructs a Message and appends to the scene →
   `EntityChanged` cascades to in-process listeners (NPC actor responds via
   its own `character.speak(...)`) AND to FE Campaign → FE re-renders.
   - .tested-by: cuj-hello-browser

The whole loop is exercised by `tests/playwright/cuj_hello.spec.ts`.
