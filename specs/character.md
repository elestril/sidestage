# character: A person in the game world

A Character represents a person in the game world — a player character, NPC,
or meta-character such as the GM. Characters store world-state and delegate
response generation to their associated Actor.

## character-impl: Implementation specs

- character-actor: A Character has an associated Actor
- character-respond: Delegates to `actor.respond()` — a pure pass-through
  - .implements: cuj-hello-respond
