# Implementation Plan: Core Sidestage Platform

This plan outlines the steps to build the core Sidestage platform.

## Phase 1: Environment & Project Scaffolding
- [x] Task: Initialize Poetry project and directory structure (9a32a19)
    - [x] Run `poetry init` and set up `src/` directory.
    - [x] Configure `pyproject.toml` with `agno` and other dependencies.
- [x] Task: Set up Agno_os and hybrid inference stubs (9a32a19)
    - [x] Create basic Agno agent configuration.
    - [x] Implement a flexible LLM provider factory for `llama.cpp` and `Gemini`.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Environment & Project Scaffolding' (Protocol in workflow.md)

## Phase 2: Agno-Native Memory & Knowledge [checkpoint: 5e054a3]
- [x] Task: Implement Agno Persistent Storage (8265f14)
    - [x] Write Tests: Verify `SqliteDb` integration for agent sessions and memory.
    - [x] Implement Feature: Configure `AgentOS` and `Agent` to use persistent SQLite storage for session memory.
- [~] Task: Enable Agno Knowledge Management (Deferred to later thread)
    - [ ] Write Tests: Verify the agent can store and retrieve "Learned Knowledge".
    - [ ] Implement Feature: Configure the Co-Author agent with Agno's native memory/knowledge tools.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Agno-Native Memory & Knowledge' (5e054a3)

## Phase 3: Introspection & Observability [checkpoint: 2329da2]
- [x] Task: Enable Agno Built-in Tracing (2329da2)
    - [x] Configure AgentOS with `tracing=True` and SQLite storage.
    - [x] Verify that prompts and tool calls are captured in `agno_spans`.
- [x] Task: Verify and Document Agno Observability Access (2329da2)
    - [x] Write Tests: Ensure Agno's trace endpoints (`/traces`, `/sessions/{id}/runs`) return captured logs.
    - [x] Implement Feature: Document how to use Agno's built-in observability (API endpoints or Agno UI).
- [x] Task: Conductor - User Manual Verification 'Phase 3: Introspection & Observability' (Protocol in workflow.md)

## Phase 4: Unified Interfaces
- [x] Task: Web Frontend Integration (Vanilla JS SPA)
    - [x] Create `static/` directory for HTML/JS/CSS assets.
    - [x] Implement High-Contrast RPG UI for chat interaction.
    - [x] Integrate client-side API calls to Agno AgentOS endpoints.
    - [x] Configure FastAPI to mount and serve static files from `static/`.
- [x] Task: Conductor - User Manual Verification 'Phase 4: Unified Interfaces' (Protocol in workflow.md)
