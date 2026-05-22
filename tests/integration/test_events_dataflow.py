"""Integration: listener-driven NPC cycle, entity-level only.

alice sends "Hi" to a SimpleScene shared with bob (StubActor). The scene
fires `EntityChanged`; bob's `Character.notify` reacts, asks his actor for
a response, and republishes it via `self.say`. The second `EntityChanged`
is delivered to alice as a subscriber. We assert at the entity layer — no
FastAPI, no SSE, no TestClient.

.tests: events-dataflow, character-notify-react, character-say,
        simple-scene-init-subscribes-characters,
        events-pattern-subscription, events-async-tasks-idle
"""

from __future__ import annotations

import pytest

from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.entity import EntityId, EntityType
from sidestage.events import EntityChanged
from sidestage.message import Message
from sidestage.scene import SimpleScene

pytestmark = pytest.mark.integration


async def test_events_dataflow() -> None:
    campaign = Campaign(name="test")

    alice = Character(
        Character.Model(
            id=EntityId("alice"),
            name="Alice",
            type=EntityType.CHARACTER,
            body="A curious traveler.",
            owner="user",
        ),
        campaign,
    )
    campaign.add(alice)

    bob = Character(
        Character.Model(
            id=EntityId("bob"),
            name="Bob",
            type=EntityType.CHARACTER,
            body="*nods quietly*",
            owner="stub",
        ),
        campaign,
    )
    campaign.add(bob)

    scene = SimpleScene(
        SimpleScene.Model(
            id=EntityId("parlor"),
            name="Parlor",
            type=EntityType.SCENE,
            body="A quiet room.",
            characters=[EntityId("alice"), EntityId("bob")],
        ),
        campaign,
    )
    campaign.add(scene)

    notify_events: list[EntityChanged] = []
    original_notify = alice.notify

    async def spy_notify(event: EntityChanged) -> None:
        notify_events.append(event)
        await original_notify(event)

    object.__setattr__(alice, "notify", spy_notify)

    # The single mutation surface: `scene.messages.append(msg)`. The
    # EntityList wrapper emits EntityChanged; bob's Character.notify
    # picks it up, asks his StubActor, and publishes via self.say.
    scene.messages.append(Message(sender_id=alice.id, body="Hi"))
    await scene.idle()

    assert len(scene.messages) == 2, (
        "events-dataflow: bob's response must be appended back to the "
        "scene via the listener cycle; "
        f"got {len(scene.messages)} messages"
    )
    assert scene.messages[0].sender_id == alice.id, (
        "events-dataflow: alice's input must be at index 0; "
        f"got sender_id={scene.messages[0].sender_id}"
    )
    assert scene.messages[1].sender_id == bob.id, (
        "character-notify-react: bob (stub) must reply via actor.respond "
        "and publish back to the scene via self.say; "
        f"got sender_id={scene.messages[1].sender_id}"
    )
    assert scene.messages[1].body == "*nods quietly*", (
        "character-notify-react: bob's StubActor returns `bob.body`; "
        f"got body={scene.messages[1].body!r}"
    )
    assert any(
        e.entity is scene
        and "messages" in e.attributes
        and e.entity.messages[-1].sender_id == bob.id
        for e in notify_events
    ), (
        "events-pattern-subscription: alice (subscribed to scene via "
        "SimpleScene.__init__) must receive an EntityChanged carrying "
        f"bob's response; got notify_events={notify_events}"
    )
