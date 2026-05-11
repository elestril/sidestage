# scene: The active game scene

A Scene is an Entity holding the characters present and the message
history. Scene is abstract; SimpleScene is the concrete impl (exactly two
characters: one user, one non-user — validated at construction).

Scene is **pure data + event source**. Public mutation:

- `scene.append(msg) -> MessageId` — append `msg` to history, emit
  `EntityChanged(scene_id, SceneChangeHint(latest_message_index=idx))`,
  return the assigned MessageId. The single mutation API. No `dispatch`,
  no `_respond` orchestration on Scene.
- `await scene.idle()` — wait for all background tasks the Scene's
  listeners spawned in response to recent emissions to settle. Used by
  tests (per `testing.md`); bounded by a small timeout.

`SimpleScene.__init__` subscribes every character to itself, wiring the
listener-driven response cycle automatically.

## scene-on-disk: Persistent shape

`Scene.Model` carries `characters: list[EntityId]` plus the inherited
Entity fields. **Messages are runtime-only** — not persisted today (per
the "ephemeral messages" decision). When save-game lands, the on-disk
shape gains a messages sidecar; until then `Scene.Model` is the complete
persistent declaration.
