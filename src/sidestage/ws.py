"""ws: WebSocket connection management.

Per `specs/events.md#events-subscription` and
`specs/backend.md#backend-ws`.

Owns the per-socket state for the multiplexed `/api/campaigns/{cid}/ws`
endpoint. Each accepted socket gets one `WsConnection`. The connection
parses incoming JSON frames, dispatches by `op`, owns one
`QueueListener` per subscribed entity, and serialises outbound
`EntityChanged` events to JSON text frames.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

from sidestage.actor import QueueListener
from sidestage.entity import EntityId
from sidestage.events import EntityChanged

if TYPE_CHECKING:
    from sidestage.campaign import Campaign


logger = logging.getLogger("sidestage.ws")


class WsConnection:
    """ws-route-connection: Per-socket state for the WS endpoint.

    Each accepted socket gets one instance. Holds one outbound queue
    drained by a sender task, and one `QueueListener` per subscribed
    entity id. Frames are JSON text per `events-subscription`.

    .implements: events-subscription, ws-dataflow-subscribe,
                 ws-dataflow-event, ws-dataflow-unsubscribe
    """

    def __init__(self, campaign: Campaign, websocket: WebSocket) -> None:
        self.campaign = campaign
        self.websocket = websocket
        # ws-route-connection: outbound queue shared by every QueueListener
        # this socket registers, plus future direct sends (ack/error frames).
        self._queue: asyncio.Queue[EntityChanged] = asyncio.Queue()
        self._subscriptions: dict[EntityId, QueueListener] = {}

    async def run(self) -> None:
        """Accept the socket and pump frames until disconnect.

        Spawns a sender task and a receiver loop. On any exit walks
        every subscription and unsubscribes from the underlying
        entities (per `ws-dataflow-unsubscribe`).
        """
        await self.websocket.accept()
        sender = asyncio.create_task(self._send_loop())
        try:
            await self._recv_loop()
        finally:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender
            self._unsubscribe_all()

    async def _send_loop(self) -> None:
        """ws-dataflow-event: drain the queue, send as `entity_changed` frames."""
        while True:
            event = await self._queue.get()
            payload: dict[str, Any] = {
                "op": "entity_changed",
                "entity_id": event.entity.id,
                "attributes": list(event.attributes),
            }
            await self.websocket.send_text(json.dumps(payload))

    async def _recv_loop(self) -> None:
        """Read incoming JSON frames and dispatch by `op`."""
        try:
            while True:
                raw = await self.websocket.receive_text()
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("ws: invalid JSON frame: %r", raw)
                    continue
                if not isinstance(frame, dict):
                    logger.warning("ws: non-object frame: %r", frame)
                    continue
                op = frame.get("op")
                if op == "subscribe":
                    self._handle_subscribe(frame)
                elif op == "unsubscribe":
                    self._handle_unsubscribe(frame)
                else:
                    # Mutation ops (`append_message` etc.) land in Phase 2
                    # per `events-subscription-future-mutations`.
                    logger.warning("ws: unknown op %r", op)
        except WebSocketDisconnect:
            return

    def _handle_subscribe(self, frame: dict[str, Any]) -> None:
        """ws-dataflow-subscribe: resolve entity and register listener.

        Idempotent: a repeated subscribe for the same id is a no-op
        (we already hold a listener — the client's intent is unchanged).
        Missing or unknown entity ids are logged and ignored; the spec
        does not promise an error frame in Phase 1.
        """
        entity_id_raw = frame.get("entity_id")
        if not isinstance(entity_id_raw, str):
            logger.warning("ws: subscribe missing entity_id")
            return
        eid = EntityId(entity_id_raw)
        if eid in self._subscriptions:
            return
        entity = self.campaign.factory.get(eid)
        if entity is None:
            logger.warning("ws: subscribe unknown entity %r", entity_id_raw)
            return
        listener = QueueListener(self._queue)
        entity.subscribe(listener)
        self._subscriptions[eid] = listener

    def _handle_unsubscribe(self, frame: dict[str, Any]) -> None:
        """ws-dataflow-unsubscribe: drop the listener for entity_id."""
        entity_id_raw = frame.get("entity_id")
        if not isinstance(entity_id_raw, str):
            return
        eid = EntityId(entity_id_raw)
        listener = self._subscriptions.pop(eid, None)
        if listener is None:
            return
        entity = self.campaign.factory.get(eid)
        if entity is not None:
            entity.unsubscribe(listener)

    def _unsubscribe_all(self) -> None:
        """Walk every subscription and unsubscribe on disconnect."""
        for eid, listener in list(self._subscriptions.items()):
            entity = self.campaign.factory.get(eid)
            if entity is not None:
                entity.unsubscribe(listener)
        self._subscriptions.clear()
