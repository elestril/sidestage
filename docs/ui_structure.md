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
The header contains navigation links to Scenes and Entities (uses React Router `NavLink` for SPA navigation with active highlighting).

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
    - **Right Sidebar (Scene Cast):** Manages which characters participate in the scene.
        - **Scene Cast:** Shows characters currently in the scene. Each entry has a hover-reveal remove button (✕).
        - **Available:** Shows characters not in the scene. Click to add (+). Only visible when there are characters not yet in the scene.

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

## Components

### Chat Widget
- Renders events from the `EventModel[]` messages state.
- **Chat messages** (`ChatMessage` event type): rendered as user/NPC chat bubbles with Markdown content.
- **System events** (`JoinEvent`, `LeaveEvent`, `AdjustGametime`): rendered as centered, italic system notices.
- **Error events** (`Error` event type): rendered with distinct red/amber styling.
- **Thinking indicator**: animated bouncing dots shown for each NPC character in the `thinkingActors` set (tracked via `actor_status` WebSocket messages).
- Supports interactive "Widgets" embedded in event metadata (`metadata.widget`), e.g., clicking an Entity card opens the Entity Modal.

### Entity Editor
- Uses `tiptap` for Markdown editing.
- Supports real-time collaborative sync (via `entity_content_sync` WebSocket events).
- Auto-saves changes to the backend.

### Entity Modal
- A floating overlay triggered from Chat Widgets.
- Displays a read-only view of an entity's markdown content.
