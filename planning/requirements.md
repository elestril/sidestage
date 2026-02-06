# Sidestage Requirements Specification

## 1. Project Overview
Sidestage is a modular, multi-agent RPG assistant designed to maintain world consistency across campaign preparation, live session management, and downtime player engagement. It serves as a digital companion for Game Masters (DMs) and players, focusing on architectural flexibility and deep introspection.

### 1.1 Core Vision
To provide a unified, consistent world state accessible through multiple interfaces, allowing for experimentation with various knowledge storage models, memory systems, and LLM backends.

### 1.2 Target Audience
- **Primary:** Game Masters (DMs/GMs) seeking to reduce cognitive load and maintain consistency.
- **Secondary:** Players participating in downtime activities and "minigames".

---

## 2. Technology Stack

### 2.1 Core Language & Frameworks
- **Language:** Python 3.12+ (Async-focused, modern typing).
- **Dependency Management:** Poetry.

### 2.2 Inference Engines
- **Hybrid Support:** Native support for local (`llama.cpp`) and cloud (`Google Gemini`) engines.

### 2.3 Storage & Persistence
- **Markdown-First:** Entities (Characters, Locations, Items, Scenes) are stored as Markdown files with YAML frontmatter.
- **Graph Database (Planned):** [FalkorDB](https://falkordb.com/) for entities, relationships, and memories.
- **Relational:** SQLite for chat logs, session memory, and user management.
- **File System:** Campaign data stored in `~/.sidestage/<campaign_name>/`.

### 2.4 Interfaces
- **Web Frontend:** React-based SPA (Single Page Application).
- **CLI:** Python-based CLI for direct interaction and debugging.
- **API:** JSON REST API and WebSocket protocol for real-time synchronization.

---

## 3. Core Features & Capabilities

### 3.1 World Building (Entity Management)
- **Universal Entity Model:** Shared structure for Characters, Locations, Items, Scenes, and Events.
- **Entity Browser:** Filtering by type/tags, search, and bulk operations.
- **Import/Export:** Bidirectional synchronization between the database and local Markdown files.
- **Collaborative Editing:** Real-time synchronization of entity content across multiple connected clients via WebSockets.

### 3.2 AI Co-Author & Actor System
- **Context-Aware Chat:** Scene-specific history and tool-based access to world knowledge.
- **Asynchronous Actor System:**
    - **Actors:** Driving entities (User or AI).
    - **Characters:** In-world personas (spoken by Actors).
- **Multi-Agent Interaction:** Support for multiple NPCs (AgentActors) reacting to events in a scene.
- **Dynamic Prompts:** System prompts generated from character descriptions and templates (`default_npc.txt`, `unseen_npc.txt`).

### 3.3 Session Management (Time & Scenes)
- **Scenes as Containers:** All interactions occur within a Scene entity.
- **Gametime Tracking:** Granular tracking of in-world time (seconds since epoch) vs. real-world walltime.
- **Concurrent Scenes:** Multiple scenes can exist at different gametimes (e.g., split parties, flashbacks).
- **Prose View:** Dedicated Markdown description for each scene.

### 3.4 Observability
- **Trace Visualization:** Ability to inspect agent reasoning, prompt chains, and tool usage.
- **Log Introspection:** Comprehensive logs for debugging agent decision-making.

---

## 4. Architectural Requirements

### 4.1 Communication Protocol
- **Event-Driven:** Message Bus for dispatching `ChatMessage`, `JoinEvent`, `LeaveEvent`, etc.
- **WebSocket Sync:** Real-time updates for chat, entity changes, and scene state.
- **Insert Hooks:** Extensible pipeline for processing events before persistence or broadcast.

### 4.2 Data Models

#### Entity (Base)
- `id`: Unique identifier.
- `name`: Display name.
- `body`: Markdown content/description.
- `type`: NPC, Location, Item, Scene, Event.

#### Character (extends Entity)
- `unseen`: Boolean (e.g., for DM or Narrator).
- `location_id`: Current location.
- `inventory`: List of Item IDs.

#### Location (extends Entity)

#### Scene (extends Entity)
- `current_gametime`: In-world timestamp.
- `location_id`: Primary location context.
- `events`: List of historical occurrences.
- `characters`: List of characters in the scene.

#### Event (Entity)
- `origin`: Entitity that created the event. 
- `gametime`: In-world timestamp
- `walltime`: Real world timestamp
- `event_type`: e.g. chat message, character join/leave, scene start/end

---

## 5. UI/UX Requirements

### 5.1 Universal Console
- **Markdown Rendering:** Rich text support for all chat messages.
- **Widgets:** Embedded interactive cards for Entities mentioned in chat.
- **Resizable Layout:** Splitter between Scene Prose and Chat history.

### 5.2 Navigation & Theming
- **Global Navbar:** Direct access to Scenes, Entities, and Traces.
- **High-Contrast RPG Theme:** Dark-mode aesthetic optimized for "DM Screen" usage.

---

## 6. Project Tracks (Implementation Roadmap)

### 6.1 Completed Tracks
- **Track 1: Core Platform:** Foundation with Agno, CLI, and basic Web UI.
- **Track 2: Entity Management:** Navbar, Entity Browser, and Markdown Import/Export.
- **Track 3: Universal Console:** Rich text, Widgets, and real-time sync.
- **Track 4: Time and Scenes:** Gametime system and Scene-based organization.
- **Track 5: NPC Agents & Actor System:** Event-driven message bus and multi-agent loops.
- **Track 7: Cleanup & Architecture Refactor:** Standardization of schemas and logic.

### 6.2 Planned/In-Progress Tracks
- **Track 6: Memory & Graph Database:** Transitioning primary storage to FalkorDB for relationship traversal and vector-based memory retrieval.
- **Track 8: Discord Bot (Future):** Extending the Actor system to Discord for downtime interactions.
