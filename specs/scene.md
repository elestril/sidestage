# scene: The active game scene

A scene is an Entity representing the active context for a game session. It
holds the characters present and the full message history. Scene is abstract;
SimpleScene is the scaffold concrete implementation.

## scene-impl: Scene and SimpleScene classes

### scene-class: Scene(Entity) _(abstract)_

- `characters: list[Character]` The characters in the scene
- `messages: list[Message]` A ordered list of all chat messages in the scene.

`dispatch(self, message: Message) -> None` _(abstract)_

### simple-scene: SimpleScene(Scene)

Assumes exactly one UserActor character and one StubActor character.

`dispatch(self, message: Message) -> None`

1. simple-scene-dispatch-appends: Appends message to history.
2. simple-scene-dispatch-forwards: Calls respond() on the non-sender character.
3. simple-scene-dispatch-response-appends: If a response is returned, appends it
   to history.
4. simple-scene-dispatch-response-delivers: Calls respond() on the sender's
   character with the response.
5. .implements: message-dataflow-route, message-dataflow-recurse, message-dataflow-return
