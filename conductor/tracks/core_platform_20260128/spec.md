# Specification: Core Sidestage Platform

## 1. Overview
This track focuses on establishing the foundational "Sidestage" platform. It includes the environment setup, the core "Co-Author" agent capable of managing world data, and the primary interfaces (CLI and Web) with integrated introspection capabilities.

## 2. Requirements

### 2.1 Core Platform & Framework
- Initialize Python project with Poetry.
- Integrate `agno_os` as the agent orchestration layer.
- **Agent OS:** The main server runs `agno.os.AgentOS` to manage and serve agents.
- Support hybrid inference: `llama.cpp` (local) and `Gemini` (cloud).
- **Campaign Storage:** The server accepts a campaign name as a CLI argument and stores all persistent data (configs, databases, files) in `~/.sidestage/<campaign_name>/`.

### 2.2 Co-Author Agent (Functional MVP)
- **Knowledge & Memory:** Utilize Agno's built-in memory and storage systems (e.g., `SqliteDb`) to maintain context across sessions.
- **Fact Management:** Leverage Agno's native capability to store and retrieve "Learned Knowledge" or agent memory for world details.
- **Tooling:** ONLY enable Agno's built-in internal tools (e.g., search, memory retrieval) that come standard with the framework. Custom domain-specific tools (e.g., NPC CRUD) are deferred to a subsequent track.

### 2.3 Introspection & Observability
- **Built-in Tracing:** Exclusively use Agno's internal tracing and observability features (via `AgentOS` and `agno_spans`).
- **Standard UI:** Use Agno's default observability interfaces or API endpoints for viewing logs, tool traces, and prompts.

### 2.4 User Interfaces
- **CLI:** A terminal-based interface for rapid agent interaction and debugging.
- **Web UI:** A high-contrast dashboard for world management and detailed introspection logs.

## 3. Constraints
- DM Veto: Any update to the world state proposed by the agent requires manual confirmation.
- Focus on flexibility and simple prompts over complex factual integrity logic.
