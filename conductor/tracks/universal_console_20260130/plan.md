# Implementation Plan: Universal Console

## Phase 1: Real-time Infrastructure (WebSockets)
- [x] Task: Set up WebSocket broadcasting in FastAPI
    - [x] Implement a `ConnectionManager` to track active sessions.
    - [x] Add a WebSocket endpoint for chat and state updates.
- [x] Task: Client-side WebSocket Integration
    - [x] Update `app.js` to connect to the WebSocket.
    - [x] Refactor chat message handling to use incoming socket events.

## Phase 2: Markdown & Widgets
- [x] Task: Implement Markdown Rendering
    - [x] Integrate a lightweight Markdown library (simple regex implementation).
    - [x] Update message rendering logic to parse Markdown.
- [x] Task: Implement Widget System
    - [x] Define a message schema that supports `type: "text"` and `type: "widget"`.
    - [x] Create the `EntityWidget` UI component.

## Phase 3: Unified Layout & Splitter
- [x] Task: Shared Chat Component
    - [x] Refactor the chat box into a reusable component that can be mounted in both root and `/entities`.
- [x] Task: Implement Draggable Splitter
    - [x] Add a resize handle between the entity list and the chat box on the Entities page.
    - [x] Persist the splitter position (optional/localStorage).

## Phase 4: State Sync & Auto-Updates
- [x] Task: Sync Entity Updates
    - [x] Broadcast entity changes (add/update/delete) over WebSockets.
    - [x] Update the Entity Browser and any active Widgets in real-time when a broadcast is received.

## Phase 5: Verification
- [x] Task: Conductor - User Manual Verification (Protocol in workflow.md)
