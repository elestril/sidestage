from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidestage.actor import NpcActor, UserActor
from sidestage.campaign import Campaign
from sidestage.character import Character
from sidestage.chat_service import ChatService
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.llm_client import LLMMessage
from sidestage.message_repository import InMemoryMessageRepository
from sidestage.scene import Scene
from sidestage.ws import create_ws_router


class _FixedTokenLLMClient:
    """Stub LLMClient that yields a fixed sequence of tokens.

    Used in place of a real LLM client so that Character/NpcActor.chat_stream
    deterministically emits known tokens for assertions.
    """

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]:
        for token in self._tokens:
            yield token


def _make_user_character(char_id: str = "bob", name: str = "Bob") -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=f"You are {name}.",
        actor=UserActor(),
    )


def _make_npc_character(
    char_id: str = "elara",
    name: str = "Elara",
    tokens: list[str] | None = None,
) -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=f"You are {name}.",
        actor=NpcActor(
            _FixedTokenLLMClient(tokens if tokens is not None else ["hello", " world"]),
            model=None,
        ),
    )


def _make_scene(
    active_character_ids: list[CharacterId],
    scene_id: str = "scene1",
    campaign_id: str = "camp1",
) -> Scene:
    return Scene(
        id=SceneId(scene_id),
        campaign_id=CampaignId(campaign_id),
        name="Tavern",
        description="A dim tavern.",
        active_character_ids=active_character_ids,
        messages=[],
    )


def _make_campaign(
    scene: Scene,
    characters: list[Character],
    campaign_id: str = "camp1",
) -> Campaign:
    return Campaign(
        id=CampaignId(campaign_id),
        name="Lost Mines",
        active_scene_id=scene.id,
        characters={c.id: c for c in characters},
        scenes={scene.id: scene},
    )


def _build_world(
    npc_tokens: list[str] | None = None,
) -> tuple[
    Campaign,
    Scene,
    Character,
    Character,
    InMemoryMessageRepository,
    ChatService,
    TestClient,
]:
    bob = _make_user_character("bob", "Bob")
    elara = _make_npc_character(
        "elara", "Elara", tokens=npc_tokens if npc_tokens is not None else ["hello", " world"]
    )
    scene = _make_scene(active_character_ids=[bob.id, elara.id])
    campaign = _make_campaign(scene, [bob, elara])
    campaigns = {campaign.id: campaign}
    repo = InMemoryMessageRepository()
    chat_service = ChatService(campaigns, repo)
    app = FastAPI()
    app.include_router(create_ws_router(campaigns, chat_service, repo))
    client = TestClient(app)
    return campaign, scene, bob, elara, repo, chat_service, client


def test_connect_as_valid_user_character_does_not_raise():
    _, _, bob, _, _, _, client = _build_world()

    try:
        with client.websocket_connect(
            f"/campaigns/camp1/ws?character_id={bob.id.value}"
        ) as ws:
            # Accepting the connection is the invariant under test.
            assert ws is not None, (
                "WS /campaigns/{campaign_id}/ws?character_id=... must accept the "
                "connection (return a usable WebSocket object) when the campaign "
                "exists, the character exists, character.actor is UserActor, and "
                "the character is in scene.active_character_ids; got a falsy "
                "websocket object instead."
            )
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            "WS /campaigns/{campaign_id}/ws?character_id=... must accept the "
            "connection without raising when the campaign exists, the character "
            "exists, character.actor is UserActor, and the character is in "
            "scene.active_character_ids. Connecting as the valid user character "
            f"'bob' raised {type(exc).__name__}: {exc!r}."
        ) from exc


