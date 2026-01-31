# Specification: Entity Management

## Goal
Provide a comprehensive system for managing RPG entities (NPCs, Locations, Items) through the web UI and file-based import/export.

## Requirements

### 1. Consistent UI Navigation
- Implement a global navbar visible on all pages.
- Navigation links: Chat, Entities, Traces.
- Ensure the navbar is responsive and matches the high-contrast RPG theme.

### 2. Entity Rendering
- **Standardized Markdown Representation:**
  - Define a YAML frontmatter + Markdown body format for all entity types.
  - NPCs include location, inventory, and stats.
  - Locations include connections and descriptions.
  - Items include properties and lore.
- **Renderer:**
  - Server-side or client-side logic to convert DB models to Markdown.
  - Visual rendering of Markdown in the browser for a polished "journal" look.

### 3. Web Entity Browser
- A dedicated `/entities` page.
- **Filtering:** Filter by entity type (NPC, Location, Item) and tags.
- **Shortcuts:** Quick filters for common queries like "All NPCs".
- **Search:** Basic text search across names and descriptions.

### 4. Import/Export
- **Export:** Export selected or all entities to a directory as individual `.md` files.
- **Import:** Scan a directory for `.md` files and update/create entities in the database.
- UI actions to trigger import/export.
