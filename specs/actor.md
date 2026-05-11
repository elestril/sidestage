# actor: The controller of a Character

An Actor controls one or more Characters. Actors are runtime singletons owned
by `App` (not Entity subclasses); each Character holds a reference to the
shared Actor instance for its `owner`. Three actors exist today: `StubActor`
(deterministic test scaffold), `UserActor` (SSE notification target), and
`NpcActor` (LLM-backed responder, future).

## actor-impl: Actor, StubActor, UserActor classes

The class specs — class-level invariants and method invariants for `Actor`,
`StubActor`, and `UserActor` — live in pydoc on `src/sidestage/actor.py` per
`spec-location-pydoc`.

Run `uv run pydoc-markdown` to render the generated
markdown view at `specs/generated/api.md`.

Key labels defined in pydoc (for cross-reference from this and other markdown specs):
- `actor-base` — the `Actor` (ABC) class spec
- `actor-notify-default-noop` — default `Actor.notify` invariant
- `stub-actor` — the `StubActor` class spec
- `stub-actor-is-human`, `stub-actor-respond-returns` — invariants of `StubActor`
- `user-actor` — the `UserActor` class spec
- `user-actor-is-human`, `user-actor-respond-noop`, `user-actor-add-queue`,
  `user-actor-remove-queue`, `user-actor-notify-broadcast` — invariants of
  `UserActor`
