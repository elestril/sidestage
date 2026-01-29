# Implementation Plan: Core Sidestage Platform

This plan outlines the steps to build the core Sidestage platform.

## Phase 1: Environment & Project Scaffolding
- [x] Task: Initialize Poetry project and directory structure (9a32a19)
    - [x] Run `poetry init` and set up `src/` directory.
    - [x] Configure `pyproject.toml` with `agno` and other dependencies.
- [x] Task: Set up Agno_os and hybrid inference stubs (9a32a19)
    - [x] Create basic Agno agent configuration.
    - [x] Implement a flexible LLM provider factory for `llama.cpp` and `Gemini`.
- [~] Task: Conductor - User Manual Verification 'Phase 1: Environment & Project Scaffolding' (Protocol in workflow.md)

## Phase 2: Knowledge Store & Co-Author Agent [checkpoint: 5e054a3]
- [x] Task: Implement persistent storage for World Entities (8265f14)
    - [x] Write Tests: Define CRUD operations for NPC, Location, and Item entities.
    - [x] Implement Feature: Create a storage layer (e.g., SQLite) to manage world facts.
- [x] Task: Create the Co-Author Agent (8265f14)
    - [x] Write Tests: Verify the agent can retrieve and suggest updates to world facts.
    - [x] Implement Feature: Configure the Agno agent with tools to interact with the storage layer.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Knowledge Store & Co-Author Agent' (5e054a3)

## Phase 3: Introspection & Observability [checkpoint: 2329da2]
- [x] Task: Enable Agno Built-in Tracing (2329da2)
    - [x] Configure AgentOS with `tracing=True` and SQLite storage.
    - [x] Verify that prompts and tool calls are captured in `agno_spans`.
- [x] Task: Verify and Document Agno Observability Access (2329da2)
    - [x] Write Tests: Ensure Agno's trace endpoints (`/traces`, `/sessions/{id}/runs`) return captured logs.
    - [x] Implement Feature: Document how to use Agno's built-in observability (API endpoints or Agno UI).
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Introspection & Observability' (Protocol in workflow.md)

## Phase 4: Unified Interfaces
- [ ] Task: Finalize CLI Interface
    - [ ] Write Tests: Validate end-to-end flow in the terminal.
    - [ ] Implement Feature: Build a robust CLI loop for agent interaction.
- [ ] Task: Basic Web Frontend Integration
    - [ ] Write Tests: Verify the web server serves the UI and connects to the agent.
    - [ ] Implement Feature: Set up a basic web server (e.g., FastAPI) to host the high-contrast UI.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Unified Interfaces' (Protocol in workflow.md)
