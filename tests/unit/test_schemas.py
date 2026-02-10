from datetime import datetime, timezone

from sidestage.models import EventModel, EventType
from sidestage.schemas import ChatResponse


def test_chat_response_references_event_model():
    """ChatResponse schema references EventModel, not ChatMessageModel."""
    now = datetime.now(timezone.utc)
    event = EventModel(
        id="evt_1",
        name="Test Message",
        body="hello",
        event_type=EventType.CHAT_MESSAGE,
        scene_id="scene_1",
        gametime=0,
        walltime=now,
        character_id="char_1",
        actor_id="user",
    )
    resp = ChatResponse(event=event)
    assert resp.event.id == "evt_1"
    assert resp.event.event_type == EventType.CHAT_MESSAGE
