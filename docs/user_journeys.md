# User Journeys

This document outlines the primary workflows for users interacting with Sidestage.

## 1. Setting Up a New Campaign

**Goal:** Initialize a fresh campaign environment.

1.  **Start Server:** User runs `sidestage <campaign_name>`.
2.  **Initialization:**
    - System creates `~/.sidestage/<campaign_name>/`.
    - System initializes SQLite database for chat logs.
    - System connects to FalkorDB and initializes the graph schema (indexes, constraints, vector index).
    - System creates a default `config.yml`.
    - System loads default entities (scenes, characters) from `data/campaign_defaults/markdown/`.
3.  **Access UI:** User opens `http://localhost:8000` in their browser.
4.  **Result:** The user is presented with the "Campaign Planning" scene, ready to start building.

## 2. World Building (Prep)

**Goal:** Populate the world with Characters and Locatioplanning/03-migration-and-sync/implementation/usage.mdns before a session.

1.  **Navigate to Entities:** User clicks "Entities" in the header.
2.  **Import Existing Notes (Optional):**
    - User organizes markdown files into `~/.sidestage/<campaign_name>/markdown/` with subdirectories for `characters/`, `locations/`, `items/`, `scenes/`, `events/`.
    - Each `.md` file uses YAML frontmatter for metadata. Companion `.d/` directories hold memories and chat logs.
    - User clicks "Import Campaign" in the UI.
    - System validates the directory tree (checking for missing references, duplicate IDs, etc.) and presents a report.
    - User reviews warnings/errors and confirms the import.
    - System imports entities, relationships, memories, and chat logs into FalkorDB.
3.  **Create New Entity:**
    - User interacts with the AI in "Campaign Planning" to generate ideas (e.g., "Create a goblin king NPC").
    - **OR** User clicks "New Entity" manually.
4.  **Refine Details:**
    - User selects an entity in the browser.
    - User edits the description in the Markdown editor.
    - User updates metadata (e.g., assigning the Goblin King to the "Goblin Cave" location).
    - User clicks "Save".

## 3. Running a Session

**Goal:** GM runs a game session with the help of the Co-Author.

1.  **Open Scene:** User navigates to the relevant scene (e.g., "The Tavern") or creates a new one.
2.  **Set Context:** User updates the Scene Prose (left pane) to describe the current situation for players.
3.  **Chat with Co-Author:**
    - The agent's prompts are enriched with memory context — scene recollections, character impressions, and world facts.
    - **Query:** "What is the bartender's name?" -> AI checks database -> "His name is Barnaby."
    - **Generate:** "Describe the smell in here." -> AI generates sensory details informed by world knowledge.
    - **Record:** "The players bought 3 ales." -> AI updates relevant memories via tool calls.
4.  **Track Time:** User updates the "Current Gametime" field in the scene metadata if time passes significantly.

## 4. Post-Session Review

**Goal:** Review what happened and update the world state.

1.  **Read Logs:** User scrolls back through the Chat History of the scene.
2.  **Backup Campaign:** User clicks "Backup Campaign" on the Entities page to export the full graph (entities, relationships, memories, chat logs) to a `markdown/` directory tree.
3.  **External Editing (Optional):** User can edit the exported markdown files with any text editor or version-control them with git, then re-import.