def test_send_message_first_frame_is_user_echo_message_frame():
    _, _, bob, _, _, _, client = _build_world()

    with client.websocket_connect(
        f"/campaigns/camp1/ws?character_id={bob.id.value}"
    ) as ws:
        ws.send_json({"type": "send_message", "content": "I open the door."})
        first = ws.receive_json()

    assert first.get("type") == "message", (
        "After receiving a send_message client frame, the WebSocket handler must "
        "first echo the user message back as a 'message' frame "
        "(MessageFrame.to_dict() with type='message') BEFORE any NPC stream "
        f"frames; got first frame type={first.get('type')!r}, full frame={first!r}."
    )
    assert first.get("character_id") == "bob", (
        "The user-echo MessageFrame must carry the user's CharacterId.value as "
        "its 'character_id' field; expected 'bob' (the connecting user "
        f"character), got {first.get('character_id')!r} (full frame: {first!r})."
    )
    assert first.get("content") == "I open the door.", (
        "The user-echo MessageFrame must carry the exact 'content' that the "
        "client sent in the send_message frame; expected 'I open the door.', "
        f"got {first.get('content')!r} (full frame: {first!r})."
    )


def test_send_message_npc_stream_frames_in_correct_order():
    _, _, bob, elara, _, _, client = _build_world(npc_tokens=["hello", " world"])

    with client.websocket_connect(
        f"/campaigns/camp1/ws?character_id={bob.id.value}"
    ) as ws:
        ws.send_json({"type": "send_message", "content": "I open the door."})
        # Drain the user echo frame.
        echo = ws.receive_json()
        assert echo.get("type") == "message", (
            "Precondition for streaming-order test: the first frame after a "
            "send_message must be the user-echo 'message' frame; got "
            f"{echo!r}."
        )

        start = ws.receive_json()
        deltas: list[dict] = []
        while True:
            frame = ws.receive_json()
            if frame.get("type") == "stream_delta":
                deltas.append(frame)
                continue
            end = frame
            break

    assert start.get("type") == "stream_start", (
        "Immediately after the user echo MessageFrame, for each NPC character "
        "in scene.active_character_ids the handler must send a 'stream_start' "
        f"frame; got frame type={start.get('type')!r}, full frame={start!r}."
    )
    assert start.get("character_id") == elara.id.value, (
        "The stream_start frame for an NPC must include 'character_id' equal "
        "to that NPC's CharacterId.value; expected "
        f"{elara.id.value!r} (Elara), got {start.get('character_id')!r} "
        f"(full frame: {start!r})."
    )
    assert start.get("character_name") == elara.name, (
        "The stream_start frame for an NPC must include 'character_name' "
        f"equal to that NPC's Character.name; expected {elara.name!r}, got "
        f"{start.get('character_name')!r} (full frame: {start!r})."
    )

    assert len(deltas) >= 1, (
        "Between stream_start and stream_end the handler must emit one or "
        "more 'stream_delta' frames (one per token yielded by "
        "character.chat_stream). The stub NPC yields the tokens "
        "['hello', ' world'], so at least 1 delta frame is required; got "
        f"{len(deltas)} delta frame(s): {deltas!r}."
    )
    for d in deltas:
        assert d.get("character_id") == elara.id.value, (
            "Every stream_delta frame for an NPC's stream must carry that "
            f"NPC's CharacterId.value as 'character_id'; expected "
            f"{elara.id.value!r}, got {d.get('character_id')!r} (delta "
            f"frame: {d!r})."
        )
        assert "token" in d, (
            "Every stream_delta frame must include a 'token' field "
            f"(StreamDelta.to_dict()); got delta frame without token: {d!r}."
        )

    concatenated = "".join(d["token"] for d in deltas)
    assert concatenated == "hello world", (
        "The concatenation of all stream_delta tokens for an NPC must equal "
        "the full content produced by the NPC's chat_stream; the stub NPC "
        "yields ['hello', ' world'] so the concatenation must equal "
        f"'hello world', got {concatenated!r}."
    )

    assert end.get("type") == "stream_end", (
        "After the final stream_delta the handler must send a 'stream_end' "
        f"frame for that NPC; got frame type={end.get('type')!r}, full "
        f"frame={end!r}."
    )
    assert end.get("character_id") == elara.id.value, (
        "The stream_end frame must carry the NPC's CharacterId.value as "
        f"'character_id'; expected {elara.id.value!r}, got "
        f"{end.get('character_id')!r} (full frame: {end!r})."
    )
    assert "message_id" in end and end.get("message_id"), (
        "The stream_end frame must include a non-empty 'message_id' field "
        "equal to the freshly-created NPC Message's MessageId.value "
        f"(StreamEnd.to_dict()); got end frame: {end!r}."
    )


