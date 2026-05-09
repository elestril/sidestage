# actor: The controller of a Character

An Actor controls a Character. It is either a human (UserActor) or an AI
model. Actors do not store world-state — all world-state lives on the Character.

## actor-impl: Implementation specs

- actor-respond: Abstract method — receives a Message, produces a response Message
- stub-actor-respond: StubActor always responds with "Hello User!"
  - .implements: cuj-hello-respond
- user-actor-ws: UserActor manages a single WebSocket connection
- user-actor-receive: Receives a user Message over WebSocket and dispatches to Scene
  - .implements: cuj-hello-send
- user-actor-send: Sends each Character's response Message back over the WebSocket
  - .implements: cuj-hello-respond
