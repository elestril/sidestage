# scene: The active game scene

A scene is an Entity representing the active context for a game session. It
holds the characters present and the full message history. Scene is abstract;
SimpleScene is the scaffold concrete implementation.

## scene-impl: Scene and SimpleScene classes

The `Scene` and `SimpleScene` class specs — class-level invariants, attribute
invariants, the inner `Scene.Model`, and per-method invariants — live in
pydoc on `src/sidestage/scene.py` per `spec-location-pydoc`.

Run `uv run pydoc-markdown` to
render the generated markdown view at `specs/generated/api.md`.

Key labels defined in pydoc (for cross-reference from this and other markdown
specs):

- `scene-class` — the abstract Scene class spec
- `scene-characters` — the `characters: list[Character]` attribute
- `scene-user-characters` — `user_characters` property: subset of `characters`
  whose `has_human_actor()` is True. Single source of truth for "which
  characters can a client send messages as".
- `scene-model` — the inner `Scene.Model` Pydantic shape
- `scene-messages-property` — the abstract `messages` property
- `scene-serialize-message` — `Scene.serialize_message`
- `scene-deserialize-signature`, `scene-deserialize-resolves`,
  `scene-deserialize-constructs` — invariants of `Scene.deserialize`
- `scene-to-response` — `Scene.to_response() -> SceneResponse` builds the
  API wire shape; the only place `SceneResponse` is constructed
- `simple-scene` — the SimpleScene class spec
- `simple-scene-init-count`, `simple-scene-init-user`, `simple-scene-init-npc`,
  `simple-scene-init-messages`, `simple-scene-init-aliases` — invariants of
  `SimpleScene.__init__`
- `simple-scene-messages` — `SimpleScene.messages` property
- `simple-scene-dispatch-append`, `simple-scene-dispatch-task`,
  `simple-scene-dispatch-return` — invariants of `SimpleScene.dispatch`

Internal contracts (private members; not public spec targets per
`spec-link-targets-private`, but invariants are documented in pydoc for
implementer reference):

- `scene-append-history`, `scene-append-return` — `Scene._append_message`
- `scene-make-update` — `SimpleScene._make_scene_update`
- `simple-scene-respond-call`, `simple-scene-respond-append`,
  `simple-scene-respond-notify` — `SimpleScene._respond`
