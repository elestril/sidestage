"""Integration test replaying CUJ-1 through CUJ-12 of the Sidestage ttRPG
assistant.

CUJ reference: .claude/plans/sleepy-coalescing-russell.md (section A).

This test boots a real FastAPI app via `sidestage.app.create_app`, populated by
`ConfigLoader` reading a fixture config tree on disk, with the LLM swapped for
a deterministic stub. It exercises the full single-user-with-NPC happy path:

  - CUJ-1/2  config-on-disk -> hydrated `dict[CampaignId, Campaign]`
  - CUJ-3    GET /campaigns
  - CUJ-4    GET /campaigns/{id}
  - CUJ-5    WS /campaigns/{id}/ws?character_id=bob accepts
  - CUJ-6/7  send_message -> server echoes 'message' frame
  - CUJ-8    server emits stream_start -> stream_delta(s) -> stream_end for NPC
  - CUJ-10   concatenated stream_delta tokens equal full NPC content
  - CUJ-11   GET .../messages returns persisted messages in order
  - CUJ-12   second send_message round still triggers NPC stream
"""

from pathlib import Path
from typing import AsyncIterator

from fastapi.testclient import TestClient

from sidestage.app import create_app
from sidestage.config_loader import ConfigLoader
from sidestage.ids import CampaignId
from sidestage.llm_client import LLMMessage
from sidestage.message_repository import InMemoryMessageRepository


CAMPAIGN_DIR = "test_campaign"
CAMPAIGN_NAME = "Test Campaign"
SCENE_ID = "opening_scene"
SCENE_NAME = "Opening Scene"
USER_CHAR_ID = "bob"
USER_CHAR_NAME = "Bob"
NPC_CHAR_ID = "elara"
NPC_CHAR_NAME = "Elara"
NPC_TOKENS = ["Hello", " there"]
NPC_FULL_CONTENT = "Hello there"


class FakeLLMClient:
    """Deterministic LLM stub.

    Conforms to the structural `LLMClient` protocol declared in
    `sidestage.llm_client`. `stream` yields a fixed token sequence regardless
    of inputs so NPC streaming output is deterministic across the whole CUJ
    replay (used by both round 1 / CUJ-8 and round 2 / CUJ-12).
    """

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]:
        for token in self._tokens:
            yield token


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _build_fixture_config(config_root: Path) -> None:
    """Materialize the on-disk config tree expected by `ConfigLoader`.

    Layout (mirrors the production layout under `./configs/`):

      <config_root>/
        sidestage.yaml                 # default_model
        <CAMPAIGN_DIR>/
          campaign.yaml                # name, active_scene_id
          characters/
            bob.md                     # frontmatter: name, actor=user
            elara.md                   # frontmatter: name, actor=npc
          scenes/
            opening_scene.md           # frontmatter: name, active_characters

    The exact YAML/frontmatter keys here MUST match what
    `sidestage.config_loader.ConfigLoader` reads:
      - server YAML key:    `default_model`
      - campaign YAML keys: `name`, `active_scene_id`
      - character keys:     `name`, `actor` (`user` | `npc`), optional `model`
      - scene keys:         `name`, `active_characters` (list of CharacterId
                            stems)
      - File stem == ID (e.g. `bob.md` -> CharacterId('bob')).
    """
    _write(config_root / "sidestage.yaml", "default_model: test-model\n")
    _write(
        config_root / CAMPAIGN_DIR / "campaign.yaml",
        f"name: {CAMPAIGN_NAME}\nactive_scene_id: {SCENE_ID}\n",
    )
    _write(
        config_root / CAMPAIGN_DIR / "characters" / f"{USER_CHAR_ID}.md",
        (
            "---\n"
            f"name: {USER_CHAR_NAME}\n"
            "actor: user\n"
            "---\n"
            "Bob is a user-controlled adventurer.\n"
        ),
    )
    _write(
        config_root / CAMPAIGN_DIR / "characters" / f"{NPC_CHAR_ID}.md",
        (
            "---\n"
            f"name: {NPC_CHAR_NAME}\n"
            "actor: npc\n"
            "---\n"
            "Elara is an NPC sage.\n"
        ),
    )
    _write(
        config_root / CAMPAIGN_DIR / "scenes" / f"{SCENE_ID}.md",
        (
            "---\n"
            f"name: {SCENE_NAME}\n"
            "active_characters:\n"
            f"  - {USER_CHAR_ID}\n"
            f"  - {NPC_CHAR_ID}\n"
            "---\n"
            "A small clearing, lit by morning sun.\n"
        ),
    )


def _drain_npc_stream(ws) -> tuple[dict, list[dict], dict]:
    """Read frames until stream_end. Returns (start, deltas, end).

    Caller is responsible for first draining the user-echo MessageFrame so the
    next frame is the NPC's stream_start.
    """
    start = ws.receive_json()
    deltas: list[dict] = []
    while True:
        frame = ws.receive_json()
        if frame.get("type") == "stream_delta":
            deltas.append(frame)
            continue
        return start, deltas, frame


