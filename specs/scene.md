# scene: The active game scene

A scene is an Entity representing the active context for a game session. It
holds the characters present and the full message history. Scene is abstract;
SimpleScene is the scaffold concrete implementation.

## scene-impl: Scene and SimpleScene classes

### scene-class: Scene(Entity) _(abstract)_

- `messages: list[Message]` Ordered list of all chat messages in the scene.
  A message's index in this list is its id; no separate counter is maintained.

`characters(self) -> list[Character]` _(abstract property)_
- scene-characters-property: Returns the characters in the scene. Subclasses compute or cache
  this — Scene does not store a list, so a SimpleScene with two fields can answer without
  duplicating state.

`_append_message(self, message: Message) -> int`
- scene-append-history: Appends `message` to `self.messages`.
- scene-append-return: Returns the new index (`len(self.messages) - 1`).

`serialize_message(self, index: int) -> Message.Model`
- scene-serialize-message: Returns
  `Message.Model(id=MessageId(f"{self.id}:{index}"), sender_id=self.messages[index].sender.id, body=self.messages[index].body)`.
  This is the only place `MessageId` is constructed; scene-internal code uses `int` indices.

`dispatch(self, message: Message) -> MessageId` _(abstract)_
- .implements: message-dataflow-receive
- .implemented-by: SimpleScene.dispatch

### simple-scene: SimpleScene(Scene)

Assumes exactly one user-controlled Character and one NPC Character. Direct references to
each are held as `_user` and `_npc` for simple two-party routing.

- `_user: Character` The human-controlled character (sender of POST messages).
- `_npc: Character` The NPC character.

`characters(self) -> list[Character]` _(property)_
- simple-scene-characters: Returns `[self._user, self._npc]`. No backing list; computed each call.

`dispatch(self, message: Message) -> MessageId`
- simple-scene-dispatch-append: Calls `index = self._append_message(message)`.
- simple-scene-dispatch-task: Spawns `asyncio.create_task(self._respond(message))`; does NOT await.
- simple-scene-dispatch-return: Returns `MessageId(f"{self.id}:{index}")`.
- .implements: message-simplescene-dispatch, message-simplescene-respond, message-dataflow-receive, Scene.dispatch

`_respond(self, message: Message) -> None` _(async)_
- simple-scene-respond-call: `response = await self._npc.respond(message)`.
- simple-scene-respond-append: If `response is not None`, calls
  `latest_index = self._append_message(response)`.
- simple-scene-respond-notify: Calls `self._user.notify_messages(latest_index)` to wake the
  user's connected SSE client.
- .implements: message-simplescene-respond
