# message: The unit of communication

A Message is created by an Actor and flows through the system from sender to
recipients via the Scene.

Per `spec-location-pydoc`, the `MessageId` NewType, `Message` class, and
`Message.Model` inner class invariants now live in pydoc on
`src/sidestage/message.py`. This file retains the prose intro, the
cross-cutting dataflow spec, and a label index for cross-reference.

Run `uv run pydoc-markdown` to
render the generated markdown view at `specs/generated/api.md`.

## message-dataflow: Dataflow

Every message — whether originating from the user via REST or from an Actor as a
response — flows through the same entry point: `scene.dispatch(message)`. The
POST handler holds no special path; it constructs a `Message` and calls
`dispatch` identically to any other caller. `dispatch` returns the `MessageId`
assigned to the message.

1. message-dataflow-receive: Message is received by `Scene.dispatch()` via
   either internal calls or [rest-api-post-message].
   - .implemented-by: SimpleScene.dispatch, rest-api-post-message, api-dataflow-send
2. message-simplescene-dispatch: `SimpleScene.dispatch`. The message is appended
   to Scene.messages, and the new array index is used to construct the MessageId
   and returned to the caller.
   - .implemented-by: SimpleScene.dispatch
3. message-simplescene-respond: asyncronously self.\_npc.response() is
   generated, it is appended to self.messages, then
   self.\_user.notify_messages() is called with the latest message id.
   - .implemented-by: SimpleScene.dispatch, Character.respond, Character.notify_messages, StubActor.respond, UserActor.notify_messages

## message-labels: Label index (defined in pydoc)

The following labels are defined in pydoc on `src/sidestage/message.py` and are
available as link targets from this and other markdown specs:

- `message-id` — the `MessageId` NewType (module docstring)
  - `message-id-newtype`, `message-id-format`, `message-id-assign` — invariants
- `message-class` — the `Message` dataclass
  - `message-class-fields`, `message-class-no-serialize` — invariants
- `message-model` — the `Message.Model` inner Pydantic class
  - `message-model-fields`, `message-model-inner`, `message-model-built-by` — invariants
