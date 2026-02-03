# NPC Agents & Actor System

**Status:** Draft
**Owner:** @user
**Date:** 2026-02-02

## Goal
To introduce a robust `Actor` system where chat participants are first-class citizens, controlled by either Users or Agents. The core communication protocol is decoupled into an asynchronous message queue, where **Events** (including ChatMessages) are attributed to **Characters** (not Actors), allowing for both in-game immersion and meta-game coordination (DM/Co-Author).

## Core Concepts

### 1. The Actor (The Controller)
An `Actor` is the entity *driving* the behavior. It receives `Event`s and decides when to respond.
- **Types:**
    - `UserActor`: Connected via WebSocket (Frontend).
    - `AgentActor`: Connected via an internal loop (LLM).

### 2. The Character (The Persona)
The `NPC` class is renamed to `Character`. All `ChatMessage`s in the chat are "spoken by" a Character.
- **Attributes:**
    - `unseen` (bool): If `true`, this character is not perceived by in-game entities (e.g., The Narrator, The DM, The Co-Author Agent).
- **Special Characters:**
    - **The Co-Author:** An `unseen` character played by an `AgentActor`. Its system prompt is derived from its `body`.
    - **The DM:** An `unseen` character played by a `UserActor`.

### 3. Asynchronous Scene Logic & Lifecycle
The `Scene.chat()` generator is replaced by an event-driven loop. The lifecycle is character-centric. The data model for a scene will be `Scene` (formerly `SceneData`) and the runtime logic class will be `SceneLogic` (formerly `Scene`).

**The Flow:**
1.  **Scene Activation:** An active `SceneLogic` object is loaded in memory.
2.  **Character Activation:** The `SceneLogic` iterates through its `Character`s and calls `character.activate()`.
3.  **AgentActor Creation:** The `Character.activate()` method instantiates an `AgentActor`.
    - The `AgentActor`'s constructor calls its own `update_prompt(character)` method, which generates a system prompt by loading a template (`default_npc.txt` or `unseen_npc.txt`) and formatting it with the `character.body`.
    - The `AgentActor` subscribes to the Scene's `MessageBus`.
4.  **Event Ingest:** An `Event` (e.g., `ChatMessage`, `JoinEvent`) is pushed to the `SceneLogic.message_bus`.
    - The bus runs an `insert_hook` that can pre-process, filter, or enrich the event.
5.  **Broadcast:** The processed event is sent to all connected WebSockets immediately.
6.  **Persist:** The event is saved to the database (if persistable).
7.  **Dispatch:** The event is delivered to all subscribers on the `MessageBus`.
8.  **Reaction:**
    - `AgentActor`:
        1.  Receives the `Event` + Context (History).
        2.  **Filter:** For `ChatMessage`s, ignores the event if the last message in history is from its own character to prevent loops.
        3.  Evaluates if it should respond.
        4.  Generates a response (asynchronously) and pushes it back to Step 4.

## Architectural Changes

### Default Content
- The project will include a `./data` directory.
    - `./data/prompts/`: Contains `default_npc.txt` and `unseen_npc.txt` templates for `AgentActor` system prompts.
    - `./data/characters/`: Contains `co-author.md` and `narrator.md` character sheets.
- On first run, a new `Campaign` will load these files to create default `Character` entities.
- An API endpoint (`/v1/campaign/reload-defaults`) will be available to re-import this data.

### Domain Models (`schemas.py`)
- **Scene:** The schema for scene data (formerly `SceneData`).
- **Character (extends Entity):**
    - `unseen`: bool (default False).
    - `voice_id`: str (Optional, for TTS).
- **ChatMessage (extends Event):**
    - `character_id`: str (The visible persona).
- **New Event Types (extend Event):**
    - `JoinEvent`, `LeaveEvent`, `FastForwardEvent`.

### Logic (`scene.py`, `character.py`, `bus.py`)
- **SceneLogic:** The runtime logic class for a scene (formerly `Scene`). Owns the message bus.
- **MessageBus:** Implements a queue with an `insert_hook` and handles generic `Event` types.
- **CharacterLogic:** Manages runtime state for a Character.
    - `activate()`: Creates and holds an `AgentActor` instance.
- The `Orchestrator` manages active `SceneLogic` instances.
