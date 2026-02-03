# Plan: NPC Agents & Actor System

## Phase 1: Model & Content Refactoring
- [ ] Create `./data/prompts` and `./data/characters` directories.
- [ ] Add `default_npc.txt` and `unseen_npc.txt` prompt templates.
- [ ] Add `co-author.md` and `narrator.md` character sheets.
- [ ] Rename `Scene` logic class to `SceneLogic` and `SceneData` schema to `Scene`.
- [ ] Rename `NPC` schema to `Character` and add `unseen` field.
- [ ] Update `Storage` and DB schema for `characters` and `scenes`.
- [ ] Update `ChatMessage` schema to use `character_id`.
- [ ] Create `JoinEvent`, `LeaveEvent`, `FastForwardEvent` schemas (all extending `Event`).

## Phase 2: Message Queue Architecture
- [ ] Implement `SceneMessageBus` in `sidestage/bus.py`.
    - Must support async listeners for generic `Event` types.
    - Must include an `insert_hook` for pre-processing `Event`s.
- [ ] Refactor `SceneLogic` to own a `MessageBus`.
- [ ] Update `Orchestrator` to route incoming WebSocket messages/events to `SceneLogic.bus.publish(event)`.

## Phase 3: Character & Agent Activation
- [ ] Create `character.py` for a `CharacterLogic` runtime class.
    - It will hold the `Character` schema data and runtime state (like the `AgentActor` instance).
- [ ] Implement `CharacterLogic.activate()` method to instantiate an `AgentActor`.
- [ ] Implement `AgentActor` class:
    - Constructor must call `self.update_prompt(character)`, which loads a template from `./data/prompts` and formats it with `character.body`.
    - `AgentActor` must subscribe to the `SceneMessageBus` for `Event`s.
    - `AgentActor.on_message(history)` must filter out `ChatMessage`s where its own character was the last speaker.

## Phase 4: Scene & Orchestrator Integration
- [ ] Implement `SceneLogic.activate()` method to activate all its `CharacterLogic` instances.
- [ ] Update `Orchestrator` to call `scenelogic.activate()` when a scene is loaded.
- [ ] Implement default content loading in `Campaign` constructor for new campaigns.
- [ ] Add `POST /v1/campaign/reload-defaults` API endpoint.
- [ ] Update the primary chat endpoint to be a simple fire-and-forget publisher of `ChatMessage`s to the bus.

## Phase 5: UI Updates
- [ ] Frontend: Update ChatWidget to render based on `character_id` name/avatar.
- [ ] Frontend: Add visual distinction for `unseen` characters.
- [ ] Frontend: Add a "Reload Default Characters" button to the UI that calls the new endpoint.
- [ ] Frontend: "Actors" panel (if scope permits).
