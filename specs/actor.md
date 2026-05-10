# actor: The controller of a Character

An Actor controls a Character. It is either a human (UserActor) or an AI
model. Actors do not store world-state — all world-state lives on the Character.
An Actor may play multiple characters (e.g. a DM or an LLM model).

## actor-impl: Actor, StubActor, and UserActor classes

### actor-base: Actor (ABC)

`is_human(self) -> bool` *(abstract)*

`respond(self, message: Message, character: Character) -> Optional[Message]` *(abstract)*

### stub-actor: StubActor(Actor)

Scaffold actor for testing.

`is_human(self) -> bool`
- stub-actor-is-human: Returns False.

`respond(self, message: Message, character: Character) -> Optional[Message]`
- stub-actor-respond-ignores: Returns None if `message.sender.has_human_actor()` is False.
- stub-actor-respond-returns: Returns `Message(sender=character, body="Hello User!")`.
- .implements: message-dataflow-recurse

### user-actor: UserActor(Actor)

Manages a human player's WebSocket connection.

`is_human(self) -> bool`
- user-actor-is-human: Returns True.

`websocket: WebSocket`
`scene: Scene`

`run(self) -> None`
- user-actor-run-receives: Awaits a `MessageEvent` from `self.websocket`.
- user-actor-run-deserializes: Constructs a domain `Message` from the `MessageEvent`, setting `sender` to this actor's character.
- user-actor-run-dispatches: Calls `self.scene.dispatch(message)` and loops.
- .implements: ws-dataflow-inbound, ws-dataflow-dispatch

`respond(self, message: Message, character: Character) -> Optional[Message]`
- user-actor-respond-sends: Serializes `message` into a `MessageEvent` (with `sender_id = message.sender.id`) and sends it over `self.websocket`.
- user-actor-respond-returns: Returns None.
- .implements: ws-dataflow-outbound
