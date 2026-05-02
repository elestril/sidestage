# Plan: Core Architecture — Single User, Single Agent CUJ

## Context

Sidestage is a greenfield agentic ttRPG assistant. We're designing the core architecture starting from the simplest CUJ (1 user chatting with NPC characters in a scene), building toward multi-agent, multi-user scenarios.

**Stack**: Python, FastAPI (REST read-only + WS), LiteLLM, FalkorDB (later), React frontend.

---

## 1. Dev Planning Loop

Traceable chain: **CUJ -> design doc -> external docs -> test invariants -> code**.

1. **CUJ narrative** — labeled step-by-step user journey (section A below)
2. **Logic flow** — maps each CUJ label to public methods + state transitions (section B)
3. **Per-class public methods** — derived from the logic flow (section C)
4. **Test invariants** — one per public method behavior, directly implementable
5. **TDD cycle** — `testwriter` (red) -> `coder` (green) -> refactor only if requested

### Planning loop lessons (from this session)

- **CUJ-first, not class-first.** The CUJ defines what the system must do. The logic flow maps that to method calls. Class interfaces are *derived*, not invented.
- **Label everything.** Every CUJ step gets an unambiguous label (CUJ-1, CUJ-2...). Logic flow references those labels. Test invariants reference the methods. The chain is traceable.
- **Test invariants must be implementable.** Each one specifies: given X, call Y, expect Z. Not "Campaign holds characters" but "campaign.get_character(CharacterId('bob')) returns the bob Character object."

---

## 2. Config Directory Structure

The server takes a working directory (`./configs/` by default). All campaign/scene/character definitions are files on disk. The API is read-only for these resources.

```
configs/
  sidestage.yaml                          # Global server config
  dragons_lair/                           # A campaign directory
    campaign.yaml                         # Campaign metadata
    characters/
      bob.md                              # Player character (USER)
      elara.md                            # NPC
      thrain.md                           # NPC
      sly.md                              # NPC
    scenes/
      dungeon_entrance.md                 # Scene file (frontmatter + description)
```

### `sidestage.yaml`
```yaml
default_model: claude-sonnet-4-20250514
```

### `campaign.yaml`
```yaml
name: Dragon's Lair
active_scene: dungeon_entrance
```

### `characters/bob.md`
```markdown
---
name: Bob
actor: user
---
A somewhat unremarkable adventurer who stumbled into this quest by accident.
```

### `characters/elara.md`
```markdown
---
name: Elara Moonwhisper
actor: npc
model: claude-sonnet-4-20250514
---
You are Elara Moonwhisper, an elven sage with centuries of arcane knowledge.
You speak in measured, poetic tones and always consider the magical implications of events.
```

### `characters/thrain.md`
```markdown
---
name: Thrain Ironfoot
actor: npc
---
You are Thrain Ironfoot, a gruff dwarven warrior. You are fiercely loyal,
suspicious of magic, and always ready for a fight. You speak bluntly.
```

### `characters/sly.md`
```markdown
---
name: Sly Pocketsnatch
actor: npc
---
You are Sly Pocketsnatch, a halfling rogue with a heart of gold and sticky fingers.
You crack jokes under pressure and always look for the hidden angle.
```

### `scenes/dungeon_entrance.md`
```markdown
---
name: Dungeon Entrance
active_characters:
  - bob
  - elara
  - thrain
  - sly
---
A crumbling stone archway leads into darkness. Cold air seeps from within,
carrying the faint smell of damp earth and something else... something ancient.
```

**ID convention**: file stem = ID (e.g., `bob.md` -> CharacterId("bob")). Campaign ID = directory name.

---

## 3. Package Structure

Flat layout — one file per class, unit tests side by side.

```
pyproject.toml
src/sidestage/
  __init__.py
  ids.py                     # CampaignId, SceneId, CharacterId, MessageId
  actor.py                   # Actor protocol, NpcActor, UserActor
  actor_test.py
  character.py               # Character
  character_test.py
  message.py                 # Message
  message_test.py
  scene.py                   # Scene
  scene_test.py
  campaign.py                # Campaign
  campaign_test.py
  config_loader.py           # ConfigLoader
  config_loader_test.py
  chat_service.py            # ChatService (thin glue)
  chat_service_test.py
  llm_client.py              # LLMClient protocol + LiteLLMClient
  llm_client_test.py
  message_repository.py      # MessageRepository protocol + InMemory
  message_repository_test.py
  protocol.py                # Wire protocol dataclasses
  protocol_test.py
  app.py                     # FastAPI app factory
  rest.py                    # REST routes (read-only)
  rest_test.py
  ws.py                      # WebSocket handler
  ws_test.py
  integration_tests/
    __init__.py
    conftest.py
    test_chat_flow.py
```

