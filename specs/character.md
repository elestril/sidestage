# character: A person in the game world

A Character represents a person in the game world — player character, NPC,
or meta-character such as the GM. Characters store world-data (name, body)
plus an `owner` discriminator that selects which runtime Actor handles
responses. Today's owners: `"user"` and `"stub"`.

`Character` is also a `Listener` (per `events.md`). When a Scene it's
subscribed to emits an `EntityChanged`, `Character.notify(event, emitter)`
inspects the new message and (if not from itself) spawns an async task
that calls `self._actor.respond(message, self)`. A non-None response is
appended back to the emitter scene via `emitter.append(response)`, firing
another `EntityChanged`.

UserActor's `respond` returns `None` so user characters auto-noop on this
listener path. StubActor returns `Message(sender=character, body=character.body)`
— the character's body verbatim is the canned response.
