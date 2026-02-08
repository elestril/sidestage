# `sidestage.sync`

## Classes

### `SyncManager`

#### `broadcast(message: dict[str, Any], exclude: WebSocket | None = None)` *async*

Broadcasts a message to all connected clients, optionally excluding one (the sender).

#### `connect(websocket: WebSocket)` *async*

#### `disconnect(websocket: WebSocket)`

#### `handle_message(websocket: WebSocket, data: str, handler: Callable[WebSocket, dict[str, Any], Awaitable[NoneType]] | None = None)` *async*

Handles incoming messages from clients and routes them accordingly.