Pytest config in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
python_files = "*_test.py test_*.py"
testpaths = ["src/sidestage"]
```

---

## A. CUJ: Single User Chatting With NPC Characters

Precondition: Config files for "Dragon's Lair" exist on disk (section 2).

| Label | Step |
|-------|------|
| **CUJ-1** | Server starts with `./configs/` as working directory. |
| **CUJ-2** | Server loads all campaigns from config. Dragon's Lair is available with 4 characters (Bob=USER, Elara/Thrain/Sly=NPC) and 1 scene (Dungeon Entrance, all 4 active). |
| **CUJ-3** | User opens React app. App calls `GET /campaigns`. User sees "Dragon's Lair". |
| **CUJ-4** | User selects Dragon's Lair. App calls `GET /campaigns/dragons_lair`. App shows active scene "Dungeon Entrance" and the 4 characters. |
| **CUJ-5** | User connects as Bob. App opens `WS /campaigns/dragons_lair/ws?character_id=bob`. Connection accepted. |
| **CUJ-6** | User types "I open the dungeon door." and sends. App sends `{"type":"send_message","content":"I open the dungeon door."}` over WebSocket. |
| **CUJ-7** | Server echoes Bob's message back: `{"type":"message", ...}`. App renders it in chat. |
| **CUJ-8** | Server streams Elara's response: `stream_start` -> `stream_delta`* -> `stream_end`. App renders tokens as they arrive. |
| **CUJ-9** | Server streams Thrain's response (same pattern). App renders. |
| **CUJ-10** | Server streams Sly's response (same pattern). App renders. |
| **CUJ-11** | All messages (Bob's + 3 NPC responses) are persisted. `GET .../messages` returns them in order. |
| **CUJ-12** | User sends another message. Loop back to CUJ-6. NPC characters now see the full conversation history when responding. |

---

## B. Logic Flow (CUJ labels -> methods -> state transitions)

### CUJ-1, CUJ-2: Startup

```
ConfigLoader.load_server_config()
  -> reads sidestage.yaml -> ServerConfig(default_model=...)

