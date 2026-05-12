# character: A person in the game world

A Character represents a person in the game world — player character, NPC,
or meta-character such as the GM. Characters store world-data (name, body)
plus an `owner` discriminator that selects which runtime Actor handles
responses. Today's owners: `"user"`, `"stub"`, and `"npc"`.

`Character` is also a `Listener` (per `events.md`). When a Scene it's
subscribed to emits an `EntityChanged`, `Character.notify(event, emitter)`
inspects the new message and (if not from itself) spawns an async task
that calls `self._actor.respond(message, self)`. A non-None response is
appended back to the emitter scene via `emitter.append(response)`, firing
another `EntityChanged`.

UserActor's `respond` returns `None` so user characters auto-noop on this
listener path. StubActor returns `Message(sender=character, body=character.body)`
— the character's body verbatim is the canned response. NpcActor calls
the LLM via `litellm.acompletion` (per `npc-actor`).

## character-factory-ref: Character holds its EntityFactory

A loaded Character carries a reference to its `EntityFactory` so it can
resolve other entities by id (scenes for context, future related
characters, future memory nodes).

- character-factory-ref: `self._factory: EntityFactory` set at
  construction. Required keyword arg of `Character.__init__`.
- character-factory-ref-deserialize: `Character.deserialize(model,
  factory)` takes the factory as a second positional argument and
  threads it into `__init__`.
- .implemented-by: Character.__init__, Character.deserialize

## character-annotate-context: Override that composes persona + setting

Character override of `entity-annotate-context` adds the scene's
contribution alongside the character's own body, so an NPC's prompt
includes both *who I am* and *where I am* via one polymorphic call.

- character-annotate-context: Calls `super().annotate_context(ctx)`
  (which writes `self.body` keyed by `self`), then recurses into the
  scene carried on the context: `ctx.scene.annotate_context(ctx)`.
  The actor populates `ctx.scene` from `event.entity` at call time,
  so Character doesn't need to look it up.
- character-annotate-context-subclasses: Future Character subclasses
  (cheap fighter, scheming villain, DM-meta) override to recurse into
  more related entities — retrieved memories (via `self._factory`),
  relevant items, etc. Today's base override is the minimum.
- .implemented-by: Character.annotate_context
