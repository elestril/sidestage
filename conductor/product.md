# Initial Concept

**Project Name:** Sidestage
**Description:** A multi-agent RPG assistant for tabletop RPGs that maintains a consistent campaign world.

**Core Use Cases:**
1.  **DM Prep Assistant:** Helps Game Masters during session preparation by facilitating consistent content creation and allowing interaction with NPC agents in new scenes.
2.  **Live Session Aid:** Functions as a smart DM screen, providing relevant context and suggestions by following the live conversation at the table.
3.  **Downtime Mini-Game:** Enables players to interact with specific parts of the world between sessions via a Discord bot (e.g., for shopping, errands, or NPC interactions).

# Product Definition

## 1. Vision
Sidestage is a modular, multi-agent RPG assistant designed to bridge the gap between campaign preparation, live session management, and downtime player engagement. The project prioritizes architectural flexibility to support experimentation with various knowledge storage models, memory systems, and LLM backends.

## 2. Target Audience
- **Primary:** Game Masters (DMs/GMs) seeking to reduce cognitive load and maintain campaign consistency.
- **Secondary:** Players participating in downtime activities and "minigames" between sessions.

## 3. Core Principles & Goals
- **Experimentation First:** Prioritize a flexible architecture that allows for rapid swapping of models, vector stores, and memory strategies.
- **Deep Introspection:** Provide comprehensive tooling to inspect agent reasoning, prompt traces, and the state of the knowledge base.
- **Unified Consistency:** Ensure a shared, consistent world state accessible across all interfaces (Prep, Live, Downtime).

## 4. Key Features & Capabilities
- **Multi-Interface Access:**
    - **CLI:** For direct, low-level agent interaction and debugging.
    - **Web Frontend:** A lightweight, self-hosted interface for campaign management and system introspection.
    - **API (agno_os):** Standard endpoints for custom integrations.
    - **Discord Bot:** (Planned) For player downtime interactions.
- **Hybrid Model Support:** Native support for both local (`llama.cpp`) and cloud (`Gemini`) inference engines.
- **Observability Suite:** Tools to visualize prompt chains, retrieve memory contexts, and debug agent decision-making paths.

## 5. Success Metrics (Phase 1)
- **Observability:** Complete visibility into agent decision-making, prompt chains, and memory state changes.
- **Modularity:** Demonstrated ability to swap backend models without code refactoring.