# Implementation Plan: Entity Management

## Phase 1: Navigation & Layout
- [x] Task: Implement Global Navbar
    - [x] Update `index.html` and `style.css` to include a fixed/sticky navbar.
    - [x] Ensure consistent navigation between Chat, Entities, and Traces (AgentOS routes).
- [x] Task: Create Entities Page Structure
    - [x] Add `entities.html` or dynamic route handling for `/entities`.

## Phase 2: Entity Representation & Rendering
- [x] Task: Define Markdown Schema
    - [x] Create examples for NPC, Location, and Item in Markdown format.
- [x] Task: Implement Markdown Renderer
    - [x] Build a utility to serialize `Entity` objects to Markdown.
    - [x] Integrate a Markdown rendering library (or simple converter) for the web UI.

## Phase 3: Web Entity Browser
- [x] Task: Build Entity List Component
    - [x] Implement client-side fetching of all entities from the API.
    - [x] Add filtering and shortcut buttons (e.g., "Show NPCs").
- [x] Task: Entity Detail View
    - [x] Implement a modal or dedicated view for reading/editing an entity's markdown.

## Phase 4: Import/Export Logic
- [x] Task: Implement Server-Side Import/Export
    - [x] Add API endpoints for triggering import/export.
    - [x] Implement filesystem logic to read/write Markdown files with YAML frontmatter.
- [x] Task: UI Integration for Import/Export
    - [x] Add buttons to the Entities page to trigger sync.

## Phase 5: Verification
- [x] Task: Conductor - User Manual Verification (Protocol in workflow.md)
