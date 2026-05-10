# message: The unit of communication

A Message is created by an Actor and flows through the system from sender to
recipients via the Scene.

## message-dataflow: Dataflow

1. message-dataflow-receive: UserActor.run() receives a serialized Message over WebSocket
   - .implements: cuj-hello-send
2. message-dataflow-deserialize: Deserializes it into a Message object
   - .implements: cuj-hello-send
3. message-dataflow-dispatch: Calls scene.dispatch(message)
   - .implements: cuj-hello-send
4. message-dataflow-route: Scene appends to history; calls character.respond() on each Character except the sender
   - .implements: cuj-hello-respond
5. message-dataflow-recurse: If respond() returns a Message, scene.dispatch() is called on it recursively
   - .implements: cuj-hello-respond
6. message-dataflow-return: scene.dispatch() returns None

## message-impl: Message class

### message-class: Message

`sender: Character`
`body: str`
