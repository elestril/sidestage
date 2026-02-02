# Implementation Plan - Cleanup and Architecture Refactor

## Phase 1: Documentation and Schema Standards
- [x] Update `conductor/workflow.md` with new documentation requirements.
- [x] Create/Update `docs/api.md` (or similar) with current JSON API details.
- [x] Create/Update `docs/ui_structure.md` with current Web Interface details.
- [x] Create/Update `docs/features.md` with current Feature list.
- [x] Create/Update `docs/user_journeys.md`.
- [x] Define canonical JSON schemas for all APIs (e.g., in `src/sidestage/schemas.py` or `docs/schemas/`).
- [x] Add tests to verify Python backend conforms to schemas.
- [x] Add tests/checks to verify Frontend conforms to schemas (where applicable).

## Phase 2: Orchestrator and Campaign Split
- [x] Refactor `SidestageOrchestrator` to extract `Campaign` class.
- [x] Move state management from Orchestrator to Campaign.
- [x] Update `SidestageOrchestrator` to manage a list of `Campaign`s.
- [x] Update usage of Orchestrator throughout the codebase to reflect this change.
- [x] Verify refactor with existing tests.

## Phase 3: Remove Agno Dependency
- [x] Identify all usages of `agno` in the codebase.
- [x] Replace `agno` usage with direct `LiteLLM` calls in `src/sidestage/orchestrator.py` (or new `Campaign` class).
- [x] Replace `agno` usage in `src/sidestage/tools.py` if applicable.
- [x] Remove `agno` from `pyproject.toml` / `poetry.lock`.
- [x] Run all tests to ensure functionality is neutral.
