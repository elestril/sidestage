# character: A person in the game world

A Character represents a person in the game world — a player character, NPC,
or meta-character such as the GM. Characters store world-state plus an
`owner` discriminator that selects which runtime Actor handles their
responses.

## character-impl: Character class

The `Character` class spec — class-level invariants, attribute invariants
(`owner`), inner `Model`, constructor, and methods (`respond`, `notify`,
`has_human_actor`) — lives in pydoc on `src/sidestage/character.py` per
`spec-location-pydoc`.

Run `uv run pydoc-markdown` to render the generated
markdown view at `specs/generated/api.md`.

Key labels defined in pydoc (for cross-reference from this and other markdown specs):
- `character-class` — the class spec
- `character-owner` — attribute
- `character-model` — inner Pydantic model
- `character-init-stores-owner`, `character-init-binds-actor` — `__init__`
  invariants
- `character-respond-passthrough` — `respond` method
- `character-notify-passthrough` — `notify` method
- `character-has-human-actor` — `has_human_actor` method
