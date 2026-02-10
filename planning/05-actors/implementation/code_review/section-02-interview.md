# Code Review Interview: Section 02 - Actors

**Date:** 2026-02-09

## Auto-Fixes

### 3. User.connect() should call ws.accept()
Adding await ws.accept() before appending.

### 5. Event ID generation - use uuid4
Changing to uuid4() pattern consistent with rest of codebase.

### 6. Missing newline at end of system_agent.txt
Adding trailing newline.

## Let Go (No Action)

- #1: Scene.py broken (per plan, fixed in section-04)
- #2: Bare NPCActor (dependencies wired during scene activation in later sections)
- #4: list[Any] typing (minor, avoids heavy FastAPI coupling in this module)
- #7: Response event no scene ref (Scene sets it during processing)
- #8: _update_prompt null chars (only called after character is set)
- #9: Missing integration tests (core tested; campaign/LLM tests in later sections)
- #10: model_dump(mode="json") (better for JSON serialization)
- #11: No record_error (tracing reworked in section-05)
