# character: A person in the game world

A Character represents a person in the game world — a player character, NPC,
or meta-character such as the GM. Characters store world-state and delegate
response generation to their associated Actor.

## character-impl: Character class

### character-class: Character(Entity)

`_actor: Actor`

`respond(self, message: Message) -> Optional[Message]`
- character-respond-passthrough: Pure pass-through to `_actor.respond(message, self)`.
- .implements: message-simplescene-respond

`notify_messages(self, latest_index: int) -> None`
- character-notify-passthrough: Pure pass-through to `_actor.notify_messages(latest_index)`.
- .implements: message-simplescene-respond

`has_human_actor(self) -> bool`
- character-has-human-actor: Returns `_actor.is_human()`.
