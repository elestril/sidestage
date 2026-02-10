# `sidestage.character`

Character runtime wrapper.

Character pairs a CharacterModel (persistent data) with an Actor (behavior).
The Actor is injected at construction time by Campaign.get_character().

## Classes

### `Character`

Runtime wrapper for a CharacterModel with an associated Actor.

#### `__init__(model: CharacterModel, actor: Actor)`

#### `activate() -> None` *async*

Initialize the actor's LLM agent (for NPCActor). No-op for User.

#### `deactivate() -> None` *async*

Clean up actor state.
