# Implementation Plan: Time and Scenes

## Phase 1: Core Time Models
- [x] Task: Implement `Gametime` class
    - [x] Create `src/sidestage/time.py` with `Gametime` logic.
    - [x] Add conversion methods for `Day X, HH:MM:SS`.
- [x] Task: Update `Entity` models
    - [x] Define `Scene` in `src/sidestage/models.py`.
    - [x] Ensure `Scene` inherits from `Entity`.

## Phase 2: Storage & Orchestration Refactor
- [x] Task: Scene-aware Storage
    - [x] Update `Storage` to handle `scenes` table.
    - [x] Link messages/events to specific scene IDs.
- [x] Task: Scene Orchestration
    - [x] Update `SidestageOrchestrator` to manage the "Campaign Planning" scene by default.
    - [x] Add methods to create and switch scenes.

## Phase 3: UI Evolution
- [x] Task: Scene Switcher
    - [x] Add a way to select the active scene in the sidebar or navbar.
- [x] Task: Scene-based Chat
    - [x] Update `app.js` to fetch and display messages per scene.
    - [x] Display the scene's current gametime.

## Phase 4: Sync & Migration
- [x] Task: Real-time Scene Sync
    - [x] Broadcast scene transitions and updates over WebSockets.
- [~] Task: Migrate existing chat (Existing sessions will be treated as scenes)

## Phase 5: Verification
- [x] Task: Conductor - User Manual Verification (Protocol in workflow.md)
