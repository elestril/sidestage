"""Integration: listener-driven NPC cycle, entity-level only.

alice sends "Hi" to a SimpleScene shared with bob (StubActor). The scene
fires `EntityChanged`; bob's `Character.notify` reacts, asks his actor for
a response, and appends it back. The second `EntityChanged` is delivered
to alice as a subscriber. We assert at the entity layer — no FastAPI,
no SSE, no TestClient.

.tests: events-dataflow, character-notify-react,
        simple-scene-init-subscribes-characters,
        events-pattern-subscription, events-async-tasks-idle
"""

from __future__ import annotations

import pytest

from sidestage.character import Character
from sidestage.entity import EntityId
from sidestage.events import EntityChanged
from sidestage.message import Message
from sidestage.scene import SimpleScene


pytestmark = pytest.mark.integration


async def test_events_dataflow() -> None:
    alice = Character(
        id=EntityId("alice"),
        name="Alice",
        body="A curious traveler.",
        owner="user",
    )
    bob = Character(
        id=EntityId("bob"),
        name="Bob",
        body="*nods quietly*",
        owner="stub",
    )
    scene = SimpleScene(
        id=EntityId("parlor"),
        name="Parlor",
        body="A quiet room.",
        characters=[alice, bob],
    )

    notify_events: list[EntityChanged] = []
    original_notify = alice.notify

    async def spy_notify(event: EntityChanged) -> None:
        notify_events.append(event)
        await original_notify(event)

    object.__setattr__(alice, "notify", spy_notify)

    scene.append(Message(sender=alice, body="Hi"))
    await scene.idle()

    assert len(scene.messages) == 2, (
        "events-dataflow: bob's response must be appended back to the "
        "scene via the listener cycle; "
        f"got {len(scene.messages)} messages"
    )
    assert scene.messages[0].sender is alice, (
        "events-dataflow: alice's input must be at index 0; "
        f"got sender={scene.messages[0].sender}"
    )
    assert scene.messages[1].sender is bob, (
        "character-notify-react: bob (stub) must reply via actor.respond "
        "and append back to the scene; "
        f"got sender={scene.messages[1].sender}"
    )
    assert scene.messages[1].body == "*nods quietly*", (
        "character-notify-react: bob's StubActor returns "
        "`Message(sender=bob, body=bob.body)`; "
        f"got body={scene.messages[1].body!r}"
    )
    assert any(
        e.entity is scene
        and "messages" in e.attributes
        and e.entity.messages[-1].sender is bob
        for e in notify_events
    ), (
        "events-pattern-subscription: alice (subscribed to scene via "
        "SimpleScene.__init__) must receive an EntityChanged carrying "
        f"bob's response; got notify_events={notify_events}"
    )
