# Specification: Cleanup and Architecture Refactor

## 1. Documentation and Schema Compliance
### Requirements
- **Documentation Updates:** The `docs/` folder must explicitly track all user-visible properties.
    - **JSON APIs:** Complete reference of all endpoints, request/response bodies.
    - **Web Interface:** Structure of HTML pages, URL routing, and functionality.
    - **Features:** Comprehensive list of supported features.
    - **User Journeys:** Documentation of key user workflows.
- **Canonical JSON Schemas:**
    - Define schemas for all API interactions.
    - **Validation:** Both the Python backend and Frontend (if applicable/feasible during build/test) must be tested against these schemas to ensure conformity.

## 2. Architecture Refactor: Orchestrator vs. Campaign
### Requirements
- **Split Responsibilities:**
    - `SidestageOrchestrator`: Responsible *only* for managing a registry/list of `Campaign` objects.
    - `Campaign`: Responsible for holding all state related to a specific campaign instance.
- **Goal:** Decouple global management from individual campaign state.

## 3. Dependency Refactor: Remove Agno
### Requirements
- **Remove `agno`:** Eliminate the dependency on the `agno` library.
- **Direct LiteLLM:** Replace all LLM interaction logic handled by `agno` with direct calls to `LiteLLM`.
- **Functionality Neutral:** The external behavior of the system must remain exactly the same. This is a pure refactor.