async def test_npc_message_persisted_to_repository_after_stream_end():
    _, scene, bob, elara, repo, _, client = _build_world(
        npc_tokens=["hello", " world"]
    )

    with client.websocket_connect(
        f"/campaigns/camp1/ws?character_id={bob.id.value}"
    ) as ws:
        ws.send_json({"type": "send_message", "content": "I open the door."})
        # Drain frames until we see stream_end.
        while True:
            frame = ws.receive_json()
            if frame.get("type") == "stream_end":
                break

    persisted = await repo.get_by_scene(scene.id)
    npc_messages = [m for m in persisted if m.character_id == elara.id]

    assert len(npc_messages) == 1, (
        "After the NPC stream completes (stream_end emitted), the WebSocket "
        "handler must have persisted exactly one NPC Message via "
        "`await repo.append(npc_msg)`. Expected 1 NPC message in "
        f"repo.get_by_scene({scene.id!r}) for character_id {elara.id!r}, got "
        f"{len(npc_messages)}: {npc_messages!r} (all messages: {persisted!r})."
    )
    assert npc_messages[0].content == "hello world", (
        "The persisted NPC Message must have content equal to the "
        "concatenation of all tokens yielded by the NPC's chat_stream. The "
        "stub NPC yields ['hello', ' world'] so the persisted content must "
        f"be 'hello world'; got {npc_messages[0].content!r}."
    )
    assert npc_messages[0].scene_id == scene.id, (
        "The persisted NPC Message must be created with scene_id equal to "
        f"the active scene's id; expected {scene.id!r}, got "
        f"{npc_messages[0].scene_id!r}."
    )


def test_connect_with_unknown_character_id_sends_error_frame():
    _, _, _, _, _, _, client = _build_world()

    received: dict | None = None
    try:
        with client.websocket_connect(
            "/campaigns/camp1/ws?character_id=does_not_exist"
        ) as ws:
            try:
                received = ws.receive_json()
            except Exception:
                received = None
    except Exception:
        # The handler may close the connection after sending the error frame,
        # which can manifest as an exception when entering/exiting the context
        # manager. The invariant is that we received an error frame BEFORE the
        # close, so we still inspect `received` below.
        pass

    assert received is not None, (
        "Connecting to WS /campaigns/{campaign_id}/ws with a character_id "
        "that is not in campaign.characters must result in the server sending "
        "an ErrorFrame ({'type': 'error', 'detail': ...}) BEFORE closing the "
        "connection; the test client received no JSON frame at all."
    )
    assert received.get("type") == "error", (
        "When character_id is unknown, the first (and only) frame the server "
        "sends must be an ErrorFrame with type='error' (per "
        f"ErrorFrame.to_dict()); got frame={received!r}."
    )


def test_connect_as_npc_character_sends_error_frame():
    _, _, _, elara, _, _, client = _build_world()

    received: dict | None = None
    try:
        with client.websocket_connect(
            f"/campaigns/camp1/ws?character_id={elara.id.value}"
        ) as ws:
            try:
                received = ws.receive_json()
            except Exception:
                received = None
    except Exception:
        # See note above: connection close after error frame is acceptable.
        pass

    assert received is not None, (
        "Connecting to WS /campaigns/{campaign_id}/ws as a character whose "
        "actor is NpcActor (not UserActor) must result in the server sending "
        "an ErrorFrame BEFORE closing the connection; the test client "
        "received no JSON frame at all (connecting as NPC character "
        f"{elara.id.value!r})."
    )
    assert received.get("type") == "error", (
        "When the connecting character's actor is not a UserActor, the first "
        "(and only) frame the server sends must be an ErrorFrame with "
        f"type='error'; got frame={received!r}."
    )
