# scene: The active game scene

A scene is the active context for a game session. It holds the characters
present and the full message history.

## scene-impl: Implementation specs

- scene-characters: Holds the list of Characters present in the scene
- scene-messages: Maintains an ordered list of all Messages exchanged in the scene
- scene-dispatch: Appends the incoming Message to the history, calls
  `character.respond()` on each Character, appends and returns their responses
  - .implements: cuj-hello-send, cuj-hello-respond

## scene-message: The Message object

A Message is the unit of communication between participants in a scene.

- message-sender: A Message has a sender (a Character)
- message-body: A Message has a text body
