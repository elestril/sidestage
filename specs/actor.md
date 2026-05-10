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
- .implements: message-simplescene-respond

### user-actor: UserActor(Actor)

Marker actor for a connected human player. Holds the SSE event queue created
by the SSE route handler at connect time. Does not generate responses —
human input arrives via REST POST, not via `respond()`.

`queue: asyncio.Queue`
`scene: Scene`

`is_human(self) -> bool`
- user-actor-is-human: Returns True.

`respond(self, message: Message, character: Character) -> Optional[Message]`
- user-actor-respond-noop: Returns None unconditionally. Human responses arrive via REST,
  not from this method.

`notify_messages(self, latest_index: int) -> None`
- user-actor-notify-enqueue: Constructs a `SceneUpdatedEvent(scene_id=self.scene.id, latest_message_index=latest_index)` and puts it onto `self.queue` via `put_nowait`.
- .implements: sse-dataflow-event, message-simplescene-respond
