# UI Structure

The Sidestage Web Interface is built as a Single Page Application (SPA) using React. It follows a high-contrast, dark-mode aesthetic suited for "DM Screen" usage.

## Global Layout
The application features a persistent layout consisting of:
- **Header:**
    - App Title ("Sidestage")
    - Navigation Links: Scenes, Entities.
- **Sidebar (Context-Dependent):**
    - **Scenes View:** Displays a list of available scenes and a "New Scene" button.
    - **Entities View:** (Currently handled within the main content area).
- **Main Content Area:** Displays the active route content.

## Routes

### Navigation
The header contains navigation links to Scenes, Entities, and Traces (uses React Router `NavLink` for SPA navigation with active highlighting).

### 1. Scenes View (`/scenes/:sceneId`)
The primary interface for running a game session or planning.

- **URL:** `/scenes/<scene_id>`
- **Structure:**
    - **Left Pane (Prose):**
        - Displays the `activeScene.body` rendered as Markdown.
        - Scrollable area for scene descriptions, notes, and static content.
    - **Splitter:** Resizable divider between Prose and Chat.
    - **Right Pane (Chat):**
        - **Header:** Shows Scene Name and Current Gametime.
        - **Message History:** Scrollable list of user and agent messages.
            - **Widgets:** Interactive cards embedded in messages (e.g., Entity Previews).
        - **Input Area:** Text input for interacting with the Co-Author agent.
    - **Right Sidebar (Actors):** (Planned) For managing active NPCs in the scene.

### 2. Entities View (`/entities/:entityId`)
The database management interface for the campaign world.

- **URL:** `/entities` or `/entities/<entity_id>`
- **Structure:**
    - **Left Pane (Browser):**
        - **Search Bar:** Real-time filtering by name and content.
        - **Sync Buttons:** Import/Export entities to disk.
        - **Campaign Buttons:**
            - **Import Campaign:** Two-phase import from `markdown/` directory. First validates and shows a confirmation dialog with counts and warnings, then executes on user confirmation.
            - **Backup Campaign:** Exports the full graph to `markdown/` directory. Shows success/failure feedback with counts.
            - Both buttons are disabled when campaign health is DEGRADED (another operation is in progress).
        - **Type Filters:** Toggle buttons for All, Characters, Locations, Items, Scenes.
        - **Entity List:** detailed list of matching entities.
    - **Right Pane (Editor):**
        - **Title Bar:** Entity Name input, Type display, ID display, Save button.
        - **Content Editor:** Rich-text (Markdown) editor for the entity's `body` text.
        - **Metadata Panel:** Form fields specific to the entity type:
            - **Character:** Location ID, Inventory list.
            - **Location:** Connected Locations list.
            - **Scene:** Current Gametime.

### 3. Trace Viewer (`/traces`, `/traces/:sceneId/:traceId`)
The trace inspection interface for debugging agent behavior.

- **URL:** `/traces` or `/traces/<scene_id>/<trace_id>`
- **Structure:**
    - **Left Pane (Trace List):**
        - **Scene Selector:** Dropdown to filter traces by scene, or "All scenes".
        - **Tracing Status:** Shows whether tracing is enabled, trace count.
        - **Trace List:** Scrollable list of trace summaries. Running traces show a pulsing green dot and "In progress..." instead of duration.
    - **Right Pane (Trace Detail):**
        - **Waterfall Timeline:** Tree-structured span timeline with collapsible nodes, color-coded duration bars (blue=LLM, green=tool, orange=memory, purple=scene, red=error).
        - **Span Detail Panel:** Shows span attributes, prompt/completion events, error details.
- **Real-time Updates:** Subscribes to WebSocket `trace_started`, `span_completed`, and `trace_completed` messages to show live trace data as spans arrive.

## Components

### Chat Widget
- Handles sending/receiving messages via WebSocket.
- Renders Markdown content.
- Supports interactive "Widgets" (e.g., clicking an Entity card opens the Entity Modal).
- **Debug Mode Toggle:** A Bug icon button in the header toggles debug mode on/off (stored in AppContext).
- **Trace Link Icons:** When debug mode is enabled, each message shows a small Activity icon. Clicking it resolves the message's trace via `GET /v1/traces?event_id=<message.id>` (with per-session caching) and navigates to the Trace Viewer.

### Entity Editor
- Uses `tiptap` for Markdown editing.
- Supports real-time collaborative sync (via `entity_content_sync` WebSocket events).
- Auto-saves changes to the backend.

### Entity Modal
- A floating overlay triggered from Chat Widgets.
- Displays a read-only view of an entity's markdown content.
