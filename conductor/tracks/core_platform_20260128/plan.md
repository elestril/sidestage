# Implementation Plan: Core Sidestage Platform

This plan outlines the steps to build the core Sidestage platform.

## Phase 1: Environment & Project Scaffolding
- [~] Task: Initialize Poetry project and directory structure
    - [x] Run `poetry init` and set up `src/` directory.
    - [x] Configure `pyproject.toml` with `agno` and other dependencies.
- [~] Task: Set up Agno_os and hybrid inference stubs
    - [x] Create basic Agno agent configuration.
    - [x] Implement a flexible LLM provider factory for `llama.cpp` and `Gemini`.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Environment & Project Scaffolding' (Protocol in workflow.md)

## Phase 2: Knowledge Store & Co-Author Agent
- [ ] Task: Implement persistent storage for World Entities
    - [ ] Write Tests: Define CRUD operations for NPC, Location, and Item entities.
    - [ ] Implement Feature: Create a storage layer (e.g., SQLite) to manage world facts.
- [ ] Task: Create the Co-Author Agent
    - [ ] Write Tests: Verify the agent can retrieve and suggest updates to world facts.
    - [ ] Implement Feature: Configure the Agno agent with tools to interact with the storage layer.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Knowledge Store & Co-Author Agent' (Protocol in workflow.md)

## Phase 3: Introspection & Observability
- [ ] Task: Implement Prompt and Tool Logging
    - [ ] Write Tests: Ensure logs are captured for LLM interactions.
    - [ ] Implement Feature: Add hooks to the Agno agent to capture prompts, responses, and tool calls.
- [ ] Task: Build Introspection Visualization (CLI & Web)
    - [ ] Write Tests: Verify the UI can display captured logs.
    - [ ] Implement Feature: Create a basic CLI log viewer and a corresponding Web dashboard component.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Introspection & Observability' (Protocol in workflow.md)

## Phase 4: Unified Interfaces
- [ ] Task: Finalize CLI Interface
    - [ ] Write Tests: Validate end-to-end flow in the terminal.
    - [ ] Implement Feature: Build a robust CLI loop for agent interaction.
- [ ] Task: Basic Web Frontend Integration
    - [ ] Write Tests: Verify the web server serves the UI and connects to the agent.
    - [ ] Implement Feature: Set up a basic web server (e.g., FastAPI) to host the high-contrast UI.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Unified Interfaces' (Protocol in workflow.md)
