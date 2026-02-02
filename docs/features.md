# Features

Sidestage is designed as a modular, AI-enhanced campaign manager.

## Core Platform

### Campaign Management
- **Multi-Campaign Support:** The orchestrator manages multiple distinct campaigns.
- **File-Based Storage:** All data is stored as human-readable files (Markdown/YAML/SQLite) in `~/.sidestage/<campaign_name>`.

### Real-Time Synchronization
- **WebSocket Architecture:** All clients (browser windows) stay in sync instantly.
- **Collaborative Editing:** Multiple users can edit entity descriptions simultaneously without conflicts.
- **Live Updates:** Changes made by the AI or other users appear immediately.

## World Building (Entity Management)

### Entity Database
- **Universal Entity Model:** All game objects (NPCs, Locations, Items, Scenes, Events) share a common structure.
- **Markdown-First:** Entities are stored and edited as Markdown files with YAML frontmatter.
- **Import/Export:**
    - **Bulk Export:** Dump the entire database to a folder of `.md` files for backup or external editing.
    - **Bulk Import:** Re-ingest modified files from disk.

### Specialized Types
- **NPCs:** Track location and inventory.
- **Locations:** Track connections (navigation graph).
- **Scenes:** Track active gametime and events.
- **Items:** Track properties.
- **Events:** Track historical occurrences with walltime and gametime timestamps.

## AI Co-Author

### Context-Aware Chat
- **Scene-Specific:** Chat history is compartmentalized by Scene.
- **World Knowledge:** The agent has access to the Entity Database via tools.
- **Tool Use:** The agent can actively query the database (`list_npcs`, `get_location`) to answer questions accurately.

### Interactive Responses
- **Widget Embedding:** The agent can return structured data (e.g., an Entity Card) alongside text, which renders as an interactive element in the chat.

## Session Tools

### Scene Management
- **Multiple Scenes:** Organize the campaign into distinct scenes (e.g., "Tavern", "Dungeon", "Flashback").
- **Prose View:** A dedicated area for the static description of the current scene.

### Gametime Tracking
- **Granular Time:** Time is tracked in seconds and displayed as `Day D, HH:MM:SS`.
- **Per-Scene Clocks:** Different scenes can exist at different times (enabling split parties or flashbacks).
