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
- **Knowledge Management:** Agent must be able to perform CRUD operations on a persistent knowledge store (e.g., SQLite or a vector-supported database).
- **Entities:** Support for NPCs, Locations, and Items.
- **Fact Updates:** Enable the DM to ask questions about the world and request updates/creations.

### 2.3 Introspection & Observability
- **Prompt Logging:** Log every prompt sent to and received from LLMs.
- **Tool Tracing:** Record and display function calls made by agents.
- **Context Visualization:** Show what data was retrieved from the knowledge store to answer a specific query.

### 2.4 User Interfaces
- **CLI:** A terminal-based interface for rapid agent interaction and debugging.
- **Web UI:** A high-contrast dashboard for world management and detailed introspection logs.

## 3. Constraints
- DM Veto: Any update to the world state proposed by the agent requires manual confirmation.
- Focus on flexibility and simple prompts over complex factual integrity logic.
