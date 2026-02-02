# UI Structure

The Sidestage Web Interface is built as a Single Page Application (SPA) using React. It follows a high-contrast, dark-mode aesthetic suited for "DM Screen" usage.

## Global Layout
The application features a persistent layout consisting of:
- **Header:**
    - App Title ("Sidestage")
    - Navigation Links: Scenes, Entities, Traces.
- **Sidebar (Context-Dependent):**
    - **Scenes View:** Displays a list of available scenes and a "New Scene" button.
    - **Entities View:** (Currently handled within the main content area).
- **Main Content Area:** Displays the active route content.

## Routes

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
        - **Type Filters:** Toggle buttons for All, NPCs, Locations, Items, Scenes.
        - **Entity List:** detailed list of matching entities.
    - **Right Pane (Editor):**
        - **Title Bar:** Entity Name input, Type display, ID display, Save button.
        - **Content Editor:** Rich-text (Markdown) editor for the entity's `body` text.
        - **Metadata Panel:** Form fields specific to the entity type:
            - **NPC:** Location ID, Inventory list.
            - **Location:** Connected Locations list.
            - **Scene:** Current Gametime.

## Components

### Chat Widget
- Handles sending/receiving messages via WebSocket.
- Renders Markdown content.
- Supports interactive "Widgets" (e.g., clicking an Entity card opens the Entity Modal).

### Entity Editor
- Uses `tiptap` for Markdown editing.
- Supports real-time collaborative sync (via `entity_content_sync` WebSocket events).
- Auto-saves changes to the backend.

### Entity Modal
- A floating overlay triggered from Chat Widgets.
- Displays a read-only view of an entity's markdown content.
