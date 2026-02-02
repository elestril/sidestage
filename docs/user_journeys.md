# User Journeys

This document outlines the primary workflows for users interacting with Sidestage.

## 1. Setting Up a New Campaign

**Goal:** Initialize a fresh campaign environment.

1.  **Start Server:** User runs `sidestage <campaign_name>`.
2.  **Initialization:**
    - System creates `~/.sidestage/<campaign_name>/`.
    - System initializes SQLite database.
    - System creates a default `config.yml`.
    - System ensures a default "Campaign Planning" scene exists.
3.  **Access UI:** User opens `http://localhost:8000` in their browser.
4.  **Result:** The user is presented with the "Campaign Planning" scene, ready to start building.

## 2. World Building (Prep)

**Goal:** Populate the world with NPCs and Locations before a session.

1.  **Navigate to Entities:** User clicks "Entities" in the header.
2.  **Import Existing Notes (Optional):**
    - User puts existing markdown files in `~/.sidestage/<campaign_name>/entities/`.
    - User clicks "Import" in the UI.
    - System ingests files into the database.
3.  **Create New Entity:**
    - User interacts with the AI in "Campaign Planning" to generate ideas (e.g., "Create a goblin king NPC").
    - **OR** (Future Feature) User clicks "New Entity" manually.
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
    - **Query:** "What is the bartender's name?" -> AI checks database -> "His name is Barnaby."
    - **Generate:** "Describe the smell in here." -> AI generates sensory details.
    - **Record:** "The players bought 3 ales." -> AI (future) updates inventory/money.
4.  **Track Time:** User updates the "Current Gametime" field in the scene metadata if time passes significantly.

## 4. Post-Session Review

**Goal:** Review what happened and update the world state.

1.  **Read Logs:** User scrolls back through the Chat History of the scene.
2.  **Export Data:** User clicks "Export" on the Entities page to backup the latest state of the world to Markdown files.