ConfigLoader.load_all_campaigns(llm_client)
  -> for each subdirectory in config root:
       reads campaign.yaml -> Campaign shell (id, name, active_scene_id)
       reads characters/*.md -> Character objects
         frontmatter "actor: npc" -> NpcActor(llm_client, model)
         frontmatter "actor: user" -> UserActor()
         body -> character_sheet
       reads scenes/*.md -> Scene objects
         frontmatter active_characters -> list of CharacterId refs
         body -> description
  -> returns dict[CampaignId, Campaign]

State after CUJ-2:
  - Campaign "dragons_lair" in memory
  - Campaign.characters: {bob, elara, thrain, sly}
  - Campaign.scenes: {dungeon_entrance}
  - Campaign.active_scene_id: "dungeon_entrance"
  - Scene.active_character_ids: [bob, elara, thrain, sly]
  - Scene.messages: [] (empty — runtime state)
  - Each NPC Character holds an NpcActor with LLMClient injected
```

### CUJ-3, CUJ-4: REST reads

```
GET /campaigns
  -> app reads campaigns dict, returns [{id, name, active_scene_id}, ...]

GET /campaigns/dragons_lair
  -> app reads Campaign, returns full detail: characters, scenes, active_scene_id
  -> No state transitions. Read-only.
```

### CUJ-5: WebSocket connect

```
WS /campaigns/dragons_lair/ws?character_id=bob
  -> ws.py looks up Campaign, looks up Character("bob")
  -> validates: character exists, character.actor is UserActor, character is active in scene
  -> accepts WebSocket connection
  -> State: WebSocket connection associated with (campaign_id, character_id)
```

### CUJ-6, CUJ-7: User sends message, gets echo

```
Client sends: {"type":"send_message","content":"I open the dungeon door."}

ws.py:
  -> parses wire message (protocol.parse_client_message)
  -> calls chat_service.handle_user_message(campaign_id, character_id="bob", content=...)

chat_service.handle_user_message:
  -> campaign = campaigns["dragons_lair"]
  -> scene = campaign.get_active_scene()
  -> character = campaign.get_character("bob")
  -> VALIDATE: character.actor is UserActor (else raise)
  -> VALIDATE: character.id in scene.active_character_ids (else raise)
  -> user_msg = Message.create(scene_id, character_id="bob", content="I open the dungeon door.")
  -> scene.add_message(user_msg)
  -> message_repo.append(user_msg)
  -> STATE: scene.messages = [user_msg]
  -> returns user_msg

ws.py:
  -> sends MessageReceived frame (echo) to client
```

### CUJ-8, CUJ-9, CUJ-10: NPC characters respond (streaming)

```
ws.py (continues after CUJ-7):
  -> npc_characters = [c for c in scene's active characters if c.actor is NpcActor]
  -> for each npc_character (elara, thrain, sly):

      ws.py sends StreamStart frame to client

      character.chat_stream(scene.messages) -> AsyncIterator[str]:
        -> builds llm_messages:
             [0] LLMMessage(role="system", content=character.character_sheet)
             [1] LLMMessage(role="system", content=f"Scene: {scene.description}")
             [N] for each msg in scene.messages:
                   if msg.character_id == self.id -> role="assistant"
                   else -> role="user", content=f"{sender_name}: {msg.content}"
        -> calls self.actor.chat_stream(llm_messages)
             NpcActor.chat_stream -> calls llm_client.stream(messages, model)
             yields tokens

      ws.py: for each token yielded:
        -> sends StreamDelta frame to client
        -> accumulates token into full_content

      After stream exhausts:
        -> npc_msg = Message.create(scene_id, character_id=npc.id, content=full_content)
        -> scene.add_message(npc_msg)
        -> message_repo.append(npc_msg)
        -> ws.py sends StreamEnd frame (with npc_msg.id)

STATE after CUJ-10:
  scene.messages = [bob_msg, elara_msg, thrain_msg, sly_msg]
  message_repo has all 4 messages
```

### CUJ-11: Persistence verification

```
GET /campaigns/dragons_lair/scenes/dungeon_entrance/messages
  -> rest.py calls message_repo.get_by_scene(SceneId("dungeon_entrance"))
  -> returns [bob_msg, elara_msg, thrain_msg, sly_msg] in order
```

### CUJ-12: Conversation continues

```
Same as CUJ-6 through CUJ-10, but now:
  -> scene.messages has 4 messages from round 1
  -> each character.chat_stream receives all prior messages as history
  -> NPC characters see the full conversation context
```

---

## C. Per-Class Public Methods (derived from logic flow)

### `Actor` (Protocol) — `actor.py`

Derived from: CUJ-8/9/10 (NPC response generation)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `chat_stream` | `async (messages: list[LLMMessage]) -> AsyncIterator[str]` | Yields response tokens. NpcActor delegates to llm_client.stream. UserActor raises NotImplementedError. |

- `NpcActor(llm_client: LLMClient, model: str | None)` — wraps LLM
- `UserActor()` — inert placeholder

### `Character` — `character.py`

Derived from: CUJ-8/9/10 (character builds prompt, delegates to actor)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `chat_stream` | `async (scene_messages: list[Message], scene_description: str, get_name: Callable) -> AsyncIterator[str]` | Builds LLM prompt (system=character_sheet, scene desc, history with role mapping), calls actor.chat_stream, yields tokens. |

- `id: CharacterId`, `name: str`, `character_sheet: str`, `actor: Actor`
- `get_name` resolves CharacterId -> display name for history formatting

### `Message` — `message.py`

Derived from: CUJ-6/7/8/9/10 (messages created throughout)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `create` (classmethod) | `(scene_id, character_id, content) -> Message` | Generates MessageId (uuid4), sets timestamp to now(UTC). Returns frozen Message. |

- `id: MessageId`, `scene_id: SceneId`, `character_id: CharacterId`, `content: str`, `timestamp: datetime`
- Frozen/immutable after creation.

### `Scene` — `scene.py`

Derived from: CUJ-6 (message added), CUJ-8/9/10 (NPC responses added)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `add_message` | `(message: Message) -> None` | Appends to messages list. Rejects if message.scene_id != self.id. |

- `id: SceneId`, `campaign_id: CampaignId`, `name: str`, `description: str`
- `active_character_ids: list[CharacterId]`, `messages: list[Message]`

### `Campaign` — `campaign.py`

Derived from: CUJ-2 (loaded), CUJ-5/6 (lookups)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `get_active_scene` | `() -> Scene` | Returns scene matching active_scene_id. Raises ValueError if None, KeyError if not found. |
| `get_character` | `(id: CharacterId) -> Character` | Returns character. Raises KeyError if not found. |

- `id: CampaignId`, `name: str`, `active_scene_id: SceneId | None`
- `characters: dict[CharacterId, Character]`, `scenes: dict[SceneId, Scene]`

### `ConfigLoader` — `config_loader.py`

Derived from: CUJ-1/2 (startup)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `load_server_config` | `() -> ServerConfig` | Reads sidestage.yaml. Returns ServerConfig(default_model). |
| `load_all_campaigns` | `(llm_client: LLMClient) -> dict[CampaignId, Campaign]` | Reads each campaign dir. Creates Characters with NpcActor(llm_client) or UserActor(). Returns fully hydrated campaigns. |

### `ChatService` — `chat_service.py`

Derived from: CUJ-6/7 (user message handling)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `handle_user_message` | `async (campaign_id, character_id, content) -> Message` | Validates sender is USER + active in scene. Creates Message, adds to scene, persists to repo. Returns the Message. |

- Injected with: campaigns dict, MessageRepository
- Thin glue — validation + persistence. Does NOT orchestrate NPC responses (ws.py does that directly by iterating active NPCs and calling character.chat_stream).

### `ws.py` — WebSocket handler

Derived from: CUJ-5 (connect), CUJ-6-10 (message + NPC streaming), CUJ-12 (loop)

The WebSocket handler is the CUJ orchestrator. On receiving a `send_message`:
1. Calls `chat_service.handle_user_message` -> gets user Message (CUJ-6/7)
2. Sends `message` echo frame
3. For each NPC character active in scene (CUJ-8/9/10):
   a. Sends `stream_start`
   b. Calls `character.chat_stream(scene.messages, scene.description, ...)`
   c. For each token: sends `stream_delta`, accumulates
   d. Creates Message from accumulated content, adds to scene, persists
   e. Sends `stream_end`

### `rest.py` — REST routes

Derived from: CUJ-3/4 (read campaigns), CUJ-11 (read messages)

| Endpoint | Behavior |
|----------|----------|
| `GET /campaigns` | List campaigns (id, name, active_scene_id) |
| `GET /campaigns/{id}` | Campaign detail with characters + scenes |
| `GET /campaigns/{id}/scenes/{sid}/messages` | Message history for scene |

### `LLMClient` (Protocol) — `llm_client.py`

Derived from: CUJ-8/9/10 (NpcActor delegates here)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `stream` | `async (messages: list[LLMMessage], model: str \| None) -> AsyncIterator[str]` | Yields tokens from LLM. |

- `LiteLLMClient(default_model: str)` — concrete impl, wraps litellm
- `LLMMessage(role: str, content: str)` — chat completion format

### `MessageRepository` (Protocol) — `message_repository.py`

Derived from: CUJ-6/8/9/10 (persist), CUJ-11 (read back)

| Method | Signature | Behavior |
|--------|-----------|----------|
| `append` | `async (message: Message) -> None` | Stores message. |
| `get_by_scene` | `async (scene_id: SceneId) -> list[Message]` | Returns messages in insertion order. Empty list if none. |

### Wire Protocol — `protocol.py`

Derived from: CUJ-6 (client->server), CUJ-7/8/9/10 (server->client)

| Direction | Type | Fields |
|-----------|------|--------|
| Client->Server | `send_message` | `content` |
| Server->Client | `message` | `message_id`, `character_id`, `character_name`, `content`, `timestamp` |
| Server->Client | `stream_start` | `character_id`, `character_name` |
| Server->Client | `stream_delta` | `character_id`, `token` |
| Server->Client | `stream_end` | `character_id`, `message_id` |
| Server->Client | `error` | `detail` |

---

## D. TDD Implementation Order

1. `ids.py`, `message.py` — leaf types, no deps
2. `actor.py` — Actor protocol, NpcActor, UserActor (mock LLMClient in tests)
3. `character.py` — Character with chat_stream (mock Actor in tests)
4. `scene.py` — Scene with add_message
5. `campaign.py` — Campaign aggregate (get_active_scene, get_character)
6. `config_loader.py` — load config dir -> hydrated domain (fixture files in tmp_path)
7. `llm_client.py` — LiteLLMClient (mock litellm)
8. `message_repository.py` — InMemoryMessageRepository
9. `chat_service.py` — handle_user_message (mock repo)
10. `protocol.py` — wire protocol serialization
11. `rest.py` — read-only REST (FastAPI TestClient)
12. `ws.py` — WebSocket full CUJ flow (mock actors, TestClient)
13. `integration_tests/test_chat_flow.py` — real server, fixture config, mocked litellm

---

## E. Verification

- Unit tests: `pytest src/sidestage/ --ignore=src/sidestage/integration_tests/`
- Integration tests: `pytest src/sidestage/integration_tests/`
- Each TDD step: testwriter writes failing tests, coder makes them pass
- Final verification: integration test replays CUJ-1 through CUJ-12
