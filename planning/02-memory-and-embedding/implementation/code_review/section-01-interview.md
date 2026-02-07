# Code Review Interview: Section 01 - Models and Health

## Finding 1: Concurrency hazard in CampaignHealth.set_status
- **Decision: Add asyncio.Lock** (user approved)
- Add `self._lock = asyncio.Lock()` in `__init__` and wrap `set_status` body in `async with self._lock`.

## Finding 2: No exception handling on on_change callback
- **Decision: Auto-fix** - wrap callback in try/except with logging

## Finding 3: Memory model lacks defaults
- **Decision: Add defaults** (user approved)
- `id`: default_factory=lambda: str(uuid.uuid4())
- `created_at`: default_factory=time.time
- `updated_at`: default_factory=time.time
- `access_count`: default=0
- `last_accessed_at`: default=None (already optional)

## Finding 4: No validation on visibility field
- **Decision: Let go** - plan explicitly chose plain str for extensibility

## Finding 5: No ge=1 validation on config int fields
- **Decision: Auto-fix** - add ge=1 constraint to context_limit, memory_token_budget, vector_dimension

## Finding 6: Dataclass/Pydantic serialization fragility
- **Decision: Let go** - Pydantic V2 handles dataclasses well

## Finding 7: Duplicated _make_memory helper in tests
- **Decision: Auto-fix** - extract to module-level helper function

## Finding 8: No __all__ in memory/__init__.py
- **Decision: Let go** - not needed at this stage