def test_full_cuj_single_user_chat_with_npc(tmp_path: Path) -> None:
    """Replay CUJ-1 .. CUJ-12 end-to-end through the real FastAPI app.

    Bootstraps the app the same way `sidestage.app.main` does (ConfigLoader ->
    campaigns + create_app + InMemoryMessageRepository), but with a
    `FakeLLMClient` that yields the fixed tokens ['Hello', ' there'] so NPC
    streaming output is deterministic.
    """
    # CUJ-1, CUJ-2: server starts with a config root and loads all campaigns.
    _build_fixture_config(tmp_path)
    loader = ConfigLoader(tmp_path)
    server_config = loader.load_server_config()
    assert server_config.default_model == "test-model", (
        "CUJ-1: ConfigLoader.load_server_config() must read "
        "<config_root>/sidestage.yaml and populate ServerConfig.default_model "
        "from the YAML key `default_model`. Fixture wrote "
        "'default_model: test-model', so ServerConfig.default_model must "
        f"equal 'test-model'; got {server_config.default_model!r}."
    )

    fake_llm = FakeLLMClient(NPC_TOKENS)
    campaigns = loader.load_all_campaigns(fake_llm)

    expected_campaign_id = CampaignId(CAMPAIGN_DIR)
    assert expected_campaign_id in campaigns, (
        "CUJ-2: ConfigLoader.load_all_campaigns must return a "
        "dict[CampaignId, Campaign] with one entry per campaign subdirectory "
        "of config_root. The subdirectory name is the CampaignId.value. "
        f"Fixture created subdirectory {CAMPAIGN_DIR!r}, so the returned "
        f"dict must contain key CampaignId({CAMPAIGN_DIR!r}); got keys "
        f"{list(campaigns.keys())!r}."
    )

    repo = InMemoryMessageRepository()
    app = create_app(campaigns, repo)
    client = TestClient(app)

    # CUJ-3: GET /campaigns lists the loaded campaign.
    resp = client.get("/campaigns")
    assert resp.status_code == 200, (
        "CUJ-3: GET /campaigns must return HTTP 200 OK so the React client "
        "can list campaigns at app startup. The endpoint is wired into the "
        "app by `create_app` via `sidestage.rest.create_router`. Got "
        f"status={resp.status_code}, body={resp.text!r}."
    )
    listing = resp.json()
    assert isinstance(listing, list), (
        "CUJ-3: GET /campaigns must return a JSON array (list of campaign "
        "summaries) per `sidestage.rest.list_campaigns`; got "
        f"{type(listing).__name__}: {listing!r}."
    )
    listed_ids = [c.get("id") for c in listing]
    assert CAMPAIGN_DIR in listed_ids, (
        "CUJ-3: GET /campaigns must include every loaded campaign's "
        "CampaignId.value under the 'id' key. The fixture loaded one "
        f"campaign with id {CAMPAIGN_DIR!r}; expected {CAMPAIGN_DIR!r} in "
        f"the listing, got ids {listed_ids!r} (full body: {listing!r})."
    )

    # CUJ-4: GET /campaigns/{id} returns campaign detail.
    resp = client.get(f"/campaigns/{CAMPAIGN_DIR}")
    assert resp.status_code == 200, (
        "CUJ-4: GET /campaigns/{campaign_id} must return HTTP 200 OK for an "
        "existing campaign so the client can show campaign detail before "
        f"connecting. Requested id {CAMPAIGN_DIR!r}; got "
        f"status={resp.status_code}, body={resp.text!r}."
    )
    detail = resp.json()
    assert detail.get("id") == CAMPAIGN_DIR, (
        "CUJ-4: GET /campaigns/{campaign_id} response body must carry the "
        "campaign's id under the 'id' key (CampaignId.value). Expected "
        f"{CAMPAIGN_DIR!r}; got {detail.get('id')!r} (full body: {detail!r})."
    )
    assert detail.get("active_scene_id") == SCENE_ID, (
        "CUJ-4: GET /campaigns/{campaign_id} response body must expose the "
        "campaign's active_scene_id (SceneId.value, sourced from "
        "campaign.yaml's `active_scene_id` key). Expected "
        f"{SCENE_ID!r}; got {detail.get('active_scene_id')!r} (full body: "
        f"{detail!r})."
    )

    # CUJ-5: WebSocket connect as the user character `bob` is accepted.
    ws_url = f"/campaigns/{CAMPAIGN_DIR}/ws?character_id={USER_CHAR_ID}"
    with client.websocket_connect(ws_url) as ws:
        # Per `sidestage.ws.create_ws_router`, error conditions cause an
        # immediate ErrorFrame frame followed by close. A successful connect
        # MUST NOT send an error frame as the first message — the server
        # waits for client input. We send a send_message and inspect the
        # first frame; if it's an error, the connection wasn't accepted.

        # CUJ-6: client sends a chat message.
        ws.send_json(
            {"type": "send_message", "content": "I open the dungeon door."}
        )

        # CUJ-7: server echoes the user message as a 'message' frame FIRST.
        first = ws.receive_json()
        assert first.get("type") != "error", (
            "CUJ-5: WS /campaigns/{campaign_id}/ws?character_id=bob must "
            "accept the connection (no ErrorFrame) when the campaign exists, "
            "the character exists, character.actor is UserActor, and the "
            "character is in scene.active_character_ids. Fixture sets all "
            "four invariants; the server returned an error frame as the "
            f"first message instead: {first!r}."
        )
        assert first.get("type") == "message", (
            "CUJ-7: After a `send_message` client frame, the WS handler "
            "MUST first echo the user message back as a `message` frame "
            "(MessageFrame.to_dict() with type='message') before any NPC "
            f"stream frames. Got first frame type={first.get('type')!r}, "
            f"full frame={first!r}."
        )
        assert first.get("character_id") == USER_CHAR_ID, (
            "CUJ-7: The user-echo MessageFrame must carry the connecting "
            "user's CharacterId.value under 'character_id'. Connected as "
            f"{USER_CHAR_ID!r}; got {first.get('character_id')!r} (full "
            f"frame: {first!r})."
        )
        assert first.get("content") == "I open the dungeon door.", (
            "CUJ-7: The user-echo MessageFrame must carry the exact "
            "`content` from the client's send_message frame. Sent "
            "'I open the dungeon door.'; got "
            f"{first.get('content')!r} (full frame: {first!r})."
        )

        # CUJ-8: server streams the NPC's response: stream_start -> deltas ->
        # stream_end. (Only one NPC in this fixture: elara.)
        start, deltas, end = _drain_npc_stream(ws)

        assert start.get("type") == "stream_start", (
            "CUJ-8: Immediately after the user-echo MessageFrame the WS "
            "handler must send a `stream_start` frame for the NPC. Got "
            f"frame type={start.get('type')!r}, full frame={start!r}."
        )
        assert start.get("character_id") == NPC_CHAR_ID, (
            "CUJ-8: The stream_start frame must carry the NPC's "
            "CharacterId.value under 'character_id'. The fixture's only NPC "
            f"is {NPC_CHAR_ID!r}; got {start.get('character_id')!r} (full "
            f"frame: {start!r})."
        )
        assert start.get("character_name") == NPC_CHAR_NAME, (
            "CUJ-8: The stream_start frame must carry the NPC's "
            "Character.name under 'character_name' (loaded from the "
            f"character markdown frontmatter `name`). Expected "
            f"{NPC_CHAR_NAME!r}; got {start.get('character_name')!r} "
            f"(full frame: {start!r})."
        )

        assert len(deltas) == len(NPC_TOKENS), (
            "CUJ-8: Between stream_start and stream_end the WS handler must "
            "emit exactly one `stream_delta` frame per token yielded by "
            f"the NPC's chat_stream. FakeLLMClient yields {NPC_TOKENS!r} "
            f"({len(NPC_TOKENS)} tokens), so exactly {len(NPC_TOKENS)} "
            f"stream_delta frames are required; got {len(deltas)}: {deltas!r}."
        )
        for i, delta in enumerate(deltas):
            assert delta.get("character_id") == NPC_CHAR_ID, (
                "CUJ-8: Every stream_delta frame for an NPC must carry that "
                "NPC's CharacterId.value under 'character_id'. Expected "
                f"{NPC_CHAR_ID!r} for delta index {i}; got "
                f"{delta.get('character_id')!r} (delta: {delta!r})."
            )
            assert delta.get("token") == NPC_TOKENS[i], (
                "CUJ-8: Each stream_delta frame's `token` must be the next "
                "token yielded by the NPC's chat_stream, in order. "
                f"FakeLLMClient yields {NPC_TOKENS!r}; expected token at "
                f"index {i} to be {NPC_TOKENS[i]!r}, got "
                f"{delta.get('token')!r} (delta: {delta!r})."
            )

        # CUJ-10: stream_end terminates the NPC stream and concatenated
        # deltas equal the persisted NPC content.
        assert end.get("type") == "stream_end", (
            "CUJ-10: After the final stream_delta the WS handler must send "
            "a `stream_end` frame for the NPC. Got frame "
            f"type={end.get('type')!r}, full frame={end!r}."
        )
        assert end.get("character_id") == NPC_CHAR_ID, (
            "CUJ-10: The stream_end frame must carry the NPC's "
            f"CharacterId.value under 'character_id'. Expected "
            f"{NPC_CHAR_ID!r}; got {end.get('character_id')!r} (full "
            f"frame: {end!r})."
        )
        assert end.get("message_id"), (
            "CUJ-10: The stream_end frame must include a non-empty "
            "`message_id` equal to the freshly-persisted NPC Message's "
            f"MessageId.value. Got {end.get('message_id')!r} (full frame: "
            f"{end!r})."
        )

        full_content = "".join(d["token"] for d in deltas)
        assert full_content == NPC_FULL_CONTENT, (
            "CUJ-10: The concatenation of all stream_delta `token` values "
            "must equal the NPC's full response content. FakeLLMClient "
            f"yields {NPC_TOKENS!r}, so the concatenation must equal "
            f"{NPC_FULL_CONTENT!r}; got {full_content!r}."
        )

    # CUJ-11: After WS close, GET .../messages returns persisted messages
    # in insertion order: [user message, NPC message].
    resp = client.get(
        f"/campaigns/{CAMPAIGN_DIR}/scenes/{SCENE_ID}/messages"
    )
    assert resp.status_code == 200, (
        "CUJ-11: GET /campaigns/{cid}/scenes/{sid}/messages must return "
        "HTTP 200 OK so the client can rehydrate scene history. Got "
        f"status={resp.status_code}, body={resp.text!r}."
    )
    history = resp.json()
    assert isinstance(history, list) and len(history) == 2, (
        "CUJ-11: After one user message + one NPC stream, the message "
        "history endpoint must return exactly 2 messages (the user message "
        "and the NPC message), in insertion order. Both `ChatService."
        "handle_user_message` and the WS handler's NPC stream-end branch "
        "MUST have called `repo.append`. Got "
        f"{type(history).__name__} of length "
        f"{len(history) if isinstance(history, list) else 'n/a'}: {history!r}."
    )
    assert history[0].get("character_id") == USER_CHAR_ID, (
        "CUJ-11: The first persisted message must be the user message "
        "(appended by ChatService.handle_user_message before any NPC "
        f"streaming). Expected character_id={USER_CHAR_ID!r}; got "
        f"{history[0].get('character_id')!r} (entry: {history[0]!r})."
    )
    assert history[0].get("content") == "I open the dungeon door.", (
        "CUJ-11: The first persisted message must carry the exact content "
        "the user sent. Expected 'I open the dungeon door.'; got "
        f"{history[0].get('content')!r} (entry: {history[0]!r})."
    )
    assert history[1].get("character_id") == NPC_CHAR_ID, (
        "CUJ-11: The second persisted message must be the NPC message "
        "(appended by the WS handler after stream_end). Expected "
        f"character_id={NPC_CHAR_ID!r}; got "
        f"{history[1].get('character_id')!r} (entry: {history[1]!r})."
    )
    assert history[1].get("content") == NPC_FULL_CONTENT, (
        "CUJ-11: The persisted NPC message's content must equal the "
        "concatenation of all tokens yielded by the NPC's chat_stream. "
        f"Expected {NPC_FULL_CONTENT!r}; got "
        f"{history[1].get('content')!r} (entry: {history[1]!r})."
    )

    # CUJ-12: Re-open the WebSocket and send a second message. The NPC must
    # respond again (history now has 3+ messages). The server MUST treat
    # subsequent send_message frames within / across connections the same
    # way: echo + per-NPC stream.
    with client.websocket_connect(ws_url) as ws:
        ws.send_json(
            {"type": "send_message", "content": "I look around carefully."}
        )

        echo = ws.receive_json()
        assert echo.get("type") == "message", (
            "CUJ-12: On a second user message (after closing & re-opening "
            "the WebSocket), the server MUST again echo the user message "
            "back as a `message` frame before any NPC stream frames. Got "
            f"{echo!r}."
        )
        assert echo.get("content") == "I look around carefully.", (
            "CUJ-12: The second-round user-echo MessageFrame must carry "
            "the content of the SECOND send_message ('I look around "
            f"carefully.'); got {echo.get('content')!r} (full frame: "
            f"{echo!r})."
        )

        start2 = ws.receive_json()
        assert start2.get("type") == "stream_start", (
            "CUJ-12: The conversation must continue: after a second user "
            "message the WS handler must again emit a `stream_start` frame "
            "for the NPC, proving the server loops back into NPC "
            f"orchestration. Got frame type={start2.get('type')!r}, full "
            f"frame={start2!r}."
        )
        assert start2.get("character_id") == NPC_CHAR_ID, (
            "CUJ-12: The second-round stream_start must again identify the "
            f"NPC by CharacterId.value. Expected {NPC_CHAR_ID!r}; got "
            f"{start2.get('character_id')!r} (full frame: {start2!r})."
        )
