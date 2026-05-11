# actor: Edge-state holder for a Character

An Actor is a runtime singleton owned by `App`. It holds the **edge state**
that connects a Character to the world outside the Sidestage process —
LLM connections, SSE subscriptions, future auth context. Character carries
world-data; Actor carries the I/O.

Two actor classes today:
- `StubActor` — deterministic test responder, no edge state. `respond`
  returns `Message(sender=character, body=character.body)`.
- `UserActor` — per-user SSE subscription manager. Holds the
  `QueueListener`s spawned by SSE handlers on this user's behalf and
  manages their lifecycle (`subscribe_to`, `unsubscribe_from`,
  `cancel_all`). `respond` returns `None` (humans answer via REST POST,
  not via the listener path).

Actor is NOT an Entity — Actors don't receive events. The Listener role
for a Character belongs to `Character.notify` (per `character.md` and
`events-pattern-subscription`); the Character orchestrates the response
cycle by calling `self._actor.respond(...)` from inside the async task it
spawns in `notify`.

`Character.owner: Literal["user", "stub"]` selects the runtime Actor via
`App.get_actor(owner)`. Today: 1:1 — one UserActor singleton, one
StubActor singleton. When multi-user lands, `owner` will generalize to
per-instance identifiers (`"bob"`, `"alice"`); each user-owned character
will resolve to its own UserActor instance.
