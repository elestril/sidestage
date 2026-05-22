"""ws: WebSocket connection management.

Per `specs/events.md#events-subscription` and
`specs/backend.md#backend-ws`.

Owns the per-socket state for the multiplexed `/api/campaigns/{cid}/ws`
endpoint. Each accepted socket gets one `WsConnection`. The connection
parses incoming JSON frames, dispatches by `op`, owns one
`QueueListener` per subscribed entity, and serialises outbound
`EntityChanged` events (with their delta payloads) to JSON text frames.

Wire schema lives in `specs/events.md#events-subscription`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import asdict, is_dataclass
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

    The outbound queue carries either `EntityChanged` (from subscribed
    entities) or dict-typed direct-send frames (acks, errors, subscribed
    replies) that the sender forwards verbatim.

    .implements: events-subscription, backend-ws
    """

    def __init__(self, campaign: Campaign, websocket: WebSocket) -> None:
        self.campaign = campaign
        self.websocket = websocket
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._subscriptions: dict[EntityId, QueueListener] = {}

    async def run(self) -> None:
        """Accept the socket and pump frames until disconnect."""
        await self.websocket.accept()
        sender = asyncio.create_task(self._send_loop())
        try:
            await self._recv_loop()
        finally:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender
            self._unsubscribe_all()

    # ---------------- send / serialisation -------------------------------

    async def _send_loop(self) -> None:
        """Drain the queue, serialise as wire frames."""
        while True:
            item = await self._queue.get()
            if isinstance(item, EntityChanged):
                payload = self._serialise_event(item)
            else:
                # Already a fully-formed dict frame (ack / error / subscribed).
                payload = item
            await self.websocket.send_text(json.dumps(payload))

    def _serialise_event(self, event: EntityChanged) -> dict[str, Any]:
        """Build the `entity_changed` wire frame from an in-process event.

        Carries the delta payloads — `ListDelta` is `{start, len, items}`,
        `ScalarDelta` is `{value}`.

        .implements: backend-ws-send, events-attribute-deltas
        """
        deltas_out: dict[str, Any] = {}
        for attr, delta in event.deltas.items():
            if is_dataclass(delta) and not isinstance(delta, type):
                deltas_out[attr] = asdict(delta)
            else:
                deltas_out[attr] = delta
        # Items inside a ListDelta might be Pydantic Models — `asdict`
        # leaves them as-is, but JSON-encoding needs `.model_dump()`. Walk
        # items per-attr.
        for _attr, payload in deltas_out.items():
            if isinstance(payload, dict) and "items" in payload:
                payload["items"] = [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in payload["items"]
                ]
        return {
            "op": "entity_changed",
            "entity_id": event.entity.id,
            "attributes": list(event.attributes),
            "deltas": deltas_out,
        }

    async def _send_frame(self, frame: dict[str, Any]) -> None:
        """Queue a direct-send frame (ack/error/subscribed) on the sender."""
        await self._queue.put(frame)

    # ---------------- receive / dispatch ---------------------------------

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
                    await self._handle_subscribe(frame)
                elif op == "unsubscribe":
                    self._handle_unsubscribe(frame)
                elif op == "entity_action":
                    await self._handle_entity_action(frame)
                else:
                    logger.warning("ws: unknown op %r", op)
        except WebSocketDisconnect:
            return

    async def _handle_subscribe(self, frame: dict[str, Any]) -> None:
        """ws-dataflow-subscribe: resolve, subscribe, reply with initial state.

        Accepts either a single `entity_id` (legacy) or a list of
        `entity_ids`. Sends back one `subscribed` reply carrying each
        requested entity's current `Entity.Model` payload.

        .implements: backend-ws-subscribe
        """
        request_id = frame.get("request_id")
        ids_raw = frame.get("entity_ids")
        if ids_raw is None and isinstance(frame.get("entity_id"), str):
            ids_raw = [frame["entity_id"]]
        if not isinstance(ids_raw, list):
            logger.warning("ws: subscribe missing entity_ids")
            return
        states: list[dict[str, Any]] = []
        for raw in ids_raw:
            if not isinstance(raw, str):
                continue
            eid = EntityId(raw)
            entity = self.campaign.get(eid)
            if entity is None:
                logger.warning("ws: subscribe unknown entity %r", raw)
                states.append({"entity_id": raw, "model": None})
                continue
            if eid not in self._subscriptions:
                listener = QueueListener(self._queue)
                entity.subscribe(listener)
                self._subscriptions[eid] = listener
            states.append(
                {
                    "entity_id": raw,
                    "model": entity.model.model_dump(),
                }
            )
        await self._send_frame(
            {
                "op": "subscribed",
                "request_id": request_id,
                "states": states,
            }
        )

    def _handle_unsubscribe(self, frame: dict[str, Any]) -> None:
        """ws-dataflow-unsubscribe: drop listener(s)."""
        ids_raw = frame.get("entity_ids")
        if ids_raw is None and isinstance(frame.get("entity_id"), str):
            ids_raw = [frame["entity_id"]]
        if not isinstance(ids_raw, list):
            return
        for raw in ids_raw:
            if not isinstance(raw, str):
                continue
            eid = EntityId(raw)
            listener = self._subscriptions.pop(eid, None)
            if listener is None:
                continue
            entity = self.campaign.get(eid)
            if entity is not None:
                entity.unsubscribe(listener)

    async def _handle_entity_action(self, frame: dict[str, Any]) -> None:
        """ws-dataflow-entity-action: dispatch to `@action`-decorated method.

        Validates the action against `type(entity)._actions`. Awaits the
        method, sends `ack` on success or `error` on validation/dispatch
        failure (per `events-errors-action-failure`).

        .implements: backend-ws-entity-action
        """
        request_id = frame.get("request_id")
        entity_id_raw = frame.get("entity_id")
        action_name = frame.get("action")
        kwargs = frame.get("kwargs") or {}
        if not isinstance(entity_id_raw, str) or not isinstance(action_name, str):
            await self._send_frame(
                {
                    "op": "error",
                    "request_id": request_id,
                    "code": "bad_frame",
                    "message": "missing entity_id/action",
                }
            )
            return
        entity = self.campaign.get(EntityId(entity_id_raw))
        if entity is None:
            await self._send_frame(
                {
                    "op": "error",
                    "request_id": request_id,
                    "code": "unknown_entity",
                    "message": f"unknown entity_id {entity_id_raw!r}",
                }
            )
            return
        if action_name not in type(entity)._actions:
            await self._send_frame(
                {
                    "op": "error",
                    "request_id": request_id,
                    "code": "unknown_action",
                    "message": f"unknown action {action_name!r}",
                }
            )
            return
        try:
            result = getattr(entity, action_name)(**kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.exception("ws: entity_action raised")
            await self._send_frame(
                {
                    "op": "error",
                    "request_id": request_id,
                    "code": "action_failed",
                    "message": str(exc),
                }
            )
            return
        await self._send_frame({"op": "ack", "request_id": request_id})

    # ---------------- teardown -----------------------------------------

    def _unsubscribe_all(self) -> None:
        """Walk every subscription and unsubscribe on disconnect."""
        for eid, listener in list(self._subscriptions.items()):
            entity = self.campaign.get(eid)
            if entity is not None:
                entity.unsubscribe(listener)
        self._subscriptions.clear()
