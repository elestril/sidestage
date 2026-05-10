# character: A person in the game world

A Character represents a person in the game world — a player character, NPC,
or meta-character such as the GM. Characters store world-state and delegate
response generation to their associated Actor.

## character-impl: Character class

### character-class: Character(Entity)

`_actor: Actor`

`respond(self, message: Message) -> Optional[Message]`
- character-respond-passthrough: Pure pass-through to `_actor.respond(message, self)`.
- .implements: message-dataflow-route

`has_human_actor(self) -> bool`
- character-has-human-actor: Returns `_actor.is_human()`.
