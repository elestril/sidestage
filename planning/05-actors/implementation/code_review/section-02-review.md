# Code Review: Section 02 - Actor Hierarchy and Character System Refactor

## CRITICAL: Scene.py left broken
Scene.py still imports ChatMessageModel, uses old on_event() method, old Character constructor. This is expected per the plan (Scene changes are in section-04). The application is non-functional until then.

## HIGH: NPCActor._resolve_actor() creates bare NPCActor
Campaign._resolve_actor() creates NPCActor without runtime dependencies (character, scene_logic, graph_client, etc.). The _update_prompt() method will silently return without creating an agent.

## HIGH: User.connect() does not call ws.accept()
Plan says connect() should call ws.accept(). Implementation only appends.

## HIGH: User.connections typed as list[Any]
Plan specifies list[WebSocket]. Implementation uses list[Any], missing the WebSocket import from fastapi.

## MEDIUM: Event ID generation is fragile and non-unique
Uses f"evt_{char_id}_{gametime}" instead of uuid4(). Could produce duplicates.

## MEDIUM: Missing newline at end of system_agent.txt

## MEDIUM: NPCActor.process() response event lacks scene reference

## MEDIUM: _update_prompt() accesses self.character without null checks

## MEDIUM: Incomplete test coverage
Missing campaign registry tests, LLM integration tests, actor resolution tests.

## LOW: User.process() uses model_dump(mode="json") vs plan's model_dump()

## LOW: Tracing - no record_error() call on failure
