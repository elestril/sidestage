# actor: Edge-state holder for a Character

An Actor is a runtime singleton owned by `App`. It holds the **edge state**
that connects a Character to the world outside the Sidestage process —
LLM connections, SSE subscriptions, future auth context. Character carries
world-data; Actor carries the I/O.

Three actor classes today:
- `StubActor` — deterministic test responder, no edge state. `respond`
  returns `Message(sender=character, body=character.body)`.
- `UserActor` — per-user SSE subscription manager. Holds the
  `QueueListener`s spawned by SSE handlers on this user's behalf and
  manages their lifecycle (`subscribe_to`, `unsubscribe_from`,
  `cancel_all`). `respond` returns `None` (humans answer via REST POST,
  not via the listener path).
- `NpcActor` — LLM-backed responder. Singleton owned by App; holds one
  resolved `ModelEntry` (the `default` role of the active profile).
  `respond(message, character)` builds a system prompt by joining
  `character.annotate_context(...)` outputs, shapes scene history into
  chat turns, and calls `litellm.acompletion`. Returns `None` on any
  failure (transport, timeout, non-2xx, empty body).

Actor is NOT an Entity — Actors don't receive events. The Listener role
for a Character belongs to `Character.notify` (per `character.md` and
`events-pattern-subscription`); the Character orchestrates the response
cycle by calling `self._actor.respond(...)` from inside the async task it
spawns in `notify`.

`Character.owner: Literal["user", "stub", "npc"]` selects the runtime
Actor via `App.get_actor(owner)`. Today: 1:1 — one UserActor singleton,
one StubActor singleton, one NpcActor singleton. When multi-user lands,
`owner` will generalize to per-instance identifiers (`"bob"`, `"alice"`);
each user-owned character will resolve to its own UserActor instance.

## npc-actor: LLM-backed Actor

`NpcActor` talks to an LLM for response generation. It is a process-wide
singleton constructed from the active profile's `default` role
(`profile.models["default"]`). Multiple Characters with `owner="npc"`
share one NpcActor instance — the entry it carries is immutable, the
litellm call is stateless per request, so concurrent `respond` calls
across scenes need no coordination.

- npc-actor-init: Constructor takes one `ModelEntry`; stores it as
  `self._entry`. No I/O at construction time.
- npc-actor-is-human: Returns `False`.
- npc-actor-respond: `respond(message, character, scene)`:
  1. Build `MessageContext(message=message, scene=scene)`.
  2. `character.annotate_context(ctx)` — entity tree contributes the
     prompt material.
  3. System prompt = `"\n\n".join(ctx.annotations.values())`.
  4. Shape `scene.messages` into chat turns mapped by sender →
     `assistant` (when sender is `character`) or `user` (otherwise).
  5. Call `litellm.acompletion` with the messages list and per-entry
     kwargs (`_litellm_kwargs(self._entry)`).
  6. Return `Message(sender=character, body=text)`.
- npc-actor-respond-error-none: On transport error, timeout, non-2xx
  response, or empty/whitespace-only completion, returns `None`. Logs
  at WARNING (empty body) or EXCEPTION (raised). No in-band error
  placeholder messages — keeps scene history clean.
- npc-actor-respond-timeout: 60-second timeout on the litellm call —
  first-call budget for a local server that lazy-loads weights.
  Subsequent calls return in seconds. Unit tests must mock litellm
  because pytest's 2s default would otherwise fail the test before the
  call returns.
- npc-actor-litellm-kwargs: Every call passes `model=entry.model` and
  `api_base=entry.endpoint`. If `entry.api_key_env` is set, the api_key
  is `os.environ[entry.api_key_env]`; otherwise a stub (`"sk-no-key"`)
  is sent — litellm requires the param even when the server ignores
  it. The provider prefix in `entry.model` (`openai/...`,
  `anthropic/...`) routes the call.
- npc-actor-consumes-context: Calls `character.annotate_context(ctx)`
  exactly once per `respond`. Never reads character internals
  (`character.body`, etc.) directly — the Entity polymorphism
  (`entity-annotate-context`) is the contract between actor and
  character. When subclassed Characters override `annotate_context`
  to add memories / schemes / etc., NpcActor needs no change.
- .implements: character-init-binds-actor, server-get-actor
- .implemented-by: NpcActor
