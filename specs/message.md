# message: The unit of communication

A Message is created by an Actor and flows through the system from sender to
recipients via the Scene.

## message-id: MessageId type

`MessageId = NewType('MessageId', str)`

- message-id-newtype: All message references use `MessageId` rather than bare
  `str`.
- message-id-format: A `MessageId` is formatted as `"{scene_id}:{index}"` where
  `index` is a per-scene monotonically increasing integer; ids within a scene
  are consecutive.
- message-id-assign: A `Message` arrives at `Scene._append_message` without an
  id; the scene assigns the next available `MessageId` there. This is the only
  place ids are assigned.

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

## message-impl: Message class

### message-class: Message

`sender: Character`
`body: str`

The domain `Message` carries no id field — its position in `scene.messages` is
its identity. Wire serialization is performed by `Scene.serialize_message(index)`
since constructing the `MessageId` requires the scene's id.

### message-model: Message.Model

Inner Pydantic model defining the canonical wire shape used both in
`GET /api/scenes/{scene_id}/messages` responses and in SSE `message_created`
event payloads.

```python
class Model(BaseModel):
    id: MessageId        # "{scene_id}:{index}" — built by Scene.serialize_message
    sender_id: EntityId  # resolves against the client entity cache
    body: str
```
