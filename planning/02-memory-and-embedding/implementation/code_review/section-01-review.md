# Code Review: Section 01 - Models and Health

The implementation is faithful to the plan with all specified files created and modified. However, there are several issues ranging from moderate to minor that a senior architect would flag.

**1. Thread safety / concurrency hazard in CampaignHealth (moderate)**

In `/home/harald/src/sidestage/src/sidestage/health.py`, lines 28-32, `set_status` performs a check-then-act pattern without any synchronization:

```python
changed = status != self.status
self.status = status
self.reason = reason
if changed and self._on_change is not None:
    await self._on_change(status, reason)
```

If two concurrent coroutines call `set_status` simultaneously (e.g., one from the embedding subsystem and one from the graph reconnection logic), the `changed` flag can be stale by the time the callback fires. Since the plan explicitly describes multiple subsystems driving transitions (embedding failure, graph reconnection), this is a realistic race. An `asyncio.Lock` should guard the entire transition block.

**2. No exception handling if on_change callback raises (moderate)**

In `/home/harald/src/sidestage/src/sidestage/health.py`, line 32, if `self._on_change(status, reason)` raises an exception, the status and reason have already been updated (lines 29-30) but the caller gets an unhandled exception. The plan says the primary consumer is a WebSocket broadcast -- WebSocket errors are common (client disconnects). A failing callback should not crash the health transition. At minimum the callback invocation should be wrapped in a try/except that logs and suppresses the error, or the design should document that callers must handle this.

**3. Memory model has no defaults for required fields -- constructing a Memory is verbose and error-prone (minor-moderate)**

In `/home/harald/src/sidestage/src/sidestage/memory/models.py`, lines 16-28, every field on `Memory` is required (no defaults except the `None`-typed optionals). Fields like `access_count`, `created_at`, `updated_at`, and `id` are boilerplate that should have sensible defaults (e.g., `access_count: int = 0`, `created_at: float = Field(default_factory=time.time)`, `id: str = Field(default_factory=lambda: str(uuid.uuid4()))`). The test code already demonstrates this pain -- both `TestMemory` and `TestContextMemories` duplicate a `_make_memory` helper to paper over the lack of defaults. This duplication will proliferate into the store and context layers.

**4. No validation on the visibility field (minor-moderate)**

The plan explicitly notes `visibility` is a plain `str` for future extensibility, but there is zero validation. Any garbage string (empty string, typos like 'pubilc') will be silently accepted. A `Literal['common', 'private']` or at minimum a Pydantic `field_validator` that warns on unexpected values would prevent data corruption in the graph store without blocking extensibility.

**5. No validation on context_limit and memory_token_budget (minor)**

`context_limit` and `memory_token_budget` accept `int | None` but have no `ge=1` or `gt=0` constraint. A value of `0` or `-5` would be silently accepted and later cause division-by-zero or nonsensical behavior in the context assembly (section 06). Same applies to `vector_dimension` in `GraphConfig`.

**6. GraphConfig is a dataclass embedded in a Pydantic BaseModel -- serialization fragility (minor)**

The test calls `config.model_dump()` and accesses `dumped['graph']['vector_dimension']`. This works because Pydantic V2 can serialize dataclasses, but it relies on implicit behavior. If `GraphConfig` gains a field that Pydantic cannot auto-serialize, this will break silently.

**7. Duplicated _make_memory helper across test classes (minor)**

`_make_memory` is defined identically in both `TestMemory` and `TestContextMemories`. This should be extracted to a module-level fixture or helper to follow DRY.

**8. No __all__ in memory/__init__.py (minor)**

The package init re-exports symbols but does not define `__all__`. Static analysis tools cannot determine the public API boundary.

**9. Tests correctly match the plan specification**

All test cases listed in the plan are present in the diff. The plan specifies 8 test cases for memory models, 11 for health, and 7 for campaign config. The implementation covers all of these. The async tests correctly use `@pytest.mark.anyio`.

**Summary**: The implementation is complete relative to the plan, but has a real concurrency hazard in `CampaignHealth.set_status`, missing input validation on numeric config fields and the visibility string, no error handling around the on_change callback, and test code duplication.
