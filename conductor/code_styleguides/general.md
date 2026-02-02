# General Code Style Principles

This document outlines general coding principles that apply across all languages and frameworks used in this project.

## Readability
- Code should be easy to read and understand by humans.
- Avoid overly clever or obscure constructs.

## Consistency
- Follow existing patterns in the codebase.
- Maintain consistent formatting, naming, and structure.

## Simplicity
- Prefer simple solutions over complex ones.
- Break down complex problems into smaller, manageable parts.

## Maintainability
- Write code that is easy to modify and extend.
- Minimize dependencies and coupling.
- **Clean Separation of Concerns:** Maintain a strict boundary between **Logic** (Domain models, workflow, state transitions) and **Representation** (UI widgets, formatting, serialization).
    - Domain classes (like `Scene` or `Campaign`) should focus purely on the "what" and "how" of the domain rules.
    - Heuristics or UI-specific data enhancements (like scanning text for interactive widgets) should be handled in dedicated formatting methods or at the API/UI boundary, never inside core logic methods.

## Documentation
- Document *why* something is done, not just *what*.
- Keep documentation up-to-date with code changes.
